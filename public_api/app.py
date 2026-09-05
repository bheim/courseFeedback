"""Hardened API for the public Course Feedback Chrome extension.

The two legacy routes and response keys are intentionally retained.  All
statistics are rebuilt from aggregate rows after deduplicating evaluation
reports by URL; this module never reads the raw-comments database.
"""

from __future__ import annotations

import math
import os
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from typing import Iterable, Sequence
from urllib.parse import urlencode

from flask import Flask, jsonify, request
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

if __package__:
    from .check_release_data import MANIFEST_ENV, IntegrityReport, inspect_release_data
    from .database import DB_PATH_ENV, DEFAULT_DB_PATH, configured_database_path, connect_read_only
    from .evidence import (
        COURSE_RATING_COLUMNS,
        HOUR_COLUMNS,
        HOUR_WEIGHTS,
        PROFESSOR_COURSE_RATING_COLUMNS,
        PROFESSOR_RATING_COLUMNS,
        SELECTED_COURSE_COLUMNS,
        ConflictingReportEvidence,
        CourseRow,
        merge_duplicate_report_rows as _merge_duplicate_report_rows,
    )
else:
    from check_release_data import MANIFEST_ENV, IntegrityReport, inspect_release_data
    from database import DB_PATH_ENV, DEFAULT_DB_PATH, configured_database_path, connect_read_only
    from evidence import (
        COURSE_RATING_COLUMNS,
        HOUR_COLUMNS,
        HOUR_WEIGHTS,
        PROFESSOR_COURSE_RATING_COLUMNS,
        PROFESSOR_RATING_COLUMNS,
        SELECTED_COURSE_COLUMNS,
        ConflictingReportEvidence,
        CourseRow,
        merge_duplicate_report_rows as _merge_duplicate_report_rows,
    )

MAX_REQUEST_BYTES = 256 * 1024
MAX_BATCH_SIZE = 250
MAX_COURSE_ID_LENGTH = 32
MAX_INSTRUCTOR_LENGTH = 256
MAX_OTHER_LISTINGS = 20
MAX_TOTAL_COURSE_REFERENCES = 750
RELEASE_MODE_ENV = "COURSE_FEEDBACK_RELEASE_MODE"

COURSE_ID_RE = re.compile(r"^\s*([A-Za-z]{2,8})\s+(\d{3,6})\s*$")
UNASSIGNED_INSTRUCTORS = {
    "",
    "staff",
    "tba",
    "tbd",
    "to be announced",
    "to be determined",
    "instructor tba",
    "instructor(s) tba",
    "not assigned",
}


class ValidationError(ValueError):
    """Raised when a request does not satisfy the bounded API contract."""


class ReleaseConfigurationError(RuntimeError):
    """Raised before startup when a release artifact is unsafe or unverified."""


@dataclass(frozen=True)
class CourseKey:
    dept: str
    number: int

    @property
    def label(self) -> str:
        return f"{self.dept} {self.number:05d}"


@dataclass(frozen=True)
class ValidatedItem:
    course_id: str
    instructor: str
    other_listings: tuple[str, ...]


@dataclass(frozen=True)
class InstructorIdentity:
    label: str
    professor_ids: tuple[int, ...]


@dataclass(frozen=True)
class InstructorResolution:
    status: str
    identities: tuple[InstructorIdentity, ...] = ()
    basis: str | None = None

    @property
    def professor_ids(self) -> tuple[int, ...]:
        return tuple(
            sorted(
                {
                    professor_id
                    for identity in self.identities
                    for professor_id in identity.professor_ids
                }
            )
        )


def parse_course_id(value: str) -> CourseKey | None:
    match = COURSE_ID_RE.fullmatch(value)
    if not match:
        return None
    return CourseKey(match.group(1).upper(), int(match.group(2)))


def _normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold().replace(".", "")
    return " ".join(value.split())


def _finite_float(value: object) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _mean(values: Iterable[float | None]) -> float | None:
    usable = [value for value in values if value is not None and math.isfinite(value)]
    return fmean(usable) if usable else None


