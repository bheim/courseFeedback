"""Build the precomputed signal layer (Roadmap W4) into signals.db.

One row per unified course, containing everything the product surfaces need:
regime classification, monopoly flag, percentile ranks, goldilocks score,
crowd-pleaser index, fairness gap, program-requirement count, and the
Autumn 2026 offering/instructor forecast.

    python build_signals.py

All inputs are already-published aggregates; signals.db is safe to commit.
"""

import os
import sqlite3
from collections import defaultdict

from forecast import DB_PATH, load, predict_quarter, predict_instructor
from identities import CATALOG_DB, build_alias_map, load_terms, parse_code

OUT_DB = os.path.join(os.path.dirname(__file__), "signals.db")

TARGET = (2026, "Autumn")
MIN_SECTIONS = 3          # percentile pool membership
HIDDEN_NAME_DEPTS = {"SOSC", "HUMA"}   # Civ is scattered across depts; W5 refines


def percentile_ranks(values):
    """value -> percentile (0-100) among non-None values."""
    clean = sorted(v for v in values if v is not None)
    if not clean:
        return {}
    return {v: round(100 * i / max(1, len(clean) - 1))
            for i, v in enumerate(clean)}


def main():
    offerings, taught, prof_names, course_meta, n_sections = load()
    alias = build_alias_map()
    terms = load_terms(alias=alias)

    # Raw per-course aggregates straight from the feedback db (canonicalized)
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    sums = defaultdict(lambda: defaultdict(float))
    counts = defaultdict(lambda: defaultdict(int))
    for d, c, ci, fair, purpose, respect, exc in conn.execute(
        """SELECT dept, course_id, challenge_intellect, fairness,
                  purpose, respect, excellence
           FROM courses"""):
        key = alias.get((d, c), (d, c))
        for name, val in [("challenge_intellect", ci), ("fairness", fair),
                          ("purpose", purpose), ("respect", respect),
                          ("excellence", exc)]:
            if val is not None:
                sums[key][name] += val
                counts[key][name] += 1
    conn.close()

    def avg(key, name):
        return sums[key][name] / counts[key][name] if counts[key][name] else None

    # Program-requirement counts from the catalog
    required_by = defaultdict(set)
    if os.path.exists(CATALOG_DB):
        cconn = sqlite3.connect(f"file:{CATALOG_DB}?mode=ro", uri=True)
        for program, code in cconn.execute("SELECT program, code FROM program_courses"):
            course = parse_code(code)
            if course:
                required_by[alias.get(course, course)].add(program)
        cconn.close()

    courses = [k for k, n in n_sections.items() if n >= MIN_SECTIONS]

    ratings = {k: course_meta.get(k, (None, None))[0] for k in courses}
    hours = {k: course_meta.get(k, (None, None))[1] for k in courses}
    challenge = {k: avg(k, "challenge_intellect") for k in courses}

    r_pct = percentile_ranks(ratings.values())
    h_pct = percentile_ranks(hours.values())
    c_pct = percentile_ranks(challenge.values())

    preds = predict_quarter(offerings, *TARGET, terms=terms)

    out = sqlite3.connect(OUT_DB)
    out.execute("DROP TABLE IF EXISTS course_signals")
    out.execute("""CREATE TABLE course_signals (
        dept TEXT, course_id INTEGER,
        n_sections INTEGER, n_quarters INTEGER, last_quarter TEXT,
        n_instructors INTEGER, monopoly INTEGER, regime TEXT,
        avg_rating REAL, rating_pctl INTEGER,
        avg_hours REAL, hours_pctl INTEGER,
        avg_challenge REAL, challenge_pctl INTEGER,
        fairness_gap REAL, crowd_pleaser INTEGER, goldilocks INTEGER,
        required_by_n_programs INTEGER,
        p_autumn_2026 REAL, likely_instructor TEXT, instructor_conf REAL,
        PRIMARY KEY (dept, course_id))""")

    rows = []
    for key in courses:
        dept, cid = key
        history = taught.get(key, {})
        quarters = sorted(history, key=lambda q: (q[0], q[1]))
        last_q = f"{quarters[-1][1]} {quarters[-1][0]}" if quarters else ""
        instructors = set().union(*history.values()) if history else set()

        monopoly = int(len(instructors) == 1 and n_sections[key] >= MIN_SECTIONS)
        if dept in HIDDEN_NAME_DEPTS:
            regime = "B"
        elif monopoly:
            regime = "C"
        else:
            regime = "A"

        rating, hrs, chal = ratings.get(key), hours.get(key), challenge.get(key)
        rp = r_pct.get(rating)
        hp = h_pct.get(hrs)
        cp = c_pct.get(chal)

        fairness = avg(key, "fairness")
        others = [avg(key, n) for n in ("challenge_intellect", "purpose",
                                        "respect", "excellence")]
        others = [o for o in others if o is not None]
        fairness_gap = round(fairness - sum(others) / len(others), 3) \
            if fairness is not None and others else None

        crowd_pleaser = None
        if rp is not None and cp is not None and hp is not None:
            crowd_pleaser = max(0, round(rp - (cp + hp) / 2))

        goldilocks = None
        if rp is not None and hp is not None and cp is not None:
            # Default weights: quality 50%, lightness 30%, challenge 20%.
            # The site exposes these as user sliders (W5).
            goldilocks = round(0.5 * rp + 0.3 * (100 - hp) + 0.2 * cp)

        pid, conf = predict_instructor(taught, key, *TARGET)
        rows.append((
            dept, cid, n_sections[key], len(quarters), last_q,
            len(instructors), monopoly, regime,
            rating, rp, hrs, hp, chal, cp,
            fairness_gap, crowd_pleaser, goldilocks,
            len(required_by.get(key, ())),
            preds.get(key), prof_names.get(pid, ""), round(conf, 2),
        ))

    out.executemany(
        "INSERT INTO course_signals VALUES (" + ",".join("?" * 21) + ")", rows)
    out.commit()

    n = len(rows)
    for label, q in [
        ("regime A", "regime='A'"), ("regime B (hidden names)", "regime='B'"),
        ("regime C (monopoly)", "regime='C'"),
        ("crowd-pleaser >= 40", "crowd_pleaser >= 40"),
        ("required by 2+ programs", "required_by_n_programs >= 2"),
    ]:
        c = out.execute(f"SELECT COUNT(*) FROM course_signals WHERE {q}").fetchone()[0]
        print(f"  {label}: {c}")
    print(f"\ncourse_signals built: {n} established courses -> {os.path.basename(OUT_DB)}")

    print("\nTop goldilocks (default weights), min 4 sections:")
    for r in out.execute("""SELECT dept, course_id, goldilocks, avg_rating,
                            ROUND(avg_hours,1), likely_instructor FROM course_signals
                            WHERE n_sections >= 4 AND goldilocks IS NOT NULL
                            ORDER BY goldilocks DESC LIMIT 8"""):
        print(f"  {r[0]} {r[1]}: score {r[2]} | rating {r[3]:.2f} | {r[4]} hrs | "
              f"likely: {r[5] or '?'}")
    out.close()


if __name__ == "__main__":
    main()
