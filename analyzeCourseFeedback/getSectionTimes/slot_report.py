"""Slot-quality analysis: does WHEN you take HBC change WHO you draw?

The naming backtest (backtest_times.py) already showed you cannot predict
the instructor's NAME from a time slot (~10% vs a 62% ceiling). This asks
the decision-relevant question instead: does a slot's history shift the
QUALITY DISTRIBUTION of the instructor you draw - and is that shift real,
or noise? Every claim is walk-forward backtested with a permutation test
before it is allowed to order the 2026 ballot.

Sections:
  A. data integrity audit (term caps, dept purity, Autumn 2025 roster)
  B. instructor quality table (feedback ratings for every HBC instructor)
  C. walk-forward backtest of predicted slot quality vs realized
  D. Autumn 2026 ballot: sections ranked, with the trust level printed

    python slot_report.py                # HUMA 12300, times.db in cwd
    python slot_report.py --db path/times.db --course 12300
"""

import os
import random
import re
import sqlite3
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN_DB = os.path.join(HERE, "..", "course_feedback.db")

DECAY = 0.6          # weight = DECAY ** (target_year - taught_year - ... age)
SHRINK_K = 2.0       # pseudo-observations pulling a slot toward the HBC mean
PERMS = 2000
HBC = (12300, 12400, 12500)

SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv"}
HIDDEN = {"staff", "tbd", "to be announced", "instructor tbd", ""}


def norm_names(instructor):
    parts = [p.strip().lower() for p in (instructor or "").split(",")]
    return tuple(sorted(p for p in parts if p and p not in SUFFIXES
                        and p not in HIDDEN))


def pretty(names):
    return " + ".join(p.title() for p in names) if names else "(hidden)"


def t_minutes(s):
    m = re.match(r"(\d{1,2}):(\d{2})\s*([AP]M)", s or "")
    if not m:
        return None
    h, mi = int(m.group(1)) % 12, int(m.group(2))
    return (h + (12 if m.group(3) == "PM" else 0)) * 60 + mi


# ---------------------------------------------------------------- load
def load_times(db):
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = conn.execute("""SELECT term, dept, course_id, section, instructor,
                                  days, start_time, end_time, enrolled, capacity
                           FROM section_times""").fetchall()
    conn.close()
    return rows


def hbc_autumns(rows, course):
    out = defaultdict(list)
    for term, dept, cid, sec, instr, days, start, end, *_ in rows:
        m = re.match(r"Autumn (\d{4})", term or "")
        if not m or dept != "HUMA" or cid != course or not days:
            continue
        out[int(m.group(1))].append({
            "sec": sec, "who": norm_names(instr), "raw": instr,
            "slot": (days, start), "days": days, "start": start, "end": end})
    return out


def suffix_owner(times_rows):
    """The feedback scraper split 'Castro, Jr.' into a professor whose last
    name is literally 'Jr.'. Reattach it using the scrape itself: if HUMA
    HBC listings show exactly one 'Surname, Jr.' string, that surname owns
    the suffix row. No guessing - ambiguity means no merge."""
    owners = set()
    pat = re.compile(r"([A-Za-z'\-]+),\s*(?:Jr\.?|Sr\.?|II|III|IV)\b", re.I)
    for term, dept, cid, sec, instr, *_ in times_rows:
        if dept == "HUMA" and cid in HBC and instr:
            for m in pat.finditer(instr):
                owners.add(m.group(1).lower())
    return owners.pop() if len(owners) == 1 else None


def quality_table(times_rows):
    """HBC-specific rating per instructor last name; feedback DB ids only,
    scoped to HUMA HBC sections so surname collisions can't leak in."""
    conn = sqlite3.connect(f"file:{MAIN_DB}?mode=ro", uri=True)
    q = conn.execute(f"""
        SELECT LOWER(p.last_name), p.first_name,
               AVG(cp.avg_prof_course_rating), AVG(c.avg_course_hours),
               COUNT(*), MAX(c.quarter)
        FROM courses c
        JOIN courses_professors cp ON cp.course_id = c.id
        JOIN professors p ON p.id = cp.professor_id
        WHERE c.dept = 'HUMA' AND c.course_id IN {HBC}
          AND cp.avg_prof_course_rating IS NOT NULL
        GROUP BY p.id""").fetchall()
    conn.close()
    owner = suffix_owner(times_rows)
    table = {}
    merged_note = None
    for last, first, rating, hours, n, last_q in q:
        if rating is None:
            continue
        if last.strip(". ") in {"jr", "sr", "ii", "iii", "iv"}:
            if owner is None:
                continue
            if owner in table:
                d = table[owner]
                tot = d["n"] + n
                d["rating"] = (d["rating"] * d["n"] + rating * n) / tot
                d["n"] = tot
            else:
                table[owner] = {"first": "", "rating": rating,
                                "hours": hours, "n": n, "last_q": last_q}
            merged_note = f"'{last}' identity merged into {owner.title()}"
            continue
        prev = table.get(last)
        if prev is not None and not prev["first"]:
            # a suffix row landed here first; fold it into the named professor
            tot = prev["n"] + n
            table[last] = {"first": first,
                           "rating": (prev["rating"] * prev["n"] + rating * n) / tot,
                           "hours": hours, "n": tot, "last_q": last_q}
            continue
        # keep the better-attested professor if two HBC teachers share a name
        if prev is not None and prev["n"] >= n:
            continue
        table[last] = {"first": first, "rating": rating,
                       "hours": hours, "n": n, "last_q": last_q}
    if merged_note:
        print(f"[identity] {merged_note}")
    return table