def _row_rating(row: CourseRow, columns: Sequence[str]) -> float | None:
    return _mean(_finite_float(row[column]) for column in columns)


def _rows_rating(rows: Sequence[CourseRow], columns: Sequence[str]) -> tuple[float | None, int]:
    report_values = [_row_rating(row, columns) for row in rows]
    return _mean(report_values), sum(value is not None for value in report_values)


def _rows_hours(rows: Sequence[CourseRow]) -> tuple[float | None, int]:
    total_weighted_hours = 0.0
    total_histogram_mass = 0.0
    usable_reports = 0
    for row in rows:
        weighted_hours = 0.0
        histogram_mass = 0.0
        for column, weight in zip(HOUR_COLUMNS, HOUR_WEIGHTS):
            value = _finite_float(row[column])
            if value is not None and value >= 0:
                weighted_hours += value * weight
                histogram_mass += value
        if histogram_mass > 0:
            total_weighted_hours += weighted_hours
            total_histogram_mass += histogram_mass
            usable_reports += 1
    if total_histogram_mass == 0:
        return None, 0
    return total_weighted_hours / total_histogram_mass, usable_reports


def _response_summary(rows: Sequence[CourseRow]) -> tuple[int | None, int]:
    values = []
    for row in rows:
        value = row["response_count"]
        if isinstance(value, int) and value >= 0:
            values.append(value)
    return (sum(values), len(values)) if values else (None, 0)


def _latest_quarter(rows: Sequence[CourseRow]) -> str | None:
    season_order = {"Winter": 1, "Spring": 2, "Summer": 3, "Autumn": 4}
    candidates: list[tuple[int, int, str]] = []
    for row in rows:
        quarter = row["quarter"]
        if not isinstance(quarter, str):
            continue
        match = re.fullmatch(r"(Winter|Spring|Summer|Autumn)\s+(\d{4})", quarter.strip())
        if match:
            candidates.append((int(match.group(2)), season_order[match.group(1)], quarter.strip()))
    return max(candidates)[2] if candidates else None


def _validate_payload(payload: object) -> list[ValidatedItem]:
    if not isinstance(payload, list):
        raise ValidationError("JSON body must be an array")
    if len(payload) > MAX_BATCH_SIZE:
        raise ValidationError(f"at most {MAX_BATCH_SIZE} courses may be requested")

    validated: list[ValidatedItem] = []
    total_course_references = 0
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValidationError(f"item {index} must be an object")

        course_id = item.get("courseId")
        if not isinstance(course_id, str) or len(course_id) > MAX_COURSE_ID_LENGTH:
            raise ValidationError(
                f"item {index}.courseId must be a string of at most {MAX_COURSE_ID_LENGTH} characters"
            )

        instructor = item.get("instructor", "")
        if instructor is None:
            instructor = ""
        if not isinstance(instructor, str) or len(instructor) > MAX_INSTRUCTOR_LENGTH:
            raise ValidationError(
                f"item {index}.instructor must be a string of at most {MAX_INSTRUCTOR_LENGTH} characters"
            )

        other_listings = item.get("otherListings", [])
        if other_listings is None:
            other_listings = []
        if not isinstance(other_listings, list) or len(other_listings) > MAX_OTHER_LISTINGS:
            raise ValidationError(
                f"item {index}.otherListings must be an array with at most {MAX_OTHER_LISTINGS} entries"
            )
        for listing_index, listing in enumerate(other_listings):
            if not isinstance(listing, str) or len(listing) > MAX_COURSE_ID_LENGTH:
                raise ValidationError(
                    f"item {index}.otherListings[{listing_index}] must be a string of at most "
                    f"{MAX_COURSE_ID_LENGTH} characters"
                )

        total_course_references += 1 + len(other_listings)
        if total_course_references > MAX_TOTAL_COURSE_REFERENCES:
            raise ValidationError(
                f"at most {MAX_TOTAL_COURSE_REFERENCES} total course listings may be requested"
            )

        validated.append(
            ValidatedItem(
                course_id=course_id,
                instructor=instructor,
                other_listings=tuple(other_listings),
            )
        )
    return validated


