"""Backtest instructor prediction under hidden-names conditions.

Simulates the new pre-registration reality: the course list for a quarter is
known, but instructor names are hidden. Using only data from BEFORE the target
quarter, predict who teaches each course, then grade against who actually did.

    python backtest_instructors.py "Autumn 2025"
"""

import sys
from collections import defaultdict

from forecast import load, qkey


def ranked_instructors(taught, course, target_year, target_season, k=3):
    """Rank likely instructors for a course using only pre-target history."""
    target_k = qkey(target_year, target_season)
    scores = defaultdict(float)
    for (year, season), pids in taught.get(course, {}).items():
        key = qkey(year, season)
        if key >= target_k:
            continue
        age_years = (target_k - key) / 4
        weight = (0.6 ** age_years) * (2.0 if season == target_season else 1.0)
        for pid in pids:
            scores[pid] += weight
    total = sum(scores.values())
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    return [(pid, score / total) for pid, score in ranked[:k]]


def report(rows, label):
    if not rows:
        print(f"{label}: no evaluable courses")
        return
    hit1 = sum(preds[0][0] in truth for _, truth, preds in rows)
    hit3 = sum(any(pid in truth for pid, _ in preds) for _, truth, preds in rows)
    avg_truth = sum(len(truth) for _, truth, _ in rows) / len(rows)
    print(f"{label}: {len(rows)} courses (avg {avg_truth:.1f} actual instructors each)")
    print(f"  top-1 guess correct: {hit1 / len(rows):.0%}    actual prof in top-3 pool: {hit3 / len(rows):.0%}")
    for lo, hi, name in [(0.7, 1.01, ">=70%"), (0.4, 0.7, "40-70%"), (0.0, 0.4, "<40%")]:
        bucket = [r for r in rows if lo <= r[2][0][1] < hi]
        if bucket:
            acc = sum(preds[0][0] in truth for _, truth, preds in bucket) / len(bucket)
            print(f"  when model confidence {name}: top-1 correct {acc:.0%} (n={len(bucket)})")


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "Autumn 2025"
    target_season, target_year = target.split()
    target_year = int(target_year)

    offerings, taught, prof_names, _meta, _n = load()
    actual_courses = offerings[(target_year, target_season)]

    evaluable = []
    no_truth = no_history = 0
    for course in sorted(actual_courses):
        truth = taught[course].get((target_year, target_season), set())
        if not truth:
            no_truth += 1
            continue
        preds = ranked_instructors(taught, course, target_year, target_season)
        if not preds:
            no_history += 1
            continue
        evaluable.append((course, truth, preds))

    print(f"Simulating pre-registration for {target}: courses known, names hidden.\n")
    print(f"{len(actual_courses)} courses ran; {no_truth} have no recorded instructors "
          f"(unusable as ground truth); {no_history} were new/no history (model abstains).\n")

    report(evaluable, "All predictable courses")
    core = [r for r in evaluable if r[0][0] in ("SOSC", "HUMA")]
    print()
    report(core, "Core sequences (SOSC + HUMA -- where names are now hidden)")

    print("\nSample of highest-confidence predictions vs reality:")
    top = sorted(evaluable, key=lambda r: -r[2][0][1])[:8]
    for (dept, cid), truth, preds in top:
        pid, conf = preds[0]
        mark = "HIT " if pid in truth else "MISS"
        true_names = ", ".join(sorted(prof_names.get(t, "?") for t in truth))
        print(f"  [{mark}] {dept} {cid}: predicted {prof_names.get(pid, '?')} "
              f"({conf:.0%}) | actually: {true_names}")


if __name__ == "__main__":
    main()