def rate(who, qual):
    """Mean HBC rating across a section's (possibly multiple) instructors."""
    vals = [qual[w]["rating"] for w in who if w in qual]
    return sum(vals) / len(vals) if vals else None


# ---------------------------------------------------------------- A
def audit(rows, autumns, course):
    print("=" * 72)
    print("A. DATA INTEGRITY AUDIT")
    per_term = Counter()
    off_dept = Counter()
    for term, dept, *_ in rows:
        per_term[term] += 1
        if dept != "HUMA":
            off_dept[(term, dept)] += 1
    capped = [t for t, n in per_term.items() if n == 250]
    print(f"terms captured: {len(per_term)}; rows: {sum(per_term.values())}")
    if capped:
        print(f"CAPPED AT 250 (portal result limit - these terms are "
              f"INCOMPLETE): {sorted(capped)}")
    if off_dept:
        print("non-HUMA rows found (filter leaked on these runs):")
        for (term, dept), n in sorted(off_dept.items()):
            print(f"  {term}: {dept} x{n}")
    else:
        print("dept purity: every row is HUMA - the department filter held")

    for year in (2025, 2026):
        secs = sorted(autumns.get(year, []), key=lambda s: int(s["sec"])
                      if str(s["sec"]).isdigit() else 0)
        print(f"\nAutumn {year} HUMA {course}: {len(secs)} sections")
        for s in secs:
            print(f"  /{s['sec']:<3} {s['days']:<12} {s['start']:>9}  "
                  f"{s['raw'] or '(hidden)'}")


# ---------------------------------------------------------------- C
def band(start):
    m = t_minutes(start)
    if m is None:
        return "unknown"
    if m < 11 * 60:
        return "morning"
    if m < 14 * 60:
        return "midday"
    return "afternoon"


# 'Cluster' granularities, finest first. Exact slots may reshuffle while a
# coarser cluster (all TTh mornings, say) still tilts the draw.
GRAINS = [
    ("exact slot", lambda s: (s["days"], s["start"])),
    ("day x band", lambda s: (s["days"], band(s["start"]))),
    ("day pattern", lambda s: s["days"]),
    ("time band", lambda s: band(s["start"])),
]


def slot_quality(history_years, autumns, qual, target_year, keyf):
    """Recency-weighted mean rating of a cluster's past holders, shrunk
    toward the overall HBC mean. Returns dict key -> (q_hat, weight)."""
    all_r = [r for y in history_years for s in autumns[y]
             for r in [rate(s["who"], qual)] if r is not None]
    prior = sum(all_r) / len(all_r) if all_r else None
    acc = defaultdict(lambda: [0.0, 0.0])
    for y in history_years:
        w_year = DECAY ** (target_year - y - 1)
        for s in autumns[y]:
            r = rate(s["who"], qual)
            if r is None:
                continue
            acc[keyf(s)][0] += w_year * r
            acc[keyf(s)][1] += w_year
    out = {}
    for key, (num, den) in acc.items():
        out[key] = ((num + SHRINK_K * prior) / (den + SHRINK_K), den)
    return out, prior


def spearman(pairs):
    if len(pairs) < 2:
        return 0.0

    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return r
    xs, ys = ranks([p[0] for p in pairs]), ranks([p[1] for p in pairs])
    n = len(pairs)
    mx, my = sum(xs) / n, sum(ys) / n
    sx = (sum((x - mx) ** 2 for x in xs)) ** 0.5
    sy = (sum((y - my) ** 2 for y in ys)) ** 0.5
    if sx == 0 or sy == 0:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def perm_pval(pooled, rho_pool):
    rng = random.Random(43)
    year_groups = defaultdict(list)
    for y, p, r in pooled:
        year_groups[y].append((p, r))
    count = 0
    for _ in range(PERMS):
        shuffled = []
        for pr in year_groups.values():
            rs = [r for _, r in pr]
            rng.shuffle(rs)
            shuffled.extend((p, r) for (p, _), r in zip(pr, rs))
        if spearman(shuffled) >= rho_pool:
            count += 1
    return count / PERMS


