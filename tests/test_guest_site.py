import importlib.util
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = REPOSITORY_ROOT / "site" / "app.py"

SPEC = importlib.util.spec_from_file_location("course_copilot_app", APP_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load Course Copilot app from {APP_PATH}")
COURSE_COPILOT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = COURSE_COPILOT
SPEC.loader.exec_module(COURSE_COPILOT)


class GuestSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        COURSE_COPILOT.app.config.update(TESTING=True)
        cls.client = COURSE_COPILOT.app.test_client()

    def test_public_routes_and_invalid_numbers_render(self):
        routes = (
            "/",
            "/?q=HUMA",
            "/plan",
            "/course/HUMA/18000",
            "/prereg",
            "/reveal",
            "/explore?wq=nan&wl=inf&wc=-inf&max_hours=nan&min_sections=nan",
        )
        for route in routes:
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)

        post_cases = (
            ("/prereg", {"candidates": "HUMA 18000", "keep": "nan", "max_load": "inf"}),
            ("/prereg", {"candidates": "HUMA 18000", "keep": "-50", "max_load": "-1"}),
            ("/reveal", {"dept": "HUMA", "cid": "18000", "name": "staff"}),
            ("/reveal", {
                "dept": "HUMA",
                "cid": "999999999999999999999999999999",
                "name": "",
            }),
        )
        for route, data in post_cases:
            with self.subTest(route=route, data=data):
                response = self.client.post(route, data=data)
                self.assertEqual(response.status_code, 200)

        self.assertEqual(
            self.client.get("/course/HUMA/999999999999999999999999999999").status_code,
            404,
        )

    def test_course_history_counts_distinct_report_urls(self):
        dept, course_id = "HUMA", 18000
        members = [(dept, course_id)] + COURSE_COPILOT.REVERSE_ALIAS.get(
            (dept, course_id), []
        )
        placeholders = " OR ".join(
            "(dept=? AND course_id=?)" for _ in members
        )
        parameters = [value for member in members for value in member]

        connection = sqlite3.connect(COURSE_COPILOT.FEEDBACK_DB)
        expected = dict(
            connection.execute(
                f"""
                SELECT quarter, COUNT(DISTINCT url)
                FROM courses
                WHERE ({placeholders})
                  AND (quarter LIKE 'Autumn %' OR quarter LIKE 'Winter %'
                       OR quarter LIKE 'Spring %' OR quarter LIKE 'Summer %')
                GROUP BY quarter
                """,
                parameters,
            ).fetchall()
        )
        connection.close()

        with COURSE_COPILOT.app.test_request_context(
            f"/course/{dept}/{course_id}"
        ), mock.patch.object(
            COURSE_COPILOT,
            "render_template",
            side_effect=lambda template, **context: {"template": template, **context},
        ):
            context = COURSE_COPILOT.course(dept, course_id)

        actual = {row["quarter"]: row["n_reports"] for row in context["history"]}
        self.assertEqual(actual, expected)

        self.assertEqual(
            COURSE_COPILOT.SIGNALS[(dept, course_id)]["n_reports"],
            sum(expected.values()),
        )

    def test_reveal_pool_deduplicates_by_url_and_professor_id(self):
        dept, course_id = "HUMA", 18000
        course_key = COURSE_COPILOT.ALIAS.get(
            (dept, course_id), (dept, course_id)
        )
        members = [course_key] + COURSE_COPILOT.REVERSE_ALIAS.get(course_key, [])
        placeholders = " OR ".join(
            "(c.dept=? AND c.course_id=?)" for _ in members
        )
        parameters = [value for member in members for value in member]

        connection = sqlite3.connect(COURSE_COPILOT.FEEDBACK_DB)
        expected_evidence_rows = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM (
                SELECT c.url, cp.professor_id
                FROM courses c
                JOIN courses_professors cp ON cp.course_id = c.id
                WHERE ({placeholders})
                GROUP BY c.url, cp.professor_id
            )
            """,
            parameters,
        ).fetchone()[0]
        connection.close()

        with COURSE_COPILOT.app.test_request_context(
            "/reveal",
            method="POST",
            data={"dept": dept, "cid": str(course_id)},
        ), mock.patch.object(
            COURSE_COPILOT,
            "render_template",
            side_effect=lambda template, **context: {"template": template, **context},
        ):
            context = COURSE_COPILOT.reveal()

        self.assertEqual(
            sum(row["n_reports"] for row in context["pool"]),
            expected_evidence_rows,
        )
        self.assertTrue(
            all(row["n_scored_reports"] <= row["n_reports"] for row in context["pool"])
        )

    def test_reveal_does_not_use_pooled_surname_rating(self):
        source = APP_PATH.read_text(encoding="utf-8")
        self.assertNotIn("avg_professor_rating", source)
        self.assertIn("GROUP BY c.url, p.id", source)

    def test_pages_state_coverage_and_probability_limits(self):
        course_page = self.client.get("/course/HUMA/18000").get_data(as_text=True)
        self.assertIn("not a calibrated probability", course_page)
        self.assertIn("Distinct reports", course_page)
        self.assertNotIn("only one instructor ever", course_page)

        prereg_page = self.client.post(
            "/prereg",
            data={"candidates": "HUMA 18000, ZZZZ 99999"},
        ).get_data(as_text=True)
        self.assertIn("Absent from our feedback coverage", prereg_page)
        self.assertIn("does not model the registrar", prereg_page)
        self.assertNotIn("new courses", prereg_page)

        for template_name in ("index.html", "explore.html", "plan.html", "prereg.html"):
            template = (APP_PATH.parent / "templates" / template_name).read_text(
                encoding="utf-8"
            )
            self.assertNotIn("likely_instructor", template, template_name)

    def test_reveal_never_recommends_from_missing_or_thin_numeric_evidence(self):
        missing_rating = self.client.post(
            "/reveal",
            data={"dept": "AANL", "cid": "10101", "name": "Theo"},
        ).get_data(as_text=True)
        self.assertIn("No numeric exact-course rating is available", missing_rating)
        self.assertNotIn("Keep it", missing_rating)

        oversized = self.client.post(
            "/reveal",
            data={"dept": "HUMA", "cid": "999999999999999999999999999999"},
        )
        self.assertEqual(oversized.status_code, 200)
        self.assertIn("3–6 digit course number", oversized.get_data(as_text=True))

    def test_personal_inputs_are_processed_by_post_not_query_strings(self):
        prereg_get = self.client.get(
            "/prereg?candidates=HUMA+18000&keep=3&max_load=45"
        ).get_data(as_text=True)
        self.assertNotIn("Your candidates, ranked", prereg_get)

        reveal_get = self.client.get(
            "/reveal?dept=AANL&cid=10101&name=Theo"
        ).get_data(as_text=True)
        self.assertNotIn("Your draw", reveal_get)

    def test_plan_missing_count_uses_unique_program_courses(self):
        program = "Economics"
        expected = sum(
            not COURSE_COPILOT.SIGNALS.get(key)
            or COURSE_COPILOT.SIGNALS[key].get("goldilocks") is None
            or COURSE_COPILOT.SIGNALS[key].get("n_reports", 0) < 3
            for key in COURSE_COPILOT.PROGRAM_POOLS[program]
        )
        with COURSE_COPILOT.app.test_request_context(
            "/plan",
            method="POST",
            data={"path": ["Economics", "Economics"]},
        ), mock.patch.object(
            COURSE_COPILOT,
            "render_template",
            side_effect=lambda template, **context: {"template": template, **context},
        ):
            context = COURSE_COPILOT.plan()

        self.assertEqual(context["paths"], [program])
        self.assertEqual(context["path_views"][0]["unrated"], expected)

    def test_four_class_plan_does_not_generate_a_fifth_course_hedge(self):
        candidates = ", ".join(
            f"{dept} {course_id}" for dept, course_id in list(COURSE_COPILOT.SIGNALS)[:6]
        )
        with COURSE_COPILOT.app.test_request_context(
            "/prereg",
            method="POST",
            data={"candidates": candidates, "keep": "4", "max_load": "45"},
        ), mock.patch.object(
            COURSE_COPILOT,
            "render_template",
            side_effect=lambda template, **context: {"template": template, **context},
        ):
            context = COURSE_COPILOT.prereg()

        self.assertEqual(context["keep"], 4)
        self.assertIsNone(context["hedge"])


if __name__ == "__main__":
    unittest.main()
