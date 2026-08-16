"""Forecast which courses will run in a future quarter and who will likely teach them.

Reads the existing course_feedback.db (read-only). Two commands:

    python forecast.py backtest              # measure accuracy against known 2025 quarters
    python forecast.py predict "Autumn 2026" # write predictions CSV for a future quarter

Model (v1, deliberately transparent):
- P(course offered in season S of year Y) starts from how often it ran in the
  last 3 same-season quarters we have data for, with small boosts for having
  run in that season last year and for having run at all in the last 3
  calendar quarters.
- Likely instructor: professors who taught the course historically, weighted
  by recency (0.6 per year of age) and doubled for same-season occurrences.
"""

import csv
import os
import sqlite3
import sys
from collections import defaultdict

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "analyzeCourseFeedback", "course_feedback.db")

SEASONS = ["Winter", "Spring", "Summer", "Autumn"]  # calendar order within a year
SEASON_IDX = {s: i for i, s in enumerate(SEASONS)}


def qkey(year, season):
    """Sortable index for a quarter."""
    return year * 4 + SEASON_IDX[season]


def load():
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    cur = conn.cursor()

    prof_names = {
        pid: f"{fn} {ln}".strip()
        for pid, fn, ln in cur.execute("SELECT id, first_name, last_name FROM professors")
    }

    sec_profs = defaultdict(set)
    for sid, pid in cur.execute("SELECT course_id, professor_id FROM courses_professors"):
        sec_profs[sid].add(pid)

    course_meta = {}
    for d, c, r, h in cur.execute(
        "SELECT dept, course_id, avg_course_rating, avg_course_hours FROM courses"
    ):
        course_meta[(d, c)] = (r, h)

    offerings = defaultdict(set)                     # (year, season) -> {(dept, course_id)}
    taught = defaultdict(lambda: defaultdict(set))   # (dept, course_id) -> (year, season) -> {prof_id}
    n_sections = defaultdict(int)                    # (dept, course_id) -> total sections ever

    for sid, d, c, q in cur.execute("SELECT id, dept, course_id, quarter FROM courses"):
        parts = q.split()
        # Skips malformed quarters like "Form 10" and "Unknown Quarter"
        if len(parts) == 2 and parts[0] in SEASON_IDX and parts[1].isdigit():
            year, season = int(parts[1]), parts[0]
            offerings[(year, season)].add((d, c))
            taught[(d, c)][(year, season)] |= sec_profs.get(sid, set())
            n_sections[(d, c)] += 1

    conn.close()
    return offerings, taught, prof_names, course_meta, n_sections


def predict_quarter(offerings, target_year, target_season):
    """Return {course: probability} using only quarters strictly before the target."""
    target_k = qkey(target_year, target_season)
    prior = [q for q in offerings if qkey(*q) < target_k]
    if not prior:
        return {}

    same_season = sorted(
        (q for q in prior if q[1] == target_season), key=lambda q: qkey(*q), reverse=True
    )[:3]
    recent3 = sorted(prior, key=lambda q: qkey(*q), reverse=True)[:3]
    recent_courses = set().union(*(offerings[q] for q in recent3))

    universe = set().union(*(offerings[q] for q in prior))
    preds = {}
    for course in universe:
        base = (
            sum(course in offerings[q] for q in same_season) / len(same_season)
            if same_season else 0.0
        )
        p = base
        if same_season and course in offerings[same_season[0]]:
            p = min(1.0, p + 0.15)
        if course in recent_courses:
            p = min(1.0, p + 0.10)
        preds[course] = round(p, 3)
    return preds


def predict_instructor(taught, course, target_year, target_season):
    """Return (prof_id, confidence 0-1) for the most likely instructor, or (None, 0)."""
    target_k = qkey(target_year, target_season)
    scores = defaultdict(float)
    for (year, season), pids in taught.get(course, {}).items():
        k = qkey(year, season)
        if k >= target_k:
            continue
        age_years = (target_k - k) / 4
        weight = (0.6 ** age_years) * (2.0 if season == target_season else 1.0)
        for pid in pids:
            scores[pid] += weight
    if not scores:
        return None, 0.0
    total = sum(scores.values())
    best = max(scores, key=scores.get)
    return best, scores[best] / total


