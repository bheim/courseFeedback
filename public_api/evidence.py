"""Shared report-evidence definitions and fail-closed duplicate merging."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence


COURSE_RATING_COLUMNS = (
    "challenge_intellect",
    "purpose",
    "standards",
    "feedback",
    "fairness",
    "respect",
    "excellence",
)
PROFESSOR_RATING_COLUMNS = (
    "organization",
    "challenge",
    "available",
    "inclusive",
    "significant",
)
PROFESSOR_COURSE_RATING_COLUMNS = COURSE_RATING_COLUMNS + PROFESSOR_RATING_COLUMNS
HOUR_COLUMNS = (
    "less_five",
    "five_to_ten",
    "ten_to_fifteen",
    "fifteen_to_twenty",
    "twenty_to_twenty_five",
    "twenty_five_to_thirty",
    "more_thirty",
)
HOUR_WEIGHTS = (2.5, 7.5, 12.5, 17.5, 22.5, 27.5, 32.5)

# These are the source fields the API needs from one logical evaluation report.
SELECTED_COURSE_COLUMNS = (
    "id",
    "dept",
    "course_id",
    "quarter",
    "url",
    "response_count",
) + COURSE_RATING_COLUMNS + PROFESSOR_RATING_COLUMNS + HOUR_COLUMNS

# A duplicate URL may fill a null left by another copy, but two different
# populated values make the logical report disputed. ID is intentionally omitted
# because physical duplicate rows necessarily have different IDs.
DUPLICATE_CONFLICT_COLUMNS = SELECTED_COURSE_COLUMNS[1:]

CourseRow = Mapping[str, object]


class ConflictingReportEvidence(RuntimeError):
    """Raised when copies of one report URL contain incompatible evidence."""

    def __init__(self, report_url: str, fields: Sequence[str]):
        self.report_url = report_url
        self.fields = tuple(fields)
        super().__init__(
            f"conflicting non-null evidence for report URL in fields: {', '.join(self.fields)}"
        )


def _values_equal(left: object, right: object) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        left_number = float(left)
        right_number = float(right)
        if math.isnan(left_number) or math.isnan(right_number):
            return False
        return left_number == right_number
    return type(left) is type(right) and left == right


def conflicting_non_null_fields(
    rows: Sequence[CourseRow],
    columns: Sequence[str] = DUPLICATE_CONFLICT_COLUMNS,
) -> tuple[str, ...]:
    """Return fields having two unequal non-null values across report copies."""

    conflicts: list[str] = []
    for column in columns:
        values = [row[column] for row in rows if row[column] is not None]
        if values and any(not _values_equal(values[0], value) for value in values[1:]):
            conflicts.append(column)
    return tuple(conflicts)


def merge_duplicate_report_rows(rows: Sequence[CourseRow]) -> dict[str, object]:
    """Merge complementary copies deterministically and reject disputed evidence.

    Physical rows are ordered by ID. Each field uses its first non-null value;
    because conflicts are rejected first, the choice cannot alter the evidence.
    """

    if not rows:
        raise ValueError("at least one report row is required")
    urls = {str(row["url"]) for row in rows if row["url"] is not None}
    report_url = min(urls) if urls else "<missing>"
    conflicts = conflicting_non_null_fields(rows)
    if conflicts:
        raise ConflictingReportEvidence(report_url, conflicts)

    ranked = sorted(rows, key=lambda row: int(row["id"]))
    merged: dict[str, object] = {}
    for column in SELECTED_COURSE_COLUMNS:
        merged[column] = next(
            (row[column] for row in ranked if row[column] is not None),
            None,
        )
    return merged
