"""Integration tests for the hardened public extension API.

These tests intentionally use only the checked-in aggregate database and open it
read-only.  They never inspect credentials or the raw-comments database.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from public_api.app import (
    COURSE_RATING_COLUMNS,
    DB_PATH_ENV,
    DEFAULT_DB_PATH,
    MAX_BATCH_SIZE,
    MAX_COURSE_ID_LENGTH,
    MAX_INSTRUCTOR_LENGTH,
    MAX_OTHER_LISTINGS,
    MAX_REQUEST_BYTES,
    MAX_TOTAL_COURSE_REFERENCES,
    PROFESSOR_RATING_COLUMNS,
    RELEASE_MODE_ENV,
    SELECTED_COURSE_COLUMNS,
    ConflictingReportEvidence,
    FeedbackRepository,
    ReleaseConfigurationError,
    _merge_duplicate_report_rows,
    _rows_rating,
    connect_read_only,
    create_app,
    create_release_app,
)
from public_api.check_release_data import MANIFEST_ENV, expected_manifest, inspect_release_data


LEGACY_FIELDS = {
    "courseId",
    "course_rating",
    "professor_rating",
    "professor_course_rating",
    "course_hours",
    "professor_course_hours",
    "feedback_urls",
}


def _create_normalized_test_database(path: Path) -> None:
    """Create a minimal aggregate-only artifact that satisfies the release gate."""

    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dept TEXT,
                quarter TEXT,
                course_id INTEGER,
                challenge_intellect REAL,
                purpose REAL,
                standards REAL,
                feedback REAL,
                fairness REAL,
                respect REAL,
                excellence REAL,
                organization REAL,
                challenge REAL,
                available REAL,
                inclusive REAL,
                significant REAL,
                less_five REAL,
                five_to_ten REAL,
                ten_to_fifteen REAL,
                fifteen_to_twenty REAL,
                twenty_to_twenty_five REAL,
                twenty_five_to_thirty REAL,
                more_thirty REAL,
                url TEXT,
                avg_course_hours REAL,
                avg_course_rating REAL,
                interest_before REAL,
                interest_after REAL,
                response_count INTEGER
            );
            CREATE TABLE professors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dept TEXT,
                first_name TEXT,
                last_name TEXT,
                avg_professor_rating REAL
            );
            CREATE TABLE courses_professors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id INTEGER,
                professor_id INTEGER,
                avg_prof_course_hours REAL,
                avg_prof_course_rating REAL,
                FOREIGN KEY (course_id) REFERENCES courses(id),
                FOREIGN KEY (professor_id) REFERENCES professors(id)
            );
            INSERT INTO courses (
                id, dept, quarter, course_id, challenge_intellect, purpose,
                standards, feedback, fairness, respect, excellence,
                organization, challenge, available, inclusive, significant,
                less_five, five_to_ten, url, response_count
            ) VALUES (
                1, 'TEST', 'Autumn 2026', 10000, 4.5, 4.4,
                4.3, 4.2, 4.1, 4.0, 3.9,
                4.6, 4.5, 4.4, 4.3, 4.2,
                25.0, 75.0, 'https://example.invalid/report/clean', 20
            );
            INSERT INTO professors (id, dept, first_name, last_name)
            VALUES (1, 'TEST', 'Ada', 'Lovelace');
            INSERT INTO courses_professors (id, course_id, professor_id)
            VALUES (1, 1, 1);
            """
        )
        connection.commit()
    finally:
        connection.close()


def _write_manifest(database_path: Path, manifest_path: Path) -> None:
    manifest = expected_manifest(inspect_release_data(database_path))
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")