def backtest(offerings, taught):
    print("Backtest: predict each 2025 quarter using only earlier data, then compare to reality.\n")
    for target_year, target_season in [(2025, "Winter"), (2025, "Spring"), (2025, "Autumn")]:
        actual = offerings[(target_year, target_season)]
        preds = predict_quarter(offerings, target_year, target_season)
        predicted = {c for c, p in preds.items() if p >= 0.5}

        tp = predicted & actual
        precision = len(tp) / len(predicted) if predicted else 0
        recall = len(tp) / len(actual) if actual else 0

        # Baseline: "same as last year's same season"
        baseline = offerings[(target_year - 1, target_season)]
        b_tp = baseline & actual
        b_precision = len(b_tp) / len(baseline) if baseline else 0

        # Instructor top-1 accuracy on correctly predicted courses
        hits = evaluable = 0
        for course in tp:
            true_profs = taught[course].get((target_year, target_season), set())
            pid, _conf = predict_instructor(taught, course, target_year, target_season)
            if true_profs and pid is not None:
                evaluable += 1
                hits += pid in true_profs
        inst_acc = hits / evaluable if evaluable else 0

        print(f"{target_season} {target_year}: {len(actual)} courses actually ran")
        print(f"  predicted {len(predicted)} courses at p>=0.5 -> precision {precision:.0%}, recall {recall:.0%}")
        print(f"  (baseline 'same as last year': precision {b_precision:.0%})")
        print(f"  top-1 instructor correct on {inst_acc:.0%} of correctly predicted courses (n={evaluable})\n")
    print("Note: recall is understated — scrape coverage expanded in 2025, so many 'missed'")
    print("courses were newly covered by the scraper, not newly offered by the university.")


def predict(offerings, taught, prof_names, course_meta, n_sections, target):
    try:
        target_season, target_year = target.split()
        target_year = int(target_year)
        assert target_season in SEASON_IDX
    except (ValueError, AssertionError):
        sys.exit(f'Could not parse quarter "{target}". Use e.g.: predict "Autumn 2026"')

    preds = predict_quarter(offerings, target_year, target_season)
    out_path = os.path.join(
        os.path.dirname(__file__), f"predictions_{target_season.lower()}_{target_year}.csv"
    )
    rows = []
    for (dept, cid), p in preds.items():
        if p < 0.2:
            continue
        pid, conf = predict_instructor(taught, (dept, cid), target_year, target_season)
        history = sorted(taught[(dept, cid)], key=lambda q: qkey(*q), reverse=True)
        last = f"{history[0][1]} {history[0][0]}" if history else ""
        rating, hours = course_meta.get((dept, cid), (None, None))
        rows.append({
            "dept": dept,
            "course": cid,
            "p_offered": p,
            "likely_instructor": prof_names.get(pid, ""),
            "instructor_confidence": round(conf, 2),
            "last_offered": last,
            "times_offered": len(history),
            "sections_ever": n_sections[(dept, cid)],
            "avg_course_rating": round(rating, 2) if rating else "",
            "avg_course_hours": round(hours, 2) if hours else "",
        })
    rows.sort(key=lambda r: (-r["p_offered"], r["dept"], r["course"]))

    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    high = sum(1 for r in rows if r["p_offered"] >= 0.5)
    print(f"{target}: {len(rows)} candidate courses written to {os.path.basename(out_path)}")
    print(f"  {high} predicted to run at p>=0.5")
    print("  Top 10 by confidence:")
    for r in rows[:10]:
        print(f"    {r['dept']} {r['course']}  p={r['p_offered']}  "
              f"likely: {r['likely_instructor']} ({r['instructor_confidence']})")


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("backtest", "predict"):
        sys.exit(__doc__)
    offerings, taught, prof_names, course_meta, n_sections = load()
    if sys.argv[1] == "backtest":
        backtest(offerings, taught)
    else:
        if len(sys.argv) < 3:
            sys.exit('Usage: python forecast.py predict "Autumn 2026"')
        predict(offerings, taught, prof_names, course_meta, n_sections, sys.argv[2])


if __name__ == "__main__":
    main()
