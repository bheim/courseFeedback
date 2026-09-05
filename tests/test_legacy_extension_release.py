import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PACKAGER_PATH = REPOSITORY_ROOT / "release" / "package_legacy_extension.py"
BASELINE_PATH = REPOSITORY_ROOT / "release" / "legacy_extension_v3.0.baseline.json"
SOURCE_PATH = REPOSITORY_ROOT / "courseFeedbackLaunch"

SPEC = importlib.util.spec_from_file_location("package_legacy_extension", PACKAGER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load packager from {PACKAGER_PATH}")
PACKAGER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGER)


class LegacyExtensionReleaseTests(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temporary_directory.name)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _copy_source(self):
        destination = self.temp_path / "source"
        shutil.copytree(SOURCE_PATH, destination)
        return destination

    def _write_baseline(self, baseline):
        path = self.temp_path / "baseline.json"
        path.write_text(json.dumps(baseline), encoding="utf-8")
        return path

    def test_baseline_records_exact_untouched_v3_source(self):
        baseline = PACKAGER.load_baseline(BASELINE_PATH)
        entries = {entry["path"]: entry for entry in baseline["files"]}
        actual_paths = {
            path.relative_to(SOURCE_PATH).as_posix()
            for path in SOURCE_PATH.rglob("*")
            if path.is_file()
        }

        self.assertEqual(set(entries), actual_paths)
        for relative, entry in entries.items():
            data = (SOURCE_PATH / relative).read_bytes()
            self.assertEqual(entry["size"], len(data), relative)
            self.assertEqual(entry["sha256"], hashlib.sha256(data).hexdigest(), relative)

        self.assertEqual(baseline["extension"]["version"], "3.0")
        self.assertEqual(baseline["extension"]["manifest_version"], 3)
        self.assertEqual(
            baseline["extension"]["chrome_web_store_id"],
            "fhmmbigjknknbmejcjbnkjjpfkbkndim",
        )
        self.assertEqual(
            baseline["source_repository"]["git_commit"],
            "0f53d31b35c8a5ca527048048c962c33d6b312da",
        )
        source_tree = subprocess.run(
            [
                "git",
                "rev-parse",
                f"{baseline['source_repository']['git_commit']}:"
                f"{baseline['source_directory']}",
            ],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.assertEqual(baseline["source_repository"]["git_tree"], source_tree)

    def test_package_is_deterministic_and_contains_only_allowlist(self):
        first = self.temp_path / "first.zip"
        second = self.temp_path / "second.zip"
        PACKAGER.build_package(output_path=first)
        PACKAGER.build_package(output_path=second)

        self.assertEqual(first.read_bytes(), second.read_bytes())
        baseline = PACKAGER.load_baseline(BASELINE_PATH)
        expected_paths = sorted(entry["path"] for entry in baseline["files"])
        with zipfile.ZipFile(first) as archive:
            self.assertEqual(archive.namelist(), expected_paths)
            for info in archive.infolist():
                self.assertEqual(info.date_time, PACKAGER.FIXED_ZIP_TIMESTAMP)
                self.assertEqual(info.compress_type, zipfile.ZIP_STORED)
                self.assertEqual((info.external_attr >> 16) & 0o777, 0o644)
                self.assertEqual(archive.read(info.filename), (SOURCE_PATH / info.filename).read_bytes())

    def test_rejects_unexpected_file(self):
        source = self._copy_source()
        (source / ".DS_Store").write_bytes(b"metadata")

        with self.assertRaisesRegex(PACKAGER.PackagingError, "unexpected files"):
            PACKAGER.build_package(source_dir=source, output_path=self.temp_path / "output.zip")

    def test_rejects_changed_allowlisted_file(self):
        source = self._copy_source()
        (source / "background.js").write_bytes(b"changed")

        with self.assertRaisesRegex(PACKAGER.PackagingError, "size mismatch|SHA-256 mismatch"):
            PACKAGER.build_package(source_dir=source, output_path=self.temp_path / "output.zip")

    def test_rejects_missing_allowlisted_file(self):
        source = self._copy_source()
        (source / "background.js").unlink()

        with self.assertRaisesRegex(PACKAGER.PackagingError, "allowlisted files missing"):
            PACKAGER.build_package(source_dir=source, output_path=self.temp_path / "output.zip")

    def test_rejects_symlink(self):
        source = self._copy_source()
        link = source / "extra-link"
        try:
            os.symlink(source / "manifest.json", link)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlinks are unavailable: {exc}")

        with self.assertRaisesRegex(PACKAGER.PackagingError, "symlink is forbidden"):
            PACKAGER.build_package(source_dir=source, output_path=self.temp_path / "output.zip")

    def test_rejects_path_traversal_in_allowlist(self):
        baseline = copy.deepcopy(PACKAGER.load_baseline(BASELINE_PATH))
        baseline["files"][0]["path"] = "../background.js"
        path = self._write_baseline(baseline)

        with self.assertRaisesRegex(PACKAGER.PackagingError, r"unsafe files\[0\]\.path"):
            PACKAGER.load_baseline(path)

    def test_rejects_forbidden_secret_and_raw_database_even_if_allowlisted(self):
        original = PACKAGER.load_baseline(BASELINE_PATH)
        for forbidden_path in (
            "comments.db",
            "comments.db.gz",
            "cookies/cookies.pkl",
            ".env.local",
            "production.env",
        ):
            with self.subTest(path=forbidden_path):
                baseline = copy.deepcopy(original)
                baseline["files"][0]["path"] = forbidden_path
                path = self._write_baseline(baseline)
                with self.assertRaisesRegex(PACKAGER.PackagingError, "forbidden secret/raw-data"):
                    PACKAGER.load_baseline(path)

    def test_rejects_output_inside_source_tree(self):
        with self.assertRaisesRegex(PACKAGER.PackagingError, "outside the extension source"):
            PACKAGER.build_package(output_path=SOURCE_PATH / "release.zip")

    def test_rejects_source_directory_symlink(self):
        source_link = self.temp_path / "source-link"
        try:
            os.symlink(SOURCE_PATH, source_link)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlinks are unavailable: {exc}")

        with self.assertRaisesRegex(PACKAGER.PackagingError, "source path may not be a symlink"):
            PACKAGER.build_package(
                source_dir=source_link,
                output_path=self.temp_path / "output.zip",
            )

    def test_rejects_output_symlink(self):
        real_output = self.temp_path / "real.zip"
        real_output.write_bytes(b"do not overwrite")
        output_link = self.temp_path / "output-link.zip"
        try:
            os.symlink(real_output, output_link)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlinks are unavailable: {exc}")

        with self.assertRaisesRegex(PACKAGER.PackagingError, "output path may not be a symlink"):
            PACKAGER.build_package(output_path=output_link)
        self.assertEqual(real_output.read_bytes(), b"do not overwrite")


if __name__ == "__main__":
    unittest.main()
