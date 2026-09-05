#!/usr/bin/env python3
"""Build a byte-for-byte verified, deterministic legacy-extension ZIP."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple
import zipfile


BASELINE_PATH = Path(__file__).with_name("legacy_extension_v3.0.baseline.json")
FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")

# Defense in depth: these may never enter an extension artifact, even if a
# future baseline file accidentally attempts to allowlist one.
FORBIDDEN_FILENAMES = {
    ".env",
    ".npmrc",
    ".pypirc",
    "auth.json",
    "comments.db",
    "cookies.pkl",
    "credentials.json",
    "id_dsa",
    "id_ed25519",
    "id_rsa",
    "prereg_dump.txt",
    "prereg_page.html",
    "service-account.json",
    "secrets.json",
    "token.json",
}
FORBIDDEN_SUFFIXES = {
    ".db",
    ".env",
    ".key",
    ".pem",
    ".pfx",
    ".pkl",
    ".p12",
    ".sqlite",
    ".sqlite3",
}
FORBIDDEN_DIRECTORY_NAMES = {"cookies", "credentials", "secrets"}


class PackagingError(ValueError):
    """Raised when a source tree or baseline is unsafe or inconsistent."""


def _reject_duplicate_json_keys(pairs: Iterable[Tuple[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PackagingError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _safe_relative_path(raw_path: Any, label: str) -> PurePosixPath:
    if not isinstance(raw_path, str) or not raw_path:
        raise PackagingError(f"{label} must be a non-empty string")
    if "\\" in raw_path or "\x00" in raw_path:
        raise PackagingError(f"unsafe {label}: {raw_path!r}")

    path = PurePosixPath(raw_path)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise PackagingError(f"unsafe {label}: {raw_path!r}")
    if path.as_posix() != raw_path:
        raise PackagingError(f"non-canonical {label}: {raw_path!r}")
    return path


def _reject_forbidden_path(path: PurePosixPath) -> None:
    lowered_parts = tuple(part.lower() for part in path.parts)
    filename = lowered_parts[-1]
    suffixes = {suffix.lower() for suffix in PurePosixPath(filename).suffixes}

    if (
        filename in FORBIDDEN_FILENAMES
        or filename.startswith(".env.")
        or suffixes.intersection(FORBIDDEN_SUFFIXES)
        or any(part in FORBIDDEN_DIRECTORY_NAMES for part in lowered_parts[:-1])
    ):
        raise PackagingError(f"forbidden secret/raw-data path in allowlist: {path}")


def load_baseline(path: Path = BASELINE_PATH) -> Mapping[str, Any]:
    """Read and strictly validate a release baseline manifest."""

    try:
        raw = path.read_text(encoding="utf-8")
        baseline = json.loads(raw, object_pairs_hook=_reject_duplicate_json_keys)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PackagingError(f"cannot read baseline {path}: {exc}") from exc

    if not isinstance(baseline, dict):
        raise PackagingError("baseline root must be a JSON object")
    if baseline.get("schema_version") != 1:
        raise PackagingError("unsupported baseline schema_version")
    if baseline.get("artifact") != "legacy-chrome-extension":
        raise PackagingError("baseline artifact must be 'legacy-chrome-extension'")

    _safe_relative_path(baseline.get("source_directory"), "source_directory")

    extension = baseline.get("extension")
    if not isinstance(extension, dict):
        raise PackagingError("baseline extension metadata must be an object")
    if not isinstance(extension.get("name"), str) or not extension["name"]:
        raise PackagingError("baseline extension name must be a non-empty string")
    if not isinstance(extension.get("version"), str) or not extension["version"]:
        raise PackagingError("baseline extension version must be a non-empty string")
    if not isinstance(extension.get("manifest_version"), int):
        raise PackagingError("baseline manifest_version must be an integer")
    store_id = extension.get("chrome_web_store_id")
    if not isinstance(store_id, str) or re.fullmatch(r"[a-p]{32}", store_id) is None:
        raise PackagingError("baseline Chrome Web Store ID is invalid")

    repository = baseline.get("source_repository")
    if not isinstance(repository, dict):
        raise PackagingError("baseline source_repository must be an object")
    commit = repository.get("git_commit")
    tree = repository.get("git_tree")
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise PackagingError("baseline git_commit is invalid")
    if not isinstance(tree, str) or re.fullmatch(r"[0-9a-f]{40}", tree) is None:
        raise PackagingError("baseline git_tree is invalid")

    files = baseline.get("files")
    if not isinstance(files, list) or not files:
        raise PackagingError("baseline files must be a non-empty list")

    seen: Set[str] = set()
    for index, entry in enumerate(files):
        if not isinstance(entry, dict):
            raise PackagingError(f"files[{index}] must be an object")
        path_value = _safe_relative_path(entry.get("path"), f"files[{index}].path")
        _reject_forbidden_path(path_value)
        canonical = path_value.as_posix()
        if canonical in seen:
            raise PackagingError(f"duplicate allowlisted path: {canonical}")
        seen.add(canonical)

        size = entry.get("size")
        digest = entry.get("sha256")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise PackagingError(f"invalid size for {canonical}")
        if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
            raise PackagingError(f"invalid SHA-256 for {canonical}")

    if "manifest.json" not in seen:
        raise PackagingError("allowlist must contain manifest.json")
    return baseline


def _allowed_files(baseline: Mapping[str, Any]) -> Mapping[str, Mapping[str, Any]]:
    return {entry["path"]: entry for entry in baseline["files"]}


def _allowed_directories(paths: Iterable[str]) -> Set[str]:
    result: Set[str] = set()
    for raw_path in paths:
        parent = PurePosixPath(raw_path).parent
        while parent != PurePosixPath("."):
            result.add(parent.as_posix())
            parent = parent.parent
    return result


def _inspect_source_tree(source_dir: Path, allowlist: Set[str]) -> None:
    try:
        root_stat = source_dir.lstat()
    except OSError as exc:
        raise PackagingError(f"cannot inspect source directory {source_dir}: {exc}") from exc
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        raise PackagingError(f"source path is not a real directory: {source_dir}")

    allowed_dirs = _allowed_directories(allowlist)
    actual_files: Set[str] = set()

    for current, directory_names, file_names in os.walk(source_dir, followlinks=False):
        current_path = Path(current)

        for name in directory_names:
            candidate = current_path / name
            relative = candidate.relative_to(source_dir).as_posix()
            try:
                mode = candidate.lstat().st_mode
            except OSError as exc:
                raise PackagingError(f"cannot inspect {relative}: {exc}") from exc
            if stat.S_ISLNK(mode):
                raise PackagingError(f"symlink is forbidden in source tree: {relative}")
            if not stat.S_ISDIR(mode):
                raise PackagingError(f"non-directory source entry: {relative}")
            if relative not in allowed_dirs:
                raise PackagingError(f"unexpected directory in source tree: {relative}")

        for name in file_names:
            candidate = current_path / name
            relative = candidate.relative_to(source_dir).as_posix()
            try:
                mode = candidate.lstat().st_mode
            except OSError as exc:
                raise PackagingError(f"cannot inspect {relative}: {exc}") from exc
            if stat.S_ISLNK(mode):
                raise PackagingError(f"symlink is forbidden in source tree: {relative}")
            if not stat.S_ISREG(mode):
                raise PackagingError(f"non-regular source entry: {relative}")
            actual_files.add(relative)

    missing = sorted(allowlist - actual_files)
    unexpected = sorted(actual_files - allowlist)
    if missing:
        raise PackagingError(f"allowlisted files missing from source tree: {', '.join(missing)}")
    if unexpected:
        raise PackagingError(f"unexpected files in source tree: {', '.join(unexpected)}")


def _read_verified_files(
    source_dir: Path, entries: Mapping[str, Mapping[str, Any]]
) -> List[Tuple[str, bytes]]:
    verified: List[Tuple[str, bytes]] = []
    no_follow = getattr(os, "O_NOFOLLOW", 0)

    for relative in sorted(entries):
        path = source_dir.joinpath(*PurePosixPath(relative).parts)
        try:
            descriptor = os.open(path, os.O_RDONLY | no_follow)
            with os.fdopen(descriptor, "rb") as source_file:
                mode = os.fstat(source_file.fileno()).st_mode
                if not stat.S_ISREG(mode):
                    raise PackagingError(f"source entry is not a regular file: {relative}")
                data = source_file.read()
        except PackagingError:
            raise
        except OSError as exc:
            raise PackagingError(f"cannot read source file {relative}: {exc}") from exc

        expected = entries[relative]
        if len(data) != expected["size"]:
            raise PackagingError(
                f"size mismatch for {relative}: expected {expected['size']}, got {len(data)}"
            )
        digest = hashlib.sha256(data).hexdigest()
        if digest != expected["sha256"]:
            raise PackagingError(
                f"SHA-256 mismatch for {relative}: expected {expected['sha256']}, got {digest}"
            )
        verified.append((relative, data))
    return verified


def _verify_chrome_manifest(files: Sequence[Tuple[str, bytes]], baseline: Mapping[str, Any]) -> None:
    manifest_bytes = dict(files)["manifest.json"]
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PackagingError(f"source manifest.json is invalid: {exc}") from exc

    expected = baseline["extension"]
    comparisons = {
        "name": expected["name"],
        "version": expected["version"],
        "manifest_version": expected["manifest_version"],
    }
    for key, expected_value in comparisons.items():
        if manifest.get(key) != expected_value:
            raise PackagingError(
                f"source manifest.json {key} mismatch: "
                f"expected {expected_value!r}, got {manifest.get(key)!r}"
            )


def _path_is_within(path: Path, directory: Path) -> bool:
    try:
        return os.path.commonpath((str(path), str(directory))) == str(directory)
    except ValueError:
        return False


def build_package(
    *,
    baseline_path: Path = BASELINE_PATH,
    source_dir: Optional[Path] = None,
    output_path: Optional[Path] = None,
) -> Path:
    """Verify the source tree against its baseline and write a deterministic ZIP."""

    baseline_path = Path(baseline_path).resolve()
    baseline = load_baseline(baseline_path)

    if source_dir is None:
        repository_root = baseline_path.parent.parent
        source_relative = PurePosixPath(baseline["source_directory"])
        source_dir = repository_root.joinpath(*source_relative.parts)
    source_dir = Path(source_dir)
    if source_dir.is_symlink():
        raise PackagingError(f"source path may not be a symlink: {source_dir}")
    source_dir = source_dir.resolve()

    if output_path is None:
        version = baseline["extension"]["version"]
        output_path = baseline_path.parent / "dist" / f"course-feedback-extension-v{version}.zip"
    output_path = Path(output_path)
    if output_path.is_symlink():
        raise PackagingError(f"output path may not be a symlink: {output_path}")
    output_path = output_path.resolve()

    if _path_is_within(output_path, source_dir):
        raise PackagingError("output ZIP must be outside the extension source directory")
    entries = _allowed_files(baseline)
    _inspect_source_tree(source_dir, set(entries))
    files = _read_verified_files(source_dir, entries)
    _verify_chrome_manifest(files, baseline)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent, delete=False
        ) as temporary_file:
            temporary_name = temporary_file.name

        with zipfile.ZipFile(
            temporary_name,
            mode="w",
            compression=zipfile.ZIP_STORED,
            strict_timestamps=True,
        ) as archive:
            archive.comment = b""
            for relative, data in files:
                info = zipfile.ZipInfo(relative, date_time=FIXED_ZIP_TIMESTAMP)
                # Stored entries avoid depending on a particular zlib version,
                # making the complete artifact reproducible across runtimes.
                info.compress_type = zipfile.ZIP_STORED
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                info.extra = b""
                info.comment = b""
                archive.writestr(info, data, compress_type=zipfile.ZIP_STORED)

        os.replace(temporary_name, output_path)
        temporary_name = None
    except OSError as exc:
        raise PackagingError(f"cannot write output ZIP {output_path}: {exc}") from exc
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass

    return output_path


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a verified deterministic ZIP of the legacy Chrome extension."
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=BASELINE_PATH,
        help=f"baseline manifest (default: {BASELINE_PATH})",
    )
    parser.add_argument(
        "--source",
        type=Path,
        help="extension source directory (default: source_directory from the baseline)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="output ZIP path (default: release/dist/course-feedback-extension-vVERSION.zip)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    try:
        output = build_package(
            baseline_path=args.baseline,
            source_dir=args.source,
            output_path=args.output,
        )
    except PackagingError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(f"created {output}")
    print(f"sha256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
