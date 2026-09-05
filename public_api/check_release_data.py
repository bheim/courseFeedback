"""Validate a normalized database artifact before the public API can serve it.

The checker is side-effect free: it opens SQLite read-only and never constructs
the Flask application. It supports both module and direct-script invocation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Iterable, Mapping, Sequence

if __package__:
    from .database import configured_database_path, connect_read_only
    from .evidence import (
        COURSE_RATING_COLUMNS,
        DUPLICATE_CONFLICT_COLUMNS,
        HOUR_COLUMNS,
        PROFESSOR_RATING_COLUMNS,
        SELECTED_COURSE_COLUMNS,
        conflicting_non_null_fields,
    )
else:
    from database import configured_database_path, connect_read_only
    from evidence import (
        COURSE_RATING_COLUMNS,
        DUPLICATE_CONFLICT_COLUMNS,
        HOUR_COLUMNS,
        PROFESSOR_RATING_COLUMNS,
        SELECTED_COURSE_COLUMNS,
        conflicting_non_null_fields,
    )


MANIFEST_ENV = "COURSE_FEEDBACK_ARTIFACT_MANIFEST"
MANIFEST_VERSION = 1
MAX_MANIFEST_BYTES = 256 * 1024

REPORT_HASH_COLUMNS = (
    "url",
    "dept",
    "quarter",
    "course_id",
) + COURSE_RATING_COLUMNS + PROFESSOR_RATING_COLUMNS + HOUR_COLUMNS + (
    "interest_before",
    "interest_after",
    "response_count",
)
GATE_CONFLICT_COLUMNS = DUPLICATE_CONFLICT_COLUMNS + (
    "interest_before",
    "interest_after",
)

COUNT_MANIFEST_FIELDS = (
    "database_size_bytes",
    "nonempty_sqlite_sidecars",
    "course_rows",
    "distinct_report_urls",
    "null_or_blank_report_urls",
    "logical_duplicate_report_groups",
    "logical_duplicate_report_rows",
    "professor_rows",
    "total_links",
    "valid_links",
    "links_with_any_missing_parent",
    "dangling_course_links",
    "dangling_professor_links",
    "foreign_key_violations",
    "duplicate_physical_link_groups",
    "duplicate_physical_link_rows",
    "duplicate_url_professor_pair_groups",
    "duplicate_url_professor_pair_rows",
    "conflicting_duplicate_report_groups",
    "conflicting_non_null_field_instances",
    "reports_without_valid_professor_links",
)
HASH_MANIFEST_FIELDS = (
    "database_sha256",
    "report_rows_sha256",
    "professor_rows_sha256",
    "professor_links_sha256",
)


class ManifestError(ValueError):
    """Raised when a supplied artifact manifest is malformed."""


@dataclass(frozen=True)
class IntegrityReport:
    database_path: str
    database_size_bytes: int
    database_sha256: str
    nonempty_sqlite_sidecars: int
    quick_check_ok: bool
    course_rows: int
    distinct_report_urls: int
    null_or_blank_report_urls: int
    logical_duplicate_report_groups: int
    logical_duplicate_report_rows: int
    professor_rows: int
    total_links: int
    valid_links: int
    links_with_any_missing_parent: int
    dangling_course_links: int
    dangling_professor_links: int
    foreign_key_violations: int
    duplicate_physical_link_groups: int
    duplicate_physical_link_rows: int
    duplicate_url_professor_pair_groups: int
    duplicate_url_professor_pair_rows: int
    conflicting_duplicate_report_groups: int
    conflicting_non_null_field_instances: int
    reports_without_valid_professor_links: int
    report_rows_sha256: str
    professor_rows_sha256: str
    professor_links_sha256: str
    conflict_examples: tuple[str, ...] = ()
    manifest_path: str | None = None
    manifest_errors: tuple[str, ...] = ()

    @property
    def integrity_errors(self) -> tuple[str, ...]:
        errors: list[str] = []
        if self.course_rows == 0 or self.distinct_report_urls == 0:
            errors.append("artifact contains no report rows")
        if self.professor_rows == 0:
            errors.append("artifact contains no professor rows")
        if self.valid_links == 0:
            errors.append("artifact contains no valid professor-report links")
        if not self.quick_check_ok:
            errors.append("SQLite PRAGMA quick_check did not return ok")
        violations = (
            ("nonempty SQLite sidecar files", self.nonempty_sqlite_sidecars),
            ("report rows with null/blank URL", self.null_or_blank_report_urls),
            ("excess logical report rows", self.logical_duplicate_report_rows),
            ("links with any missing parent", self.links_with_any_missing_parent),
            ("dangling course links", self.dangling_course_links),
            ("dangling professor links", self.dangling_professor_links),
            ("foreign-key violations", self.foreign_key_violations),
            ("duplicate physical course/professor link rows", self.duplicate_physical_link_rows),
            ("duplicate URL/professor link rows", self.duplicate_url_professor_pair_rows),
            ("duplicate reports with conflicting evidence", self.conflicting_duplicate_report_groups),
            ("report URLs without a valid professor link", self.reports_without_valid_professor_links),
        )
        errors.extend(f"{label}: {count}" for label, count in violations if count)
        return tuple(errors)

    @property
    def ready(self) -> bool:
        return not self.integrity_errors and not self.manifest_errors

    def as_json(self) -> dict[str, object]:
        payload = asdict(self)
        payload["integrity_errors"] = list(self.integrity_errors)
        payload["ready"] = self.ready
        return payload


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as database_file:
        for chunk in iter(lambda: database_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _frame_bytes(value: bytes) -> bytes:
    return str(len(value)).encode("ascii") + b":" + value


def _typed_value_bytes(value: object) -> bytes:
    if value is None:
        return b"N"
    if type(value) is int:
        return b"I" + _frame_bytes(str(value).encode("ascii"))
    if type(value) is float:
        return b"F" + _frame_bytes(value.hex().encode("ascii"))
    if type(value) is bytes:
        return b"B" + _frame_bytes(value)
    if type(value) is str:
        return b"T" + _frame_bytes(value.encode("utf-8"))
    raise TypeError(f"unsupported SQLite value type in logical hash: {type(value).__name__}")


def _query_sha256(
    connection: sqlite3.Connection,
    domain: str,
    columns: Sequence[str],
    query: str,
    parameters: Sequence[object] = (),
) -> str:
    digest = hashlib.sha256()
    digest.update(b"course-feedback-logical-hash-v1\n")
    digest.update(_frame_bytes(domain.encode("utf-8")))
    for column in columns:
        digest.update(_frame_bytes(column.encode("utf-8")))
    for row in connection.execute(query, parameters):
        digest.update(b"R")
        for value in row:
            digest.update(_typed_value_bytes(value))
    return digest.hexdigest()


def _duplicate_conflicts(
    connection: sqlite3.Connection,
) -> tuple[int, int, tuple[str, ...]]:
    columns = tuple(
        dict.fromkeys(SELECTED_COURSE_COLUMNS + ("interest_before", "interest_after"))
    )
    rows = connection.execute(
        f"SELECT {', '.join(columns)} FROM courses "
        "WHERE url IS NOT NULL AND trim(url) != '' ORDER BY url, id"
    )
    current_url: str | None = None
    group: list[sqlite3.Row] = []
    conflict_groups = 0
    conflict_fields = 0
    examples: list[str] = []

    def inspect_group(report_url: str | None, report_rows: Sequence[sqlite3.Row]) -> None:
        nonlocal conflict_groups, conflict_fields
        if report_url is None or len(report_rows) < 2:
            return
        fields = conflicting_non_null_fields(report_rows, GATE_CONFLICT_COLUMNS)
        if not fields:
            return
        conflict_groups += 1
        conflict_fields += len(fields)
        if len(examples) < 10:
            url_fingerprint = hashlib.sha256(report_url.encode("utf-8")).hexdigest()[:12]
            examples.append(f"url_sha256:{url_fingerprint} fields:{','.join(fields)}")

    for row in rows:
        row_url = str(row["url"])
        if current_url is not None and row_url != current_url:
            inspect_group(current_url, group)
            group = []
        current_url = row_url
        group.append(row)
    inspect_group(current_url, group)
    return conflict_groups, conflict_fields, tuple(examples)


def _reject_duplicate_json_keys(pairs: Iterable[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ManifestError(f"duplicate manifest key: {key}")
        result[key] = value
    return result


def _read_manifest(path: Path) -> Mapping[str, object]:
    if not path.is_file():
        raise ManifestError(f"manifest is not a file: {path}")
    if path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ManifestError(f"manifest exceeds {MAX_MANIFEST_BYTES} bytes")
    try:
        manifest = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ManifestError(f"non-finite JSON value is forbidden: {value}")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ManifestError) as error:
        raise ManifestError(f"cannot read manifest: {error}") from error
    if not isinstance(manifest, dict):
        raise ManifestError("manifest root must be an object")
    return manifest


def _manifest_errors(report: IntegrityReport, manifest_path: Path) -> tuple[str, ...]:
    try:
        manifest = _read_manifest(manifest_path)
    except ManifestError as error:
        return (str(error),)

    errors: list[str] = []
    allowed_top_level = {"manifest_version", "counts", "hashes"}
    unknown_top_level = sorted(set(manifest).difference(allowed_top_level))
    if unknown_top_level:
        errors.append(f"unknown manifest keys: {', '.join(unknown_top_level)}")
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        errors.append(f"manifest_version must equal {MANIFEST_VERSION}")

    counts = manifest.get("counts")
    if not isinstance(counts, dict) or not counts:
        errors.append("manifest counts must be a non-empty object")
    else:
        missing_counts = sorted(set(COUNT_MANIFEST_FIELDS).difference(counts))
        if missing_counts:
            errors.append(f"missing manifest count keys: {', '.join(missing_counts)}")
        unknown_counts = sorted(set(counts).difference(COUNT_MANIFEST_FIELDS))
        if unknown_counts:
            errors.append(f"unknown manifest count keys: {', '.join(unknown_counts)}")
        for field, expected in counts.items():
            if field not in COUNT_MANIFEST_FIELDS:
                continue
            if not isinstance(expected, int) or isinstance(expected, bool) or expected < 0:
                errors.append(f"manifest count {field} must be a non-negative integer")
                continue
            actual = getattr(report, field)
            if actual != expected:
                errors.append(f"manifest count mismatch for {field}: expected {expected}, got {actual}")

    hashes = manifest.get("hashes")
    if not isinstance(hashes, dict) or not hashes:
        errors.append("manifest hashes must be a non-empty object")
    else:
        missing_hashes = sorted(set(HASH_MANIFEST_FIELDS).difference(hashes))
        if missing_hashes:
            errors.append(f"missing manifest hash keys: {', '.join(missing_hashes)}")
        unknown_hashes = sorted(set(hashes).difference(HASH_MANIFEST_FIELDS))
        if unknown_hashes:
            errors.append(f"unknown manifest hash keys: {', '.join(unknown_hashes)}")
        for field, expected in hashes.items():
            if field not in HASH_MANIFEST_FIELDS:
                continue
            if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
                errors.append(
                    f"manifest hash {field} must be a lowercase 64-character SHA-256 hex string"
                )
                continue
            actual = getattr(report, field)
            if actual != expected:
                errors.append(f"manifest hash mismatch for {field}")
    return tuple(errors)


def expected_manifest(report: IntegrityReport) -> dict[str, object]:
    """Return a strict manifest for a structurally valid normalized artifact."""

    if report.integrity_errors:
        raise ManifestError("cannot manifest an artifact that fails structural integrity checks")
    return {
        "manifest_version": MANIFEST_VERSION,
        "counts": {field: getattr(report, field) for field in COUNT_MANIFEST_FIELDS},
        "hashes": {field: getattr(report, field) for field in HASH_MANIFEST_FIELDS},
    }


def inspect_release_data(
    database_path: str | os.PathLike[str] | None = None,
    manifest_path: str | os.PathLike[str] | None = None,
) -> IntegrityReport:
    path = configured_database_path(database_path)
    database_size = path.stat().st_size
    nonempty_sidecars = sum(
        sidecar.is_file() and sidecar.stat().st_size > 0
        for sidecar in (
            Path(f"{path}-wal"),
            Path(f"{path}-shm"),
            Path(f"{path}-journal"),
        )
    )
    database_hash = _file_sha256(path)

    with connect_read_only(path) as connection:
        quick_check_rows = [row[0] for row in connection.execute("PRAGMA quick_check")]
        quick_check_ok = quick_check_rows == ["ok"]
        foreign_key_violations = sum(1 for _row in connection.execute("PRAGMA foreign_key_check"))
        course_counts = connection.execute(
            """
            SELECT COUNT(*) AS course_rows,
                   COUNT(DISTINCT CASE WHEN url IS NOT NULL AND trim(url) != '' THEN url END)
                       AS distinct_report_urls,
                   SUM(CASE WHEN url IS NULL OR trim(url) = '' THEN 1 ELSE 0 END)
                       AS null_or_blank_report_urls
            FROM courses
            """
        ).fetchone()
        duplicate_counts = connection.execute(
            """
            SELECT COUNT(*) AS duplicate_groups, COALESCE(SUM(row_count - 1), 0) AS duplicate_rows
            FROM (
                SELECT url, COUNT(*) AS row_count
                FROM courses
                WHERE url IS NOT NULL AND trim(url) != ''
                GROUP BY url HAVING COUNT(*) > 1
            )
            """
        ).fetchone()
        professor_rows = connection.execute("SELECT COUNT(*) FROM professors").fetchone()[0]
        link_counts = connection.execute(
            """
            SELECT COUNT(*) AS total_links,
                   SUM(CASE WHEN c.id IS NOT NULL AND p.id IS NOT NULL THEN 1 ELSE 0 END)
                       AS valid_links,
                   SUM(CASE WHEN c.id IS NULL OR p.id IS NULL THEN 1 ELSE 0 END)
                       AS links_with_any_missing_parent,
                   SUM(CASE WHEN c.id IS NULL THEN 1 ELSE 0 END) AS dangling_course_links,
                   SUM(CASE WHEN p.id IS NULL THEN 1 ELSE 0 END) AS dangling_professor_links
            FROM courses_professors AS cp
            LEFT JOIN courses AS c ON c.id = cp.course_id
            LEFT JOIN professors AS p ON p.id = cp.professor_id
            """
        ).fetchone()
        duplicate_physical_link_counts = connection.execute(
            """
            SELECT COUNT(*) AS duplicate_groups, COALESCE(SUM(pair_count - 1), 0) AS duplicate_rows
            FROM (
                SELECT cp.course_id, cp.professor_id, COUNT(*) AS pair_count
                FROM courses_professors AS cp
                JOIN courses AS c ON c.id = cp.course_id
                JOIN professors AS p ON p.id = cp.professor_id
                GROUP BY cp.course_id, cp.professor_id HAVING COUNT(*) > 1
            )
            """
        ).fetchone()
        duplicate_pair_counts = connection.execute(
            """
            SELECT COUNT(*) AS duplicate_groups, COALESCE(SUM(pair_count - 1), 0) AS duplicate_rows
            FROM (
                SELECT c.url, cp.professor_id, COUNT(*) AS pair_count
                FROM courses_professors AS cp
                JOIN courses AS c ON c.id = cp.course_id
                JOIN professors AS p ON p.id = cp.professor_id
                WHERE c.url IS NOT NULL AND trim(c.url) != ''
                GROUP BY c.url, cp.professor_id HAVING COUNT(*) > 1
            )
            """
        ).fetchone()
        unlinked_reports = connection.execute(
            """
            WITH report_urls AS (
                SELECT DISTINCT url FROM courses
                WHERE url IS NOT NULL AND trim(url) != ''
            ), valid_linked_urls AS (
                SELECT DISTINCT c.url
                FROM courses_professors AS cp
                JOIN courses AS c ON c.id = cp.course_id
                JOIN professors AS p ON p.id = cp.professor_id
                WHERE c.url IS NOT NULL AND trim(c.url) != ''
            )
            SELECT COUNT(*) FROM report_urls AS reports
            LEFT JOIN valid_linked_urls AS linked ON linked.url = reports.url
            WHERE linked.url IS NULL
            """
        ).fetchone()[0]
        conflict_groups, conflict_fields, conflict_examples = _duplicate_conflicts(connection)
        report_hash = _query_sha256(
            connection,
            "courses",
            REPORT_HASH_COLUMNS,
            f"SELECT {', '.join(REPORT_HASH_COLUMNS)} FROM courses "
            "ORDER BY url, dept, course_id, quarter, id",
        )
        professor_hash_columns = ("id", "dept", "first_name", "last_name")
        professor_hash = _query_sha256(
            connection,
            "professors",
            professor_hash_columns,
            "SELECT id, dept, first_name, last_name FROM professors ORDER BY id",
        )
        link_hash_columns = ("report_url", "professor_id")
        link_hash = _query_sha256(
            connection,
            "courses_professors",
            link_hash_columns,
            """
            SELECT c.url, cp.professor_id
            FROM courses_professors AS cp
            JOIN courses AS c ON c.id = cp.course_id
            JOIN professors AS p ON p.id = cp.professor_id
            ORDER BY c.url, cp.professor_id, cp.id
            """,
        )

    report = IntegrityReport(
        database_path=str(path),
        database_size_bytes=database_size,
        database_sha256=database_hash,
        nonempty_sqlite_sidecars=int(nonempty_sidecars),
        quick_check_ok=quick_check_ok,
        course_rows=int(course_counts["course_rows"] or 0),
        distinct_report_urls=int(course_counts["distinct_report_urls"] or 0),
        null_or_blank_report_urls=int(course_counts["null_or_blank_report_urls"] or 0),
        logical_duplicate_report_groups=int(duplicate_counts["duplicate_groups"] or 0),
        logical_duplicate_report_rows=int(duplicate_counts["duplicate_rows"] or 0),
        professor_rows=int(professor_rows or 0),
        total_links=int(link_counts["total_links"] or 0),
        valid_links=int(link_counts["valid_links"] or 0),
        links_with_any_missing_parent=int(link_counts["links_with_any_missing_parent"] or 0),
        dangling_course_links=int(link_counts["dangling_course_links"] or 0),
        dangling_professor_links=int(link_counts["dangling_professor_links"] or 0),
        foreign_key_violations=int(foreign_key_violations),
        duplicate_physical_link_groups=int(
            duplicate_physical_link_counts["duplicate_groups"] or 0
        ),
        duplicate_physical_link_rows=int(
            duplicate_physical_link_counts["duplicate_rows"] or 0
        ),
        duplicate_url_professor_pair_groups=int(duplicate_pair_counts["duplicate_groups"] or 0),
        duplicate_url_professor_pair_rows=int(duplicate_pair_counts["duplicate_rows"] or 0),
        conflicting_duplicate_report_groups=conflict_groups,
        conflicting_non_null_field_instances=conflict_fields,
        reports_without_valid_professor_links=int(unlinked_reports or 0),
        report_rows_sha256=report_hash,
        professor_rows_sha256=professor_hash,
        professor_links_sha256=link_hash,
        conflict_examples=conflict_examples,
        manifest_path=str(Path(manifest_path).expanduser().resolve()) if manifest_path else None,
    )
    if manifest_path:
        resolved_manifest = Path(manifest_path).expanduser().resolve()
        report = replace(report, manifest_errors=_manifest_errors(report, resolved_manifest))
    return report


def _print_human(report: IntegrityReport) -> None:
    print(f"database: {report.database_path}")
    print(f"database sha256: {report.database_sha256}")
    print(
        f"SQLite quick_check: {'ok' if report.quick_check_ok else 'FAILED'}; "
        f"foreign-key violations: {report.foreign_key_violations}; "
        f"nonempty sidecars: {report.nonempty_sqlite_sidecars}"
    )
    print(
        f"reports: {report.course_rows} rows / {report.distinct_report_urls} URLs; "
        f"duplicate groups: {report.logical_duplicate_report_groups}; "
        f"excess rows: {report.logical_duplicate_report_rows}"
    )
    print(
        f"links: {report.total_links} total / {report.valid_links} valid; "
        f"any missing parent: {report.links_with_any_missing_parent}; "
        f"dangling course: {report.dangling_course_links}; "
        f"dangling professor: {report.dangling_professor_links}"
    )
    print(
        f"duplicate URL/professor pairs: {report.duplicate_url_professor_pair_groups} groups / "
        f"{report.duplicate_url_professor_pair_rows} excess rows"
    )
    print(
        f"duplicate physical course/professor pairs: "
        f"{report.duplicate_physical_link_groups} groups / "
        f"{report.duplicate_physical_link_rows} excess rows"
    )
    print(
        f"conflicting duplicate reports: {report.conflicting_duplicate_report_groups}; "
        f"conflicting fields: {report.conflicting_non_null_field_instances}"
    )
    print(f"report URLs without valid professor link: {report.reports_without_valid_professor_links}")
    for error in report.integrity_errors:
        print(f"INTEGRITY ERROR: {error}")
    for error in report.manifest_errors:
        print(f"MANIFEST ERROR: {error}")
    print(
        "PASS: normalized artifact is release-ready."
        if report.ready
        else "BLOCKED: artifact is not release-ready."
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", help="database artifact (default: configured local path)")
    parser.add_argument(
        "--manifest",
        default=os.environ.get(MANIFEST_ENV),
        help=f"expected JSON manifest (default: ${MANIFEST_ENV})",
    )
    parser.add_argument("--json", action="store_true", help="emit a machine-readable JSON report")
    args = parser.parse_args(argv)
    try:
        report = inspect_release_data(args.database, args.manifest)
    except (OSError, sqlite3.Error, ValueError) as error:
        if args.json:
            print(json.dumps({"ready": False, "error": str(error)}, sort_keys=True))
        else:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report.as_json(), sort_keys=True))
    else:
        _print_human(report)
    return 0 if report.ready else 1


if __name__ == "__main__":
    sys.exit(main())
