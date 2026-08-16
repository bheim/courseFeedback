"""Data-quality tripwire. Run after every scrape (RUNBOOK step) — it fails
LOUDLY if the newest quarter's data looks degraded, so a silent breakage like
the 2025 platform migration (which cost 5 of 12 ratings and all hours data
for a year before anyone noticed) gets caught the same day.

    python data_quality_check.py            # checks the newest quarter
    python data_quality_check.py "Winter 2026"   # or a specific quarter

Exit code 0 = healthy, 1 = tripped.
"""

import sqlite3
import sys

DB_PATH = 'course_feedback.db'
SEASONS = {"Winter": 0, "Spring": 1, "Summer": 2, "Autumn": 3}

RATING_COLS = ["challenge_intellect", "purpose", "standards", "feedback", "fairness",
               "respect", "excellence", "organization", "challenge", "available",
               "inclusive", "significant"]

# Thresholds calibrated to post-repair reality: healthy quarters show ~70-84%
# rating/hours coverage (the gap to 100% is graduate-form reports, which the
# parser does not yet cover) and ~100% instructor coverage.
MIN_INSTRUCTOR_PCT = 90
MIN_ANY_RATING_PCT = 50
MIN_PER_COLUMN_PCT_OF_RATED = 60   # catches selective breakage (the migration
                                   # zeroed 5 specific columns while 7 worked)
MIN_HOURS_PCT_OF_RATED = 60
# 1,378 legacy rows carry malformed quarter labels ("Form 10" etc.) from
# scrapes prior to 2026; the check fires only if that count GROWS.
KNOWN_LEGACY_MALFORMED = 1378
MALFORMED_GROWTH_ALLOWANCE = 25


def latest_quarter(cur):
    rows = cur.execute("SELECT DISTINCT quarter FROM courses").fetchall()
    best, best_key = None, -1
    for (q,) in rows:
        parts = q.split()
        if len(parts) == 2 and parts[0] in SEASONS and parts[1].isdigit():
            key = int(parts[1]) * 4 + SEASONS[parts[0]]
            if key > best_key:
                best, best_key = q, key
    return best


def main():
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    cur = conn.cursor()

    quarter = sys.argv[1] if len(sys.argv) > 1 else latest_quarter(cur)
    if not quarter:
        print("TRIPWIRE FAILED: no parseable quarters found in the database at all.")
        sys.exit(1)

    total = cur.execute("SELECT COUNT(*) FROM courses WHERE quarter=?", (quarter,)).fetchone()[0]
    if total == 0:
        print(f"TRIPWIRE FAILED: no rows found for quarter '{quarter}'.")
        sys.exit(1)

    failures = []

    with_prof = cur.execute("""SELECT COUNT(*) FROM courses c WHERE quarter=? AND EXISTS
        (SELECT 1 FROM courses_professors cp WHERE cp.course_id = c.id)""", (quarter,)).fetchone()[0]
    prof_pct = 100 * with_prof / total
    if prof_pct < MIN_INSTRUCTOR_PCT:
        failures.append(f"instructor coverage {prof_pct:.0f}% < {MIN_INSTRUCTOR_PCT}%")

    any_rating_expr = " OR ".join(f"{c} IS NOT NULL" for c in RATING_COLS)
    rated = cur.execute(
        f"SELECT COUNT(*) FROM courses WHERE quarter=? AND ({any_rating_expr})", (quarter,)
    ).fetchone()[0]
    rated_pct = 100 * rated / total
    if rated_pct < MIN_ANY_RATING_PCT:
        failures.append(f"rows with any rating {rated_pct:.0f}% < {MIN_ANY_RATING_PCT}% "
                        f"(grad-form rows explain ~25-30%, not more)")

    per_col_report = []
    if rated:
        for col in RATING_COLS:
            n = cur.execute(
                f"SELECT COUNT({col}) FROM courses WHERE quarter=? AND ({any_rating_expr})",
                (quarter,)).fetchone()[0]
            pct = 100 * n / rated
            per_col_report.append(f"{col} {pct:.0f}%")
            if pct < MIN_PER_COLUMN_PCT_OF_RATED:
                failures.append(f"column '{col}' present in only {pct:.0f}% of rated rows "
                                f"< {MIN_PER_COLUMN_PCT_OF_RATED}% (question wording changed again?)")

        hours = cur.execute(f"""SELECT COUNT(*) FROM courses WHERE quarter=? AND ({any_rating_expr}) AND
            COALESCE(less_five,0)+COALESCE(five_to_ten,0)+COALESCE(ten_to_fifteen,0)
            +COALESCE(fifteen_to_twenty,0)+COALESCE(twenty_to_twenty_five,0)
            +COALESCE(twenty_five_to_thirty,0)+COALESCE(more_thirty,0) > 0""", (quarter,)).fetchone()[0]
        hours_pct = 100 * hours / rated
        if hours_pct < MIN_HOURS_PCT_OF_RATED:
            failures.append(f"hours data in only {hours_pct:.0f}% of rated rows "
                            f"< {MIN_HOURS_PCT_OF_RATED}% (chart image moved again?)")
    else:
        hours_pct = 0

    malformed = cur.execute("""SELECT COUNT(*) FROM courses WHERE quarter NOT LIKE 'Winter %'
        AND quarter NOT LIKE 'Spring %' AND quarter NOT LIKE 'Summer %'
        AND quarter NOT LIKE 'Autumn %'""").fetchone()[0]
    if malformed > KNOWN_LEGACY_MALFORMED + MALFORMED_GROWTH_ALLOWANCE:
        failures.append(f"malformed quarter labels grew: {malformed} now vs "
                        f"{KNOWN_LEGACY_MALFORMED} known legacy rows "
                        f"(quarter parsing broke again?)")

    conn.close()

    print(f"Quarter checked: {quarter} ({total} rows)")
    print(f"  instructors {prof_pct:.0f}% | any-rating {rated_pct:.0f}% | hours-of-rated {hours_pct:.0f}%")
    if per_col_report:
        print(f"  per-column (of rated rows): {', '.join(per_col_report)}")

    if failures:
        print("\n" + "!" * 66)
        print("TRIPWIRE FAILED — the scrape looks degraded. Do NOT push this data")
        print("to production until the cause is understood:")
        for f in failures:
            print(f"  - {f}")
        print("!" * 66)
        sys.exit(1)

    print("\nTripwire passed: data quality is in the healthy range.")


if __name__ == "__main__":
    main()
