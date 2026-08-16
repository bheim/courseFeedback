"""Pressure-test instructor prediction: many quarters, harsher metrics, baselines.

Checks performed:
1. Sweep over 7 target quarters (not just Autumn 2025) — does accuracy hold?
2. Per-SECTION metric: a student lands in one section; did our top-1 name
   match that section's actual instructor? (The course-level "hit any
   instructor" metric is generous for multi-section courses.)
3. Baselines: (a) modal = most-frequently-observed past instructor,
   (b) last-set = every instructor from the most recent past offering
   (a set-valued, generous baseline). If the model can't beat these,
   the weighting scheme adds nothing.
All predictions use only data from strictly before the target quarter.

    python pressure_test.py
"""

import sqlite3
from collections import defaultdict

from forecast import DB_PATH, SEASON_IDX, qkey
from backtest_instructors import ranked_instructors


def load_sections():
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    cur = conn.cursor()
    sec_profs = defaultdict(set)
    for sid, pid in cur.execute("SELECT course_id, professor_id FROM courses_professors"):
        sec_profs[sid].add(pid)
    sections = []                                    # ((dept,cid), (year,season), {prof_ids})
    taught = defaultdict(lambda: defaultdict(set))   # course -> quarter -> {prof_ids}
    for sid, d, c, q in cur.execute("SELECT id, dept, course_id, quarter FROM courses"):
        parts = q.split()
        if len(parts) == 2 and parts[0] in SEASON_IDX and parts[1].isdigit():
            year, season = int(parts[1]), parts[0]
            profs = sec_profs.get(sid, set())
            sections.append(((d, c), (year, season), profs))
            taught[(d, c)][(year, season)] |= profs
    conn.close()
    return sections, taught


def eval_quarter(sections, taught, target_year, target_season):
    target_k = qkey(target_year, target_season)

    truth_by_course = defaultdict(set)
    quarter_sections = []
    for course, (y, s), profs in sections:
        if (y, s) == (target_year, target_season) and profs:
            truth_by_course[course] |= profs
            quarter_sections.append((course, profs))

    rows = []
    for course, truth in truth_by_course.items():
        preds = ranked_instructors(taught, course, target_year, target_season)
        if preds:
            rows.append((course, truth, preds))
    if not rows:
        return None
    n = len(rows)

    top1 = sum(p[0][0] in t for _, t, p in rows) / n
    top3 = sum(any(pid in t for pid, _ in p) for _, t, p in rows) / n

    hi = [r for r in rows if r[2][0][1] >= 0.7]
    hi_acc = sum(p[0][0] in t for _, t, p in hi) / len(hi) if hi else None

    # Student's-eye view: evaluate against each individual section
    pred_by_course = {c: p for c, _, p in rows}
    sec_rows = [(c, profs) for c, profs in quarter_sections if c in pred_by_course]
    sec_top1 = sum(pred_by_course[c][0][0] in profs for c, profs in sec_rows) / len(sec_rows)

    # Baseline (a): most-frequently-observed past instructor (no recency/season logic)
    def modal(course):
        counts = defaultdict(int)
        for (y, s), pids in taught[course].items():
            if qkey(y, s) < target_k:
                for pid in pids:
                    counts[pid] += 1
        return max(counts, key=counts.get) if counts else None

    base_modal = sum(modal(c) in t for c, t, _ in rows) / n

    # Baseline (b): the full instructor set from the most recent past offering
    def last_set(course):
        history = [(qkey(y, s), pids) for (y, s), pids in taught[course].items()
                   if qkey(y, s) < target_k and pids]
        return max(history)[1] if history else set()

    base_last_any = sum(bool(last_set(c) & t) for c, t, _ in rows) / n

    return {
        "n": n, "coverage": n / len(truth_by_course),
        "top1": top1, "top3": top3,
        "hi_share": len(hi) / n, "hi_acc": hi_acc,
        "n_sections": len(sec_rows), "sec_top1": sec_top1,
        "base_modal": base_modal, "base_last_any": base_last_any,
    }


def main():
    sections, taught = load_sections()
    targets = [
        (2023, "Autumn"), (2024, "Winter"), (2024, "Spring"), (2024, "Autumn"),
        (2025, "Winter"), (2025, "Spring"), (2025, "Autumn"),
        (2026, "Winter"), (2026, "Spring"),
    ]
    print("All predictions use only pre-target data (enforced by qkey filter).\n")
    header = (f"{'quarter':<13} {'courses':>7} {'top1':>5} {'top3':>5} "
              f"{'hi-conf acc (share)':>20} {'per-section top1':>17} "
              f"{'modal':>6} {'last-set':>8}")
    print(header)
    for year, season in targets:
        r = eval_quarter(sections, taught, year, season)
        if not r:
            continue
        hi = f"{r['hi_acc']:.0%} ({r['hi_share']:.0%})" if r["hi_acc"] is not None else "--"
        print(f"{season + ' ' + str(year):<13} {r['n']:>7} {r['top1']:>5.0%} {r['top3']:>5.0%} "
              f"{hi:>20} {r['sec_top1']:>16.0%} "
              f"{r['base_modal']:>6.0%} {r['base_last_any']:>8.0%}")

    # Identity-split check: same last name + dept under multiple ids can cause
    # false misses (understates accuracy)
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    n_collide = conn.execute("""
        SELECT COUNT(*) FROM (
            SELECT dept, last_name FROM professors
            GROUP BY dept, last_name HAVING COUNT(*) > 1
        )
    """).fetchone()[0]
    n_profs = conn.execute("SELECT COUNT(*) FROM professors").fetchone()[0]
    conn.close()
    print(f"\n{n_collide} (dept, last_name) pairs have multiple professor ids "
          f"(of {n_profs} professors) — name-variant splits cause false misses, "
          f"so true accuracy is likely slightly higher than measured.")


if __name__ == "__main__":
    main()
