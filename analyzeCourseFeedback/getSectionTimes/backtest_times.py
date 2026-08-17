"""Backtest: how predictable is 'which time slot gets which instructor'?

Walk-forward test on times.db (run scrape_section_times.py --all-terms HUMA
first). For each Autumn year Y it uses ONLY years before Y to predict every
section's instructor, then scores against what actually happened. No
leakage, no shortcuts: every rule is scored over every section, misses
included.

Rules tested
    slot_recent  the instructor who most recently taught this exact
                 (course, days, start time) slot in a prior autumn
    slot_freq    the most frequent instructor in that slot across all
                 prior autumns
    sec_recent   the instructor who had this section NUMBER last autumn
    ceiling      share of this year's instructors seen in ANY prior autumn
                 (no rule can beat this - new hires are unpredictable)

Then the same rules are applied to Autumn 2026's sections, whose
instructors pre-registration hides.

    python backtest_times.py                    # HUMA 12300 (HBC)
    python backtest_times.py HUMA 11500 12000   # specific courses
    python backtest_times.py HUMA --all         # every course in the dept
"""

import re
import sqlite3
import sys
from collections import Counter

DB = "times.db"
PREDICT_TERM_YEAR = 2026

SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv"}
HIDDEN = {"staff", "tbd", "to be announced", "instructor tbd", ""}


def norm_names(instructor):
    """'Castro, Jr.' -> ('castro',); 'Doostdar, El Shakry' -> both names."""
    parts = [p.strip().lower() for p in (instructor or "").split(",")]
    parts = [p for p in parts if p and p not in SUFFIXES and p not in HIDDEN]
    return tuple(sorted(parts))


def pretty(names):
    return " + ".join(p.title() for p in names) if names else "(hidden)"


def load(dept, courses):
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = conn.execute(
        """SELECT term, course_id, section, instructor, days, start_time
           FROM section_times WHERE dept = ?""", (dept,)).fetchall()
    conn.close()
    autumns = {}
    for term, cid, sec, instr, days, start in rows:
        m = re.match(r"Autumn (\d{4})", term or "")
        if not m or not days:
            continue
        if courses is not None and cid not in courses:
            continue
        try:
            sec_n = int(sec)
        except (TypeError, ValueError):
            sec_n = sec
        autumns.setdefault(int(m.group(1)), []).append(
            {"cid": cid, "sec": sec_n, "who": norm_names(instr),
             "slot": (cid, days, start), "days": days, "start": start})
    return autumns


def build_history(autumns, before_year):
    slot_recent, sec_recent = {}, {}
    slot_freq = {}
    known = set()
    for y in sorted(y for y in autumns if y < before_year):
        for s in autumns[y]:
            if not s["who"]:
                continue
            slot_recent[s["slot"]] = s["who"]
            slot_freq.setdefault(s["slot"], Counter())[s["who"]] += 1
            sec_recent[(s["cid"], s["sec"])] = s["who"]
            known.add(s["who"])
    return slot_recent, slot_freq, sec_recent, known


def main():
    args = sys.argv[1:]
    dept = args[0] if args else "HUMA"
    if "--all" in args:
        courses = None
    else:
        nums = [int(a) for a in args[1:] if a.isdigit()]
        courses = set(nums) if nums else {12300}

    autumns = load(dept, courses)
    years = sorted(y for y in autumns if y < PREDICT_TERM_YEAR
                   and any(s["who"] for s in autumns[y]))
    label = "--all" if courses is None else ", ".join(map(str, sorted(courses)))
    print(f"{dept} [{label}] - autumns with instructor data: {years}")
    if len(years) < 2:
        sys.exit("Need at least two autumns in times.db. "
                 "Run: python scrape_section_times.py --all-terms " + dept)

    print(f"\n{'year':>6} {'n':>4} {'ceiling':>8} {'slot_recent':>12} "
          f"{'slot_freq':>10} {'sec_recent':>11} {'slot seen':>10}")
    agg = Counter()
    for y in years[1:]:
        slot_recent, slot_freq, sec_recent, known = build_history(autumns, y)
        c = Counter()
        for s in autumns[y]:
            if not s["who"]:
                continue
            c["n"] += 1
            c["ceiling"] += s["who"] in known
            c["covered"] += s["slot"] in slot_recent
            c["slot_recent"] += slot_recent.get(s["slot"]) == s["who"]
            if s["slot"] in slot_freq:
                c["slot_freq"] += slot_freq[s["slot"]].most_common(1)[0][0] == s["who"]
            c["sec_recent"] += sec_recent.get((s["cid"], s["sec"])) == s["who"]
        if not c["n"]:
            continue
        agg.update(c)
        print(f"{y:>6} {c['n']:>4} {c['ceiling'] / c['n']:>7.0%} "
              f"{c['slot_recent'] / c['n']:>11.0%} {c['slot_freq'] / c['n']:>9.0%} "
              f"{c['sec_recent'] / c['n']:>10.0%} {c['covered'] / c['n']:>9.0%}")
    if agg["n"]:
        print(f"{'TOTAL':>6} {agg['n']:>4} {agg['ceiling'] / agg['n']:>7.0%} "
              f"{agg['slot_recent'] / agg['n']:>11.0%} "
              f"{agg['slot_freq'] / agg['n']:>9.0%} "
              f"{agg['sec_recent'] / agg['n']:>10.0%} {agg['covered'] / agg['n']:>9.0%}")
        print("\nRead: 'ceiling' = instructor returned from a prior autumn at all;")
        print("rules can only be right when the instructor is a returner.")

    target = autumns.get(PREDICT_TERM_YEAR, [])
    if not target:
        print(f"\nNo Autumn {PREDICT_TERM_YEAR} rows in times.db yet - scrape it, "
              "then rerun this for the section-by-section forecast.")
        return

    revealed = [s for s in target if s["who"]]
    if revealed:
        print(f"\nAutumn {PREDICT_TERM_YEAR}: {len(revealed)}/{len(target)} sections "
              "ALREADY SHOW instructors on Class Search - no prediction needed there:")
    slot_recent, slot_freq, sec_recent, _ = build_history(autumns, PREDICT_TERM_YEAR)
    print(f"\nAutumn {PREDICT_TERM_YEAR} section forecast "
          "(history through the latest scraped autumn):")
    for s in sorted(target, key=lambda s: (s["cid"], str(s["sec"]))):
        line = f"  {dept} {s['cid']}/{s['sec']:<3} {s['days']:<12} {s['start']:>9}"
        if s["who"]:
            print(f"{line}  LISTED: {pretty(s['who'])}")
            continue
        by_slot = slot_recent.get(s["slot"])
        freq = slot_freq.get(s["slot"], Counter())
        by_sec = sec_recent.get((s["cid"], s["sec"]))
        held = freq[by_slot] if by_slot else 0
        parts = []
        if by_slot:
            parts.append(f"slot says {pretty(by_slot)} (held slot {held}x)")
        if by_sec and by_sec != by_slot:
            parts.append(f"section # says {pretty(by_sec)}")
        if not parts:
            parts.append("no history for this slot - genuine unknown")
        print(f"{line}  {'; '.join(parts)}")


if __name__ == "__main__":
    main()