class PublicApiV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_path = Path(DEFAULT_DB_PATH)
        if not cls.database_path.is_file():
            raise unittest.SkipTest(f"aggregate database missing: {cls.database_path}")
        cls.app = create_app(cls.database_path)
        cls.app.config.update(TESTING=True)
        cls.client = cls.app.test_client()

    def post(self, payload):
        return self.client.post("/get-course-feedback", json=payload)

    def test_sanitized_launch_payload_contract_fixture(self):
        fixture_path = Path(__file__).parent / "fixtures" / "public_api_v2_contract_cases.json"
        cases = json.loads(fixture_path.read_text(encoding="utf-8"))
        response = self.post([case["request"] for case in cases])
        self.assertEqual(response.status_code, 200)
        results = response.get_json()
        self.assertEqual(len(results), len(cases))
        for case, item in zip(cases, results):
            with self.subTest(case=case["name"]):
                expected = case["expected"]
                self.assertTrue(LEGACY_FIELDS.issubset(item))
                self.assertEqual(item["courseId"], expected["courseId"])
                self.assertEqual(item["provenance"]["course_match"], expected["course_match"])
                self.assertEqual(
                    item["provenance"]["professor_match"], expected["professor_match"]
                )
                self.assertEqual(item["course_rating"] is not None, expected["course_metrics"])
                self.assertEqual(
                    item["professor_rating"] is not None, expected["professor_metrics"]
                )

    def test_health_route_preserves_legacy_contract_and_cors(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_data(as_text=True), "The Flask app is working!")
        self.assertEqual(response.headers["Access-Control-Allow-Origin"], "*")

    def test_cors_preflight_supports_legacy_cross_origin_post(self):
        response = self.client.options(
            "/get-course-feedback",
            headers={
                "Origin": "https://coursesearch92.uchicago.edu",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Access-Control-Allow-Origin"], "*")
        self.assertIn("POST", response.headers["Access-Control-Allow-Methods"])
        self.assertIn("Content-Type", response.headers["Access-Control-Allow-Headers"])

    def test_known_course_preserves_fields_and_adds_deduplicated_sample_sizes(self):
        response = self.post(
            [
                {
                    "courseTitle": "Introduction to Ethics",
                    "courseId": "PHIL 21000",
                    "instructor": "Benjamin Callard",
                    "otherListings": [],
                }
            ]
        )
        self.assertEqual(response.status_code, 200)
        item = response.get_json()[0]
        self.assertTrue(LEGACY_FIELDS.issubset(item))
        self.assertIsNotNone(item["course_rating"])
        self.assertIsNotNone(item["course_hours"])
        self.assertEqual(item["provenance"]["deduplicated_by"], "report_url")
        self.assertEqual(item["provenance"]["professor_match"], "resolved")
        self.assertEqual(
            item["provenance"]["professor_match_basis"], "course_scoped_full_name"
        )

        with connect_read_only(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS rows, COUNT(DISTINCT url) AS reports
                FROM courses WHERE dept = 'PHIL' AND course_id = 21000
                """
            ).fetchone()
        self.assertGreater(row["rows"], row["reports"], "fixture should exercise URL deduplication")
        self.assertEqual(item["course_report_count"], row["reports"])
        self.assertEqual(item["sample_sizes"]["course"]["reports"], row["reports"])

    def test_legacy_surname_input_is_never_guessed_from_course_evidence(self):
        response = self.post(
            [{"courseId": "PHIL 25000", "instructor": "Brooks", "otherListings": []}]
        )
        item = response.get_json()[0]
        self.assertEqual(item["provenance"]["professor_match"], "surname_only")
        self.assertEqual(
            item["provenance"]["professor_match_basis"], "unresolved_surname_only"
        )
        self.assertEqual(item["provenance"]["matched_professors"], [])
        self.assertIsNone(item["professor_rating"])

    def test_course_rating_is_recomputed_from_unique_reports(self):
        response = self.post([{"courseId": "PHIL 21000", "instructor": "Staff"}])
        actual = response.get_json()[0]["course_rating"]

        columns = ", ".join(COURSE_RATING_COLUMNS)
        with connect_read_only(self.database_path) as connection:
            rows = connection.execute(
                f"""
                WITH ranked AS (
                    SELECT *, ROW_NUMBER() OVER (
                        PARTITION BY url
                        ORDER BY (
                            {" + ".join(f"({column} IS NOT NULL)" for column in COURSE_RATING_COLUMNS)}
                        ) DESC, id DESC
                    ) AS rank
                    FROM courses WHERE dept = 'PHIL' AND course_id = 21000
                )
                SELECT {columns} FROM ranked WHERE rank = 1
                """
            ).fetchall()
        section_ratings = []
        for row in rows:
            values = [row[column] for column in COURSE_RATING_COLUMNS if row[column] is not None]
            if values:
                section_ratings.append(sum(values) / len(values))
        expected = sum(section_ratings) / len(section_ratings)
        self.assertAlmostEqual(actual, expected, places=12)

    def test_staff_and_unknown_instructors_keep_course_result_and_null_professor_metrics(self):
        response = self.post(
            [
                {"courseId": "HUMA 11500", "instructor": "Staff", "otherListings": []},
                {"courseId": "PHIL 21000", "instructor": "No Such Faculty Member"},
            ]
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["provenance"]["professor_match"], "staff")
        self.assertEqual(data[1]["provenance"]["professor_match"], "not_found")
        for item in data:
            self.assertIsNotNone(item["course_rating"])
            self.assertIsNone(item["professor_rating"])
            self.assertIsNone(item["professor_course_rating"])
            self.assertIsNone(item["professor_course_hours"])

    def test_surname_is_not_guessed_but_full_name_resolves_by_id(self):
        response = self.post(
            [
                {"courseId": "HUMA 11500", "instructor": "Callard"},
                {"courseId": "HUMA 11500", "instructor": "Benjamin Callard"},
                {"courseId": "HUMA 11500", "instructor": "Callard, Agnes"},
            ]
        )
        self.assertEqual(response.status_code, 200)
        surname_only, benjamin, agnes = response.get_json()
        self.assertEqual(surname_only["provenance"]["professor_match"], "surname_only")
        self.assertIsNone(surname_only["professor_rating"])
        self.assertEqual(benjamin["provenance"]["matched_professors"], ["Benjamin Callard"])
        self.assertEqual(agnes["provenance"]["matched_professors"], ["Agnes Callard"])
        self.assertIsNotNone(benjamin["professor_course_rating"])
        self.assertIsNotNone(agnes["professor_course_rating"])
        self.assertNotEqual(benjamin["professor_course_rating"], agnes["professor_course_rating"])

        # The stored field is pooled by surname, so both Callards have the same
        # forbidden legacy value. The API must instead derive distinct metrics
        # from the resolved professor IDs and unique report URLs.
        with connect_read_only(self.database_path) as connection:
            pooled = connection.execute(
                """
                SELECT avg_professor_rating
                FROM professors
                WHERE dept = 'HUMA' AND first_name = 'Benjamin' AND last_name = 'Callard'
                """
            ).fetchone()[0]
        self.assertNotAlmostEqual(benjamin["professor_rating"], pooled, places=8)
        self.assertNotAlmostEqual(agnes["professor_rating"], pooled, places=8)

    def test_multiple_instructor_separators_are_supported_without_guessing(self):
        response = self.post(
            [{"courseId": "HUMA 11500", "instructor": "Benjamin Callard and Agnes Callard"}]
        )
        item = response.get_json()[0]
        self.assertEqual(item["provenance"]["professor_match"], "resolved")
        self.assertCountEqual(
            item["provenance"]["matched_professors"],
            ["Benjamin Callard", "Agnes Callard"],
        )
        self.assertIsNotNone(item["professor_rating"])

        with connect_read_only(self.database_path) as connection:
            professor_ids = [
                row["id"]
                for row in connection.execute(
                    """
                    SELECT id FROM professors
                    WHERE dept = 'HUMA' AND last_name = 'Callard'
                      AND first_name IN ('Benjamin', 'Agnes')
                    """
                ).fetchall()
            ]
            repository = FeedbackRepository(connection)
            rows = repository.canonical_rows(repository.professor_urls(professor_ids))
            expected, _ = _rows_rating(rows, PROFESSOR_RATING_COLUMNS)
        self.assertAlmostEqual(item["professor_rating"], expected, places=12)
        self.assertEqual(item["professor_report_count"], len(rows))

    def test_partial_multi_instructor_match_returns_null_legacy_professor_metrics(self):
        response = self.post(
            [
                {
                    "courseId": "HUMA 11500",
                    "instructor": "Benjamin Callard, No Such Faculty Member",
                }
            ]
        )
        item = response.get_json()[0]
        self.assertEqual(item["provenance"]["professor_match"], "partially_resolved")
        self.assertEqual(item["provenance"]["matched_professors"], ["Benjamin Callard"])
        self.assertIsNone(item["professor_rating"])
        self.assertIsNone(item["professor_course_rating"])
        self.assertIsNone(item["professor_course_hours"])
        self.assertEqual(item["professor_report_count"], 0)

    def test_duplicate_full_names_under_different_ids_remain_ambiguous(self):
        response = self.post(
            [
                {
                    "courseId": "PBPL 99999",
                    "instructor": "Colm O'Muircheartaigh",
                }
            ]
        )
        item = response.get_json()[0]
        self.assertEqual(item["provenance"]["professor_match"], "ambiguous")
        self.assertIsNone(item["professor_rating"])

    def test_complementary_duplicate_rows_are_merged_per_field(self):
        first = {column: None for column in SELECTED_COURSE_COLUMNS}
        first.update(
            id=1,
            dept="TEST",
            course_id=10000,
            quarter="Autumn 2025",
            url="https://example.invalid/report/one",
            challenge_intellect=4.75,
        )
        second = {column: None for column in SELECTED_COURSE_COLUMNS}
        second.update(
            id=2,
            dept="TEST",
            course_id=10000,
            quarter="Autumn 2025",
            url="https://example.invalid/report/one",
            organization=4.25,
            less_five=25.0,
            five_to_ten=75.0,
        )
        merged = _merge_duplicate_report_rows([first, second])
        reversed_merged = _merge_duplicate_report_rows([second, first])
        self.assertEqual(merged["challenge_intellect"], 4.75)
        self.assertEqual(merged["organization"], 4.25)
        self.assertEqual(merged["less_five"], 25.0)
        self.assertEqual(merged, reversed_merged)

    def test_conflicting_duplicate_report_evidence_fails_closed(self):
        first = {column: None for column in SELECTED_COURSE_COLUMNS}
        first.update(
            id=1,
            dept="TEST",
            course_id=10000,
            quarter="Autumn 2025",
            url="https://example.invalid/report/disputed",
            challenge_intellect=4.75,
        )
        second = dict(first)
        second.update(id=2, challenge_intellect=3.25)

        with self.assertRaises(ConflictingReportEvidence) as context:
            _merge_duplicate_report_rows([first, second])
        self.assertEqual(context.exception.fields, ("challenge_intellect",))
        self.assertNotIn("https://example.invalid", str(context.exception))

    def test_response_has_one_item_per_input_in_original_order(self):
        payload = [
            {"courseId": "NOT A COURSE", "instructor": "Staff"},
            {"courseId": "ZZZZ 99999", "instructor": "Unknown"},
            {"courseId": "HUMA 11500", "instructor": "Staff"},
        ]
        response = self.post(payload)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(len(data), len(payload))
        self.assertEqual([item["courseId"] for item in data], ["NOT A COURSE", "ZZZZ 99999", "HUMA 11500"])
        self.assertEqual(data[0]["provenance"]["course_match"], "invalid_format")
        self.assertEqual(data[1]["provenance"]["course_match"], "not_in_coverage")
        self.assertEqual(data[2]["provenance"]["course_match"], "matched")

    def test_alternate_listing_can_supply_course_evidence(self):
        with connect_read_only(self.database_path) as connection:
            source = connection.execute(
                "SELECT dept, course_id FROM courses GROUP BY dept, course_id HAVING COUNT(*) > 0 LIMIT 1"
            ).fetchone()
        alternate = f"{source['dept']} {source['course_id']:05d}"
        response = self.post(
            [{"courseId": "ZZZZ 99999", "instructor": "Staff", "otherListings": [alternate]}]
        )
        item = response.get_json()[0]
        self.assertEqual(item["courseId"], alternate)
        self.assertEqual(item["provenance"]["matched_course_id"], alternate)
        self.assertGreater(item["course_report_count"], 0)

    def test_rated_alternate_wins_when_primary_has_hours_but_no_rating(self):
        response = self.post(
            [
                {
                    "courseId": "IMMU 31200",
                    "instructor": "Staff",
                    "otherListings": ["ANTH 10100"],
                }
            ]
        )
        item = response.get_json()[0]
        self.assertEqual(item["courseId"], "ANTH 10100")
        self.assertIsNotNone(item["course_rating"])
        self.assertEqual(item["provenance"]["matched_course_id"], "ANTH 10100")

    def test_read_only_connection_rejects_writes(self):
        with connect_read_only(self.database_path) as connection:
            self.assertEqual(connection.execute("PRAGMA query_only").fetchone()[0], 1)
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("CREATE TABLE api_must_not_write (id INTEGER)")

    def test_environment_path_override_is_honored(self):
        with patch.dict(os.environ, {DB_PATH_ENV: str(self.database_path)}):
            app = create_app()
        self.assertEqual(Path(app.config["FEEDBACK_DATABASE_PATH"]), self.database_path.resolve())

    def test_malformed_and_unbounded_requests_are_rejected(self):
        cases = [
            (self.client.post("/get-course-feedback", data="[]"), 415),
            (self.client.post("/get-course-feedback", data="[", content_type="application/json"), 400),
            (self.post({"courseId": "HUMA 11500"}), 400),
            (self.post([{"courseId": 11500}]), 400),
            (self.post([{"courseId": "HUMA 11500", "otherListings": "PHIL 11500"}]), 400),
            (self.post([{"courseId": "HUMA 11500"}] * (MAX_BATCH_SIZE + 1)), 400),
            (
                self.post(
                    [
                        {
                            "courseId": "HUMA 11500",
                            "otherListings": ["PHIL 21000"] * 3,
                        }
                    ]
                    * (MAX_TOTAL_COURSE_REFERENCES // 4 + 1)
                ),
                400,
            ),
            (
                self.client.post(
                    "/get-course-feedback",
                    data=b" " * (MAX_REQUEST_BYTES + 1),
                    content_type="application/json",
                ),
                413,
            ),
        ]
        for response, expected_status in cases:
            with self.subTest(response=response, expected_status=expected_status):
                self.assertEqual(response.status_code, expected_status)
                self.assertIn("error", response.get_json())

    def test_individual_validator_boundaries(self):
        valid = {
            "courseId": "X" * MAX_COURSE_ID_LENGTH,
            "instructor": "X" * MAX_INSTRUCTOR_LENGTH,
            "otherListings": ["X"] * MAX_OTHER_LISTINGS,
        }
        # A maximum-length but unparseable course ID remains an ordered null
        # result; it is bounded input, not a reason to shift response indexes.
        response = self.post([valid])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.get_json()), 1)

        invalid_payloads = [
            [{**valid, "courseId": "X" * (MAX_COURSE_ID_LENGTH + 1)}],
            [{**valid, "instructor": "X" * (MAX_INSTRUCTOR_LENGTH + 1)}],
            [{**valid, "otherListings": ["X"] * (MAX_OTHER_LISTINGS + 1)}],
            [{**valid, "otherListings": [None]}],
            [{**valid, "otherListings": [7]}],
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = self.post(payload)
                self.assertEqual(response.status_code, 400)
                self.assertIn("error", response.get_json())

    def test_empty_batch_is_valid(self):
        response = self.post([])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), [])

    def test_maximum_total_course_reference_workload_is_bounded(self):
        with connect_read_only(self.database_path) as connection:
            rows = connection.execute(
                "SELECT dept, course_id FROM courses GROUP BY dept, course_id LIMIT ?",
                (MAX_TOTAL_COURSE_REFERENCES,),
            ).fetchall()
        if len(rows) < MAX_TOTAL_COURSE_REFERENCES:
            self.skipTest("aggregate fixture has too few distinct courses")
        labels = [f"{row['dept']} {row['course_id']:05d}" for row in rows]
        payload = [
            {
                "courseId": labels[index],
                "instructor": "Staff",
                "otherListings": [labels[index + 250], labels[index + 500]],
            }
            for index in range(250)
        ]
        started = time.monotonic()
        response = self.post(payload)
        elapsed = time.monotonic() - started
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.get_json()), 250)
        # This catches accidental reintroduction of a query per listing (which
        # took more than 30 seconds locally) without imposing a tight benchmark.
        self.assertLess(elapsed, 10.0)

    def test_missing_database_returns_service_unavailable_without_creating_file(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            missing = Path(temp_directory) / "missing.db"
            app = create_app(missing)
            app.config.update(TESTING=True)
            with self.assertLogs(app.logger, level="ERROR"):
                response = app.test_client().post("/get-course-feedback", json=[])
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.get_json(), {"error": "feedback database unavailable"})
            self.assertFalse(missing.exists())

    def test_release_integrity_gate_exposes_current_dangling_links(self):
        report = inspect_release_data(self.database_path)
        self.assertTrue(report.quick_check_ok)
        self.assertEqual(report.course_rows, 23_641)
        self.assertEqual(report.distinct_report_urls, 19_349)
        self.assertEqual(report.logical_duplicate_report_groups, 2_516)
        self.assertEqual(report.logical_duplicate_report_rows, 4_292)
        self.assertEqual(report.total_links, 36_746)
        self.assertEqual(report.valid_links, 25_609)
        self.assertEqual(report.links_with_any_missing_parent, 11_137)
        self.assertEqual(report.dangling_course_links, 11_137)
        self.assertEqual(report.dangling_professor_links, 0)
        self.assertEqual(report.foreign_key_violations, 11_137)
        self.assertEqual(report.duplicate_physical_link_rows, 0)
        self.assertEqual(report.duplicate_url_professor_pair_rows, 4_700)
        self.assertEqual(report.conflicting_duplicate_report_groups, 0)
        self.assertEqual(report.reports_without_valid_professor_links, 0)
        self.assertFalse(report.ready)

    def test_release_gate_accepts_clean_artifact_and_exact_manifest(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            database_path = Path(temp_directory) / "normalized.db"
            manifest_path = Path(temp_directory) / "artifact-manifest.json"
            _create_normalized_test_database(database_path)

            unmanifested = inspect_release_data(database_path)
            self.assertTrue(unmanifested.ready)
            self.assertEqual(unmanifested.course_rows, 1)
            self.assertEqual(unmanifested.valid_links, 1)
            _write_manifest(database_path, manifest_path)

            verified = inspect_release_data(database_path, manifest_path)
            self.assertTrue(verified.ready)
            self.assertEqual(verified.manifest_errors, ())

    def test_release_gate_reports_every_requested_relationship_anomaly(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            database_path = Path(temp_directory) / "broken.db"
            _create_normalized_test_database(database_path)
            connection = sqlite3.connect(database_path)
            try:
                connection.execute("PRAGMA foreign_keys = OFF")
                connection.execute(
                    """
                    INSERT INTO courses (
                        id, dept, quarter, course_id, challenge_intellect, url, response_count
                    ) VALUES (2, 'TEST', 'Autumn 2026', 10000, 1.0,
                              'https://example.invalid/report/clean', 20)
                    """
                )
                connection.execute(
                    "INSERT INTO courses (id, dept, quarter, course_id, url) "
                    "VALUES (3, 'TEST', 'Autumn 2026', 20000, "
                    "'https://example.invalid/report/unlinked')"
                )
                connection.execute(
                    "INSERT INTO courses_professors (id, course_id, professor_id) "
                    "VALUES (2, 1, 1)"
                )
                connection.execute(
                    "INSERT INTO courses_professors (id, course_id, professor_id) "
                    "VALUES (3, 2, 1)"
                )
                connection.execute(
                    "INSERT INTO courses_professors (id, course_id, professor_id) "
                    "VALUES (4, 999, 999)"
                )
                connection.commit()
            finally:
                connection.close()

            report = inspect_release_data(database_path)
            self.assertGreater(report.logical_duplicate_report_rows, 0)
            self.assertGreater(report.duplicate_physical_link_rows, 0)
            self.assertGreater(report.duplicate_url_professor_pair_rows, 0)
            self.assertGreater(report.conflicting_duplicate_report_groups, 0)
            self.assertIn("challenge_intellect", report.conflict_examples[0])
            self.assertGreater(report.links_with_any_missing_parent, 0)
            self.assertGreater(report.dangling_course_links, 0)
            self.assertGreater(report.dangling_professor_links, 0)
            self.assertGreater(report.foreign_key_violations, 0)
            self.assertGreater(report.reports_without_valid_professor_links, 0)
            self.assertFalse(report.ready)

    def test_manifest_mismatch_rejects_changed_artifact(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            database_path = Path(temp_directory) / "normalized.db"
            manifest_path = Path(temp_directory) / "artifact-manifest.json"
            _create_normalized_test_database(database_path)
            _write_manifest(database_path, manifest_path)

            connection = sqlite3.connect(database_path)
            try:
                connection.execute("UPDATE courses SET response_count = 21 WHERE id = 1")
                connection.commit()
            finally:
                connection.close()

            report = inspect_release_data(database_path, manifest_path)
            self.assertFalse(report.ready)
            self.assertTrue(
                any("hash mismatch" in error for error in report.manifest_errors),
                report.manifest_errors,
            )

    def test_manifest_requires_complete_exact_finite_contract(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            database_path = Path(temp_directory) / "normalized.db"
            manifest_path = Path(temp_directory) / "artifact-manifest.json"
            _create_normalized_test_database(database_path)

            manifest_path.write_text(
                json.dumps(
                    {
                        "manifest_version": 1,
                        "counts": {"course_rows": 1},
                        "hashes": {"database_sha256": "0" * 64},
                    }
                ),
                encoding="utf-8",
            )
            incomplete = inspect_release_data(database_path, manifest_path)
            self.assertFalse(incomplete.ready)
            self.assertTrue(
                any("missing manifest count keys" in error for error in incomplete.manifest_errors)
            )
            self.assertTrue(
                any("missing manifest hash keys" in error for error in incomplete.manifest_errors)
            )

            manifest_path.write_text(
                '{"manifest_version":1,"manifest_version":1,"counts":NaN,"hashes":{}}',
                encoding="utf-8",
            )
            malformed = inspect_release_data(database_path, manifest_path)
            self.assertFalse(malformed.ready)
            self.assertTrue(malformed.manifest_errors)

    def test_release_factory_requires_explicit_verified_artifact(self):
        with patch.dict(os.environ, {RELEASE_MODE_ENV: "1"}, clear=True):
            with self.assertRaises(ReleaseConfigurationError):
                create_app()
            with self.assertRaises(ReleaseConfigurationError):
                create_release_app()

        with tempfile.TemporaryDirectory() as temp_directory:
            database_path = Path(temp_directory) / "normalized.db"
            manifest_path = Path(temp_directory) / "artifact-manifest.json"
            _create_normalized_test_database(database_path)
            _write_manifest(database_path, manifest_path)
            release_environment = {
                RELEASE_MODE_ENV: "true",
                DB_PATH_ENV: str(database_path),
                MANIFEST_ENV: str(manifest_path),
            }
            with patch.dict(os.environ, release_environment, clear=True):
                app = create_app()
                direct_release_app = create_release_app()
            self.assertEqual(app.test_client().get("/").status_code, 200)
            self.assertEqual(direct_release_app.test_client().get("/").status_code, 200)
            self.assertTrue(app.config["RELEASE_INTEGRITY_REPORT"]["ready"])

    def test_release_factory_rejects_relative_paths_and_raw_database(self):
        with patch.dict(
            os.environ,
            {
                RELEASE_MODE_ENV: "1",
                DB_PATH_ENV: "relative.db",
                MANIFEST_ENV: "relative.json",
            },
            clear=True,
        ):
            with self.assertRaises(ReleaseConfigurationError):
                create_app()

        with tempfile.TemporaryDirectory() as temp_directory:
            manifest_path = Path(temp_directory) / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "manifest_version": 1,
                        "counts": {"course_rows": 23_641},
                        "hashes": {"database_sha256": "0" * 64},
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    RELEASE_MODE_ENV: "1",
                    DB_PATH_ENV: str(self.database_path),
                    MANIFEST_ENV: str(manifest_path),
                },
                clear=True,
            ):
                with self.assertRaisesRegex(
                    ReleaseConfigurationError, "release artifact rejected"
                ):
                    create_app()


if __name__ == "__main__":
    unittest.main()