def backtest(autumns, qual):
    print("\n" + "=" * 72)
    print("C. WALK-FORWARD BACKTEST: does a time's past CLUSTER of instructors")
    print("   predict the quality of who you draw? (four granularities)")
    years = sorted(y for y in autumns if y < 2026)
    results = {}
    for name, keyf in GRAINS:
        pooled = []
        per_year = {}
        for y in years[1:]:
            hist = [h for h in years if h < y]
            pred, _ = slot_quality(hist, autumns, qual, y, keyf)
            pairs = []
            for s in autumns[y]:
                r = rate(s["who"], qual)
                k = keyf(s)
                if r is None or k not in pred:
                    continue
                pairs.append((pred[k][0], r))
            if len(pairs) >= 5:
                per_year[y] = (spearman(pairs), len(pairs))
                pooled.extend((y, p, r) for p, r in pairs)
        if name == "exact slot":
            for y, (rho, n) in sorted(per_year.items()):
                print(f"    {y}: rank corr {rho:+.2f} over {n} sections")
        if len(pooled) < 10:
            results[name] = (0.0, 1.0, len(pooled))
            continue
        rho_pool = spearman([(p, r) for _, p, r in pooled])
        results[name] = (rho_pool, perm_pval(pooled, rho_pool), len(pooled))

    print(f"\n  {'cluster':<12} {'rank corr':>9} {'perm p':>7} {'n':>5}")
    for name, (rho, p, n) in results.items():
        mark = "  <-- significant" if p < 0.05 and n >= 10 else ""
        print(f"  {name:<12} {rho:>+9.2f} {p:>7.3f} {n:>5}{mark}")
    print("  (p < .05: that clustering genuinely tilts your draw; p >= .05:")
    print("   indistinguishable from shuffling instructors within each year)")
    return results


def choose_grain(results):
    for name, keyf in GRAINS:
        rho, p, n = results.get(name, (0.0, 1.0, 0))
        if p < 0.05 and n >= 10:
            return name, keyf, rho, p, False
    name, keyf = GRAINS[0][0], GRAINS[0][1]
    rho, p, _ = results.get(name, (0.0, 1.0, 0))
    return name, keyf, rho, p, True


# ---------------------------------------------------------------- D
def ballot(autumns, qual, results):
    target = autumns.get(2026, [])
    if not target:
        print("\nNo Autumn 2026 rows - scrape Autumn 2026 first.")
        return
    name, keyf, rho, pval, weak = choose_grain(results)
    print("\n" + "=" * 72)
    print(f"D. AUTUMN 2026 BALLOT - ranked by '{name}' history "
          f"(rank corr {rho:+.2f}, p={pval:.3f}: "
          + ("usable tilt)" if not weak else
             "WEAK - order by schedule fit, not slot history)"))
    hist_years = sorted(y for y in autumns if y < 2026)
    pred, prior = slot_quality(hist_years, autumns, qual, 2026, keyf)
    print(f"HBC average instructor rating (the blind-draw baseline): "
          f"{prior:.2f}\n" if prior else "")

    scored = []
    for s in target:
        q, den = pred.get(keyf(s), (prior, 0.0))
        holders = Counter()
        for y in hist_years:
            for h in autumns[y]:
                if h["slot"] == s["slot"] and h["who"]:
                    holders[h["who"]] += 1
        detail = ", ".join(
            f"{pretty(w)} x{n}"
            + (f" ({qual[w[0]]['rating']:.2f})" if len(w) == 1 and w[0] in qual
               else "")
            for w, n in holders.most_common(4)) or "no history at this time"
        scored.append((q if q is not None else 0, den, s, detail))

    scored.sort(key=lambda t: (-t[0], -t[1]))
    print(f"{'rank':>4} {'sec':>4} {'meets':<22} {'E[rating]':>9} "
          f"{'evidence':>8}  past holders of this slot")
    for i, (q, den, s, detail) in enumerate(scored, 1):
        meets = f"{s['days']} {s['start']}"
        print(f"{i:>4} /{s['sec']:<3} {meets:<22} {q:>9.2f} {den:>8.1f}  {detail}")
    print("\n'evidence' = decay-weighted years of history behind that slot's")
    print("estimate; E[rating] shrinks toward the baseline when it is thin.")


def main():
    args = sys.argv[1:]
    db = "times.db"
    course = 12300
    if "--db" in args:
        db = args[args.index("--db") + 1]
    if "--course" in args:
        course = int(args[args.index("--course") + 1])

    rows = load_times(db)
    autumns = hbc_autumns(rows, course)
    qual = quality_table(rows)

    audit(rows, autumns, course)

    print("\n" + "=" * 72)
    print("B. INSTRUCTOR QUALITY TABLE (HBC sections in the feedback data)")
    for last, d in sorted(qual.items(), key=lambda kv: -kv[1]["rating"]):
        print(f"  {d['first']} {last.title():<16} rating {d['rating']:.2f} "
              f"over {d['n']} section(s), last {d['last_q']}")
    known = {last for last in qual}
    seen = {w for ss in autumns.values() for s in ss for w in s["who"]}
    blind = sorted(seen - known)
    if blind:
        print(f"  no feedback data (blind draws): {', '.join(b.title() for b in blind)}")

    results = backtest(autumns, qual)
    ballot(autumns, qual, results)


if __name__ == "__main__":
    main()