class FeedbackRepository:
    """Read-only aggregate queries scoped to one request connection."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self._course_url_cache: dict[CourseKey, frozenset[str]] = {}
        self._canonical_row_cache: dict[str, dict[str, object]] = {}
        self._relevant_professor_cache: dict[tuple[CourseKey, ...], tuple[sqlite3.Row, ...]] = {}
        self._professors_by_course: dict[CourseKey, tuple[sqlite3.Row, ...]] = {}
        self._department_professor_cache: dict[tuple[str, ...], tuple[sqlite3.Row, ...]] = {}
        self._professor_url_cache: dict[tuple[int, ...], frozenset[str]] = {}
        self._professor_course_url_cache: dict[
            tuple[tuple[int, ...], tuple[CourseKey, ...]], frozenset[str]
        ] = {}

    def prefetch_courses(self, keys: Iterable[CourseKey]) -> None:
        """Populate course/report caches in bounded bulk queries for a batch."""

        missing_keys = sorted(
            set(keys).difference(self._course_url_cache),
            key=lambda key: (key.dept, key.number),
        )
        collected: dict[CourseKey, set[str]] = {key: set() for key in missing_keys}
        # Two parameters per key; 200 stays safely below common SQLite limits.
        for offset in range(0, len(missing_keys), 200):
            chunk = missing_keys[offset : offset + 200]
            conditions = " OR ".join("(dept = ? AND course_id = ?)" for _ in chunk)
            parameters = tuple(
                value
                for key in chunk
                for value in (key.dept, key.number)
            )
            rows = self.connection.execute(
                f"SELECT dept, course_id, url FROM courses "
                f"WHERE url IS NOT NULL AND ({conditions})",
                parameters,
            ).fetchall()
            for row in rows:
                collected[CourseKey(row["dept"], row["course_id"])].add(row["url"])
        for key, urls in collected.items():
            self._course_url_cache[key] = frozenset(urls)

        all_urls = {url for urls in collected.values() for url in urls}
        self.canonical_rows(all_urls)

    def course_urls(self, key: CourseKey) -> frozenset[str]:
        if key not in self._course_url_cache:
            rows = self.connection.execute(
                "SELECT DISTINCT url FROM courses WHERE dept = ? AND course_id = ? AND url IS NOT NULL",
                (key.dept, key.number),
            ).fetchall()
            self._course_url_cache[key] = frozenset(row["url"] for row in rows if row["url"])
        return self._course_url_cache[key]

    def canonical_rows(self, urls: Iterable[str]) -> list[dict[str, object]]:
        requested = set(urls)
        missing = sorted(requested.difference(self._canonical_row_cache))
        for offset in range(0, len(missing), 500):
            chunk = missing[offset : offset + 500]
            placeholders = ",".join("?" for _ in chunk)
            rows = self.connection.execute(
                f"SELECT {', '.join(SELECTED_COURSE_COLUMNS)} "
                f"FROM courses WHERE url IN ({placeholders}) ORDER BY id",
                chunk,
            ).fetchall()
            by_url: dict[str, list[sqlite3.Row]] = {}
            for row in rows:
                by_url.setdefault(row["url"], []).append(row)
            for url, duplicate_rows in by_url.items():
                self._canonical_row_cache[url] = _merge_duplicate_report_rows(duplicate_rows)
        return [self._canonical_row_cache[url] for url in sorted(requested) if url in self._canonical_row_cache]

    def relevant_professors(self, keys: Sequence[CourseKey]) -> list[sqlite3.Row]:
        cache_key = tuple(keys)
        if cache_key in self._relevant_professor_cache:
            return list(self._relevant_professor_cache[cache_key])
        self.prefetch_relevant_professors(keys)
        result: dict[int, sqlite3.Row] = {}
        for key in cache_key:
            rows = self._professors_by_course[key]
            result.update({row["id"]: row for row in rows})
        resolved = tuple(result.values())
        self._relevant_professor_cache[cache_key] = resolved
        return list(resolved)

    def prefetch_relevant_professors(self, keys: Iterable[CourseKey]) -> None:
        missing_keys = sorted(
            set(keys).difference(self._professors_by_course),
            key=lambda key: (key.dept, key.number),
        )
        collected: dict[CourseKey, dict[int, sqlite3.Row]] = {
            key: {} for key in missing_keys
        }
        for offset in range(0, len(missing_keys), 150):
            chunk = missing_keys[offset : offset + 150]
            conditions = " OR ".join("(c.dept = ? AND c.course_id = ?)" for _ in chunk)
            parameters = tuple(
                value
                for key in chunk
                for value in (key.dept, key.number)
            )
            rows = self.connection.execute(
                f"""
                SELECT DISTINCT c.dept AS course_dept, c.course_id AS course_number,
                                p.id, p.dept, p.first_name, p.last_name
                FROM professors AS p
                JOIN courses_professors AS cp ON cp.professor_id = p.id
                JOIN courses AS c ON c.id = cp.course_id
                WHERE {conditions}
                """,
                parameters,
            ).fetchall()
            for row in rows:
                key = CourseKey(row["course_dept"], row["course_number"])
                collected[key][row["id"]] = row
        for key, rows_by_id in collected.items():
            self._professors_by_course[key] = tuple(rows_by_id.values())

    def department_professors(self, departments: Sequence[str]) -> list[sqlite3.Row]:
        unique_departments = tuple(sorted(set(departments)))
        if not unique_departments:
            return []
        if unique_departments in self._department_professor_cache:
            return list(self._department_professor_cache[unique_departments])
        placeholders = ",".join("?" for _ in unique_departments)
        resolved = tuple(self.connection.execute(
            f"SELECT id, dept, first_name, last_name FROM professors WHERE dept IN ({placeholders})",
            unique_departments,
        ).fetchall())
        self._department_professor_cache[unique_departments] = resolved
        return list(resolved)

    def professor_urls(self, professor_ids: Sequence[int]) -> frozenset[str]:
        cache_key = tuple(sorted(set(professor_ids)))
        if not cache_key:
            return frozenset()
        if cache_key in self._professor_url_cache:
            return self._professor_url_cache[cache_key]
        placeholders = ",".join("?" for _ in cache_key)
        rows = self.connection.execute(
            f"""
            SELECT DISTINCT c.url
            FROM courses_professors AS cp
            JOIN courses AS c ON c.id = cp.course_id
            WHERE cp.professor_id IN ({placeholders}) AND c.url IS NOT NULL
            """,
            cache_key,
        ).fetchall()
        urls = frozenset(row["url"] for row in rows if row["url"])
        self._professor_url_cache[cache_key] = urls
        return urls

    def professor_course_urls(
        self, professor_ids: Sequence[int], keys: Sequence[CourseKey]
    ) -> frozenset[str]:
        id_key = tuple(sorted(set(professor_ids)))
        course_key = tuple(keys)
        if not id_key or not course_key:
            return frozenset()
        cache_key = (id_key, course_key)
        if cache_key in self._professor_course_url_cache:
            return self._professor_course_url_cache[cache_key]
        urls: set[str] = set()
        professor_placeholders = ",".join("?" for _ in id_key)
        for key in course_key:
            rows = self.connection.execute(
                f"""
                SELECT DISTINCT c.url
                FROM courses_professors AS cp
                JOIN courses AS c ON c.id = cp.course_id
                WHERE cp.professor_id IN ({professor_placeholders})
                  AND c.dept = ? AND c.course_id = ? AND c.url IS NOT NULL
                """,
                (*id_key, key.dept, key.number),
            ).fetchall()
            urls.update(row["url"] for row in rows if row["url"])
        resolved = frozenset(urls)
        self._professor_course_url_cache[cache_key] = resolved
        return resolved


def _identity_groups(rows: Sequence[sqlite3.Row]) -> dict[int, list[sqlite3.Row]]:
    """Group duplicate query rows by stable professor ID, never by a name."""

    grouped: dict[int, list[sqlite3.Row]] = {}
    for row in rows:
        grouped.setdefault(int(row["id"]), []).append(row)
    return grouped


def _match_full_name(token: str, rows: Sequence[sqlite3.Row]) -> list[list[sqlite3.Row]]:
    normalized = _normalize_name(token)
    matches = []
    for identity_rows in _identity_groups(rows).values():
        first = _normalize_name(identity_rows[0]["first_name"] or "")
        last = _normalize_name(identity_rows[0]["last_name"] or "")
        forms = {
            _normalize_name(f"{first} {last}"),
            _normalize_name(f"{last}, {first}"),
            _normalize_name(f"{last} {first}"),
        }
        if normalized in forms:
            matches.append(identity_rows)
    return matches


def _match_surname(token: str, rows: Sequence[sqlite3.Row]) -> list[list[sqlite3.Row]]:
    normalized = _normalize_name(token)
    return [
        identity_rows
        for identity_rows in _identity_groups(rows).values()
        if normalized == _normalize_name(identity_rows[0]["last_name"] or "")
    ]


def _as_identity(rows: Sequence[sqlite3.Row]) -> InstructorIdentity:
    first = (rows[0]["first_name"] or "").strip()
    last = (rows[0]["last_name"] or "").strip()
    return InstructorIdentity(
        label=" ".join(part for part in (first, last) if part),
        professor_ids=tuple(sorted({int(row["id"]) for row in rows})),
    )


def _resolve_token(
    token: str,
    relevant_rows: Sequence[sqlite3.Row],
    department_rows: Sequence[sqlite3.Row],
) -> InstructorResolution:
    normalized = _normalize_name(token)
    if normalized in UNASSIGNED_INSTRUCTORS:
        return InstructorResolution("staff")

    full_matches = _match_full_name(token, relevant_rows)
    if len(full_matches) == 1:
        return InstructorResolution(
            "resolved", (_as_identity(full_matches[0]),), "course_scoped_full_name"
        )
    if len(full_matches) > 1:
        return InstructorResolution("ambiguous")

    surname_matches = _match_surname(token, relevant_rows)
    if surname_matches:
        # The legacy page may expose only a surname. Even when historical
        # evidence for this course contains one matching ID, a new instructor
        # with the same surname would be silently misattributed. Never turn a
        # surname-only value into a professor join.
        return InstructorResolution("surname_only", basis="unresolved_surname_only")

    # A full name may be resolved exactly within one of the requested
    # departments even when this course has no historical instructor link.
    # Deliberately do not fall back to a department-wide or global surname.
    full_department_matches = _match_full_name(token, department_rows)
    if len(full_department_matches) == 1:
        return InstructorResolution(
            "resolved", (_as_identity(full_department_matches[0]),), "department_scoped_full_name"
        )
    if len(full_department_matches) > 1:
        return InstructorResolution("ambiguous")
    return InstructorResolution("not_found")


def _split_instructor_field(value: str) -> list[str]:
    return [
        piece.strip()
        for piece in re.split(r"\s*(?:;|&|\band\b)\s*", value, flags=re.IGNORECASE)
        if piece.strip()
    ]


def resolve_instructors(
    value: str,
    relevant_rows: Sequence[sqlite3.Row],
    department_rows: Sequence[sqlite3.Row],
) -> InstructorResolution:
    if _normalize_name(value) in UNASSIGNED_INSTRUCTORS:
        return InstructorResolution("staff")

    # Treat the whole field as one name first so "Last, First" remains valid.
    whole = _resolve_token(value, relevant_rows, department_rows)
    if whole.status == "resolved":
        return whole

    pieces = _split_instructor_field(value)
    if len(pieces) == 1 and "," in value:
        pieces = [piece.strip() for piece in value.split(",") if piece.strip()]
    if len(pieces) < 2:
        return whole

    resolutions = [_resolve_token(piece, relevant_rows, department_rows) for piece in pieces]
    identities: dict[tuple[int, ...], InstructorIdentity] = {}
    for resolution in resolutions:
        for identity in resolution.identities:
            identities[identity.professor_ids] = identity

    if identities:
        status = "resolved" if all(item.status == "resolved" for item in resolutions) else "partially_resolved"
        bases = sorted({item.basis for item in resolutions if item.basis})
        basis = "+".join(bases) if bases else None
        return InstructorResolution(status, tuple(identities.values()), basis)
    if any(item.status == "ambiguous" for item in resolutions):
        return InstructorResolution("ambiguous")
    if any(item.status == "surname_only" for item in resolutions):
        return InstructorResolution("surname_only", basis="unresolved_surname_only")
    if all(item.status == "staff" for item in resolutions):
        return InstructorResolution("staff")
    return InstructorResolution("not_found")


def _sample_size(rows: Sequence[CourseRow], rating_columns: Sequence[str]) -> dict[str, int | None]:
    _rating, rating_reports = _rows_rating(rows, rating_columns)
    _hours, hours_reports = _rows_hours(rows)
    responses, reports_with_responses = _response_summary(rows)
    return {
        "reports": len(rows),
        "rating_reports": rating_reports,
        "hours_reports": hours_reports,
        "known_responses": responses,
        "reports_with_response_counts": reports_with_responses,
    }


def _null_response(item: ValidatedItem, match_status: str) -> dict[str, object]:
    return {
        "courseId": item.course_id,
        "course_rating": None,
        "professor_rating": None,
        "professor_course_rating": None,
        "course_hours": None,
        "professor_course_hours": None,
        "feedback_urls": None,
        "course_report_count": 0,
        "professor_report_count": 0,
        "professor_course_report_count": 0,
        "sample_sizes": {
            "course": _sample_size([], COURSE_RATING_COLUMNS),
            "professor": _sample_size([], PROFESSOR_RATING_COLUMNS),
            "professor_course": _sample_size([], PROFESSOR_COURSE_RATING_COLUMNS),
        },
        "provenance": {
            "methodology": "public-api-v2",
            "source": "aggregate_course_feedback_database",
            "deduplicated_by": "report_url",
            "course_match": match_status,
            "matched_course_id": None,
            "professor_match": "not_evaluated",
            "professor_match_basis": None,
            "matched_professors": [],
            "course_data_through": None,
        },
    }


def build_feedback(item: ValidatedItem, repository: FeedbackRepository) -> dict[str, object]:
    main_key = parse_course_id(item.course_id)
    if main_key is None:
        return _null_response(item, "invalid_format")

    keys: list[CourseKey] = [main_key]
    for listing in item.other_listings:
        key = parse_course_id(listing)
        if key is not None and key not in keys:
            keys.append(key)

    chosen_key = main_key
    chosen_rows: list[sqlite3.Row] = []
    fallback_rows: list[sqlite3.Row] = []
    for key in keys:
        rows = repository.canonical_rows(repository.course_urls(key))
        if rows and not fallback_rows:
            fallback_rows = rows
            chosen_key = key
        rating, _ = _rows_rating(rows, COURSE_RATING_COLUMNS)
        if rating is not None:
            chosen_key = key
            chosen_rows = rows
            break
    if not chosen_rows:
        chosen_rows = fallback_rows

    course_rating, _ = _rows_rating(chosen_rows, COURSE_RATING_COLUMNS)
    course_hours, _ = _rows_hours(chosen_rows)

    if _normalize_name(item.instructor) in UNASSIGNED_INSTRUCTORS:
        resolution = InstructorResolution("staff")
    else:
        relevant_professors = repository.relevant_professors(keys)
        department_professors = repository.department_professors([key.dept for key in keys])
        resolution = resolve_instructors(
            item.instructor, relevant_professors, department_professors
        )

    all_professor_urls: set[str] = set()
    all_professor_course_urls: set[str] = set()

    # Never present a subset as the rating for a multi-instructor field. If any
    # named instructor is unresolved, all legacy professor metrics stay null.
    if resolution.status == "resolved":
        for identity in resolution.identities:
            all_professor_urls.update(repository.professor_urls(identity.professor_ids))
            all_professor_course_urls.update(
                repository.professor_course_urls(identity.professor_ids, keys)
            )

    professor_rows = repository.canonical_rows(all_professor_urls)
    professor_course_rows = repository.canonical_rows(all_professor_course_urls)
    # Metrics and sample counts share the same report-URL-deduplicated union,
    # so the reported N is the actual denominator at the report level.
    professor_rating = _rows_rating(professor_rows, PROFESSOR_RATING_COLUMNS)[0]
    professor_course_rating = _rows_rating(
        professor_course_rows, PROFESSOR_COURSE_RATING_COLUMNS
    )[0]
    professor_course_hours = _rows_hours(professor_course_rows)[0]

    course_sample = _sample_size(chosen_rows, COURSE_RATING_COLUMNS)
    professor_sample = _sample_size(professor_rows, PROFESSOR_RATING_COLUMNS)
    professor_course_sample = _sample_size(
        professor_course_rows, PROFESSOR_COURSE_RATING_COLUMNS
    )

    feedback_url = "https://coursefeedback.uchicago.edu/?" + urlencode(
        {"CourseDepartment": main_key.dept, "CourseNumber": main_key.number}
    )
    has_course_evidence = bool(chosen_rows)
    response_course_id = chosen_key.label if has_course_evidence else main_key.label

    return {
        # Legacy fields consumed by courseFeedbackLaunch/courseScrape.js.
        "courseId": response_course_id,
        "course_rating": course_rating,
        "professor_rating": professor_rating,
        "professor_course_rating": professor_course_rating,
        "course_hours": course_hours,
        "professor_course_hours": professor_course_hours,
        "feedback_urls": feedback_url,
        # Additive fields: old clients ignore these, while new clients can show N.
        "course_report_count": course_sample["reports"],
        "professor_report_count": professor_sample["reports"],
        "professor_course_report_count": professor_course_sample["reports"],
        "sample_sizes": {
            "course": course_sample,
            "professor": professor_sample,
            "professor_course": professor_course_sample,
        },
        "provenance": {
            "methodology": "public-api-v2",
            "source": "aggregate_course_feedback_database",
            "deduplicated_by": "report_url",
            "course_match": "matched" if has_course_evidence else "not_in_coverage",
            "matched_course_id": chosen_key.label if has_course_evidence else None,
            "professor_match": resolution.status,
            "professor_match_basis": resolution.basis,
            "matched_professors": [identity.label for identity in resolution.identities],
            "course_data_through": _latest_quarter(chosen_rows),
        },
    }


def _release_mode_enabled() -> bool:
    raw_value = os.environ.get(RELEASE_MODE_ENV)
    if raw_value is None:
        return False
    value = raw_value.strip().casefold()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ReleaseConfigurationError(
        f"{RELEASE_MODE_ENV} must be one of 1/true/yes/on or 0/false/no/off"
    )


def _validated_release_artifact() -> tuple[Path, IntegrityReport]:
    raw_database_path = os.environ.get(DB_PATH_ENV)
    if raw_database_path is None or not raw_database_path.strip():
        raise ReleaseConfigurationError(
            f"release startup requires an explicit absolute {DB_PATH_ENV}"
        )
    configured_path = Path(raw_database_path)
    if not configured_path.is_absolute():
        raise ReleaseConfigurationError(f"{DB_PATH_ENV} must be an absolute path")
    try:
        database_path = configured_path.resolve(strict=True)
    except OSError as error:
        raise ReleaseConfigurationError(f"configured database is unavailable: {error}") from error
    if not database_path.is_file():
        raise ReleaseConfigurationError("configured database path is not a regular file")

    raw_manifest_path = os.environ.get(MANIFEST_ENV)
    if raw_manifest_path is None or not raw_manifest_path.strip():
        raise ReleaseConfigurationError(
            f"release startup requires an explicit absolute {MANIFEST_ENV}"
        )
    configured_manifest = Path(raw_manifest_path)
    if not configured_manifest.is_absolute():
        raise ReleaseConfigurationError(f"{MANIFEST_ENV} must be an absolute path")
    try:
        manifest_path = configured_manifest.resolve(strict=True)
    except OSError as error:
        raise ReleaseConfigurationError(f"configured manifest is unavailable: {error}") from error
    if not manifest_path.is_file():
        raise ReleaseConfigurationError("configured manifest path is not a regular file")

    try:
        report = inspect_release_data(database_path, manifest_path)
    except (OSError, sqlite3.Error, ValueError) as error:
        raise ReleaseConfigurationError(f"release integrity check failed: {error}") from error
    if not report.ready:
        failures = (*report.integrity_errors, *report.manifest_errors)
        raise ReleaseConfigurationError(
            "release artifact rejected: " + "; ".join(failures)
        )
    return database_path, report


def _build_app(
    database_path: str | os.PathLike[str],
    release_report: IntegrityReport | None = None,
) -> Flask:
    app = Flask(__name__)
    app.config.update(
        MAX_CONTENT_LENGTH=MAX_REQUEST_BYTES,
        FEEDBACK_DATABASE_PATH=str(configured_database_path(database_path)),
        JSON_SORT_KEYS=False,
        RELEASE_INTEGRITY_REPORT=release_report.as_json() if release_report else None,
    )

    @app.after_request
    def add_cors_headers(response):
        # Required by the existing extension's cross-origin fetch.
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return response

    @app.errorhandler(RequestEntityTooLarge)
    def payload_too_large(_error):
        return jsonify(error=f"request body exceeds {MAX_REQUEST_BYTES} bytes"), 413

    @app.get("/")
    def home():
        return "The Flask app is working!"

    @app.post("/get-course-feedback")
    def get_course_feedback():
        if not request.is_json:
            return jsonify(error="Content-Type must be application/json"), 415
        try:
            payload = request.get_json()
        except BadRequest:
            return jsonify(error="malformed JSON body"), 400

        try:
            items = _validate_payload(payload)
        except ValidationError as error:
            return jsonify(error=str(error)), 400

        try:
            with connect_read_only(app.config["FEEDBACK_DATABASE_PATH"]) as connection:
                repository = FeedbackRepository(connection)
                requested_keys = []
                for item in items:
                    for course_id in (item.course_id, *item.other_listings):
                        key = parse_course_id(course_id)
                        if key is not None:
                            requested_keys.append(key)
                repository.prefetch_courses(requested_keys)
                professor_lookup_keys = []
                for item in items:
                    if _normalize_name(item.instructor) in UNASSIGNED_INSTRUCTORS:
                        continue
                    for course_id in (item.course_id, *item.other_listings):
                        key = parse_course_id(course_id)
                        if key is not None:
                            professor_lookup_keys.append(key)
                repository.prefetch_relevant_professors(professor_lookup_keys)
                results = [build_feedback(item, repository) for item in items]
        except ConflictingReportEvidence:
            app.logger.exception("Feedback report copies contain conflicting evidence")
            return jsonify(error="feedback data failed integrity checks"), 503
        except (OSError, sqlite3.Error):
            app.logger.exception("Feedback database unavailable")
            return jsonify(error="feedback database unavailable"), 503
        return jsonify(results), 200

    return app


def create_release_app() -> Flask:
    """Create a production app only after validating an explicit artifact+manifest."""

    database_path, report = _validated_release_artifact()
    return _build_app(database_path, report)


def create_app(database_path: str | os.PathLike[str] | None = None) -> Flask:
    """Create the local/test app, or enforce the release guard when flagged."""

    if _release_mode_enabled():
        release_path, report = _validated_release_artifact()
        if database_path is not None and configured_database_path(database_path) != release_path:
            raise ReleaseConfigurationError(
                "release-mode factory argument does not match the explicit database environment path"
            )
        return _build_app(release_path, report)
    return _build_app(configured_database_path(database_path))


if __name__ == "__main__":
    create_app().run()
