"""Unified course identities from catalog cross-listings (Roadmap W2/W4).

The same class is often filed under several departments (LACS 26382 = HIST
26310 = CEGU 28900...). The feedback database treats each listing as a
separate course, fragmenting its history and suppressing forecast accuracy.
The catalog's "Equivalent Course(s)" field tells us which codes are the same
class; this module builds an alias map so every listing collapses onto one
canonical identity.

Usage:
    from identities import build_alias_map
    alias = build_alias_map()          # {} if catalog.db is absent
    canonical = alias.get(course, course)

Run directly for a report:  python identities.py
"""

import os
import re
import sqlite3
from collections import defaultdict

CATALOG_DB = os.path.join(os.path.dirname(__file__), "..",
                          "analyzeCourseFeedback", "getCourseIDs", "catalog.db")

# A cluster larger than this almost certainly comes from a bad equivalence
# chain (e.g. generic topics courses); we refuse to merge it.
MAX_CLUSTER = 15

CODE_RE = re.compile(r'([A-Z]{4})\s+(\d{5})')


def parse_code(text):
    m = CODE_RE.search(text.replace('\xa0', ' '))
    return (m.group(1), int(m.group(2))) if m else None


def build_alias_map(catalog_db=CATALOG_DB, verbose=False):
    """Return {(dept, course_id) -> canonical (dept, course_id)} for every
    non-canonical member of an equivalence cluster. Empty dict if the
    catalog snapshot isn't available."""
    if not os.path.exists(catalog_db):
        return {}

    conn = sqlite3.connect(f"file:{catalog_db}?mode=ro", uri=True)
    rows = conn.execute(
        "SELECT code, equivalents FROM catalog_courses WHERE equivalents != ''"
    ).fetchall()
    conn.close()

    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for code_text, equiv_text in rows:
        base = parse_code(code_text)
        if not base:
            continue
        for m in CODE_RE.finditer(equiv_text.replace('\xa0', ' ')):
            union(base, (m.group(1), int(m.group(2))))

    clusters = defaultdict(set)
    for member in list(parent):
        clusters[find(member)].add(member)

    alias = {}
    skipped = 0
    for members in clusters.values():
        if len(members) < 2:
            continue
        if len(members) > MAX_CLUSTER:
            skipped += 1
            if verbose:
                print(f"  skipping oversized cluster ({len(members)}): "
                      f"{sorted(members)[:6]}...")
            continue
        canonical = min(members)
        for member in members:
            if member != canonical:
                alias[member] = canonical

    if verbose:
        sizes = defaultdict(int)
        for members in clusters.values():
            if 2 <= len(members) <= MAX_CLUSTER:
                sizes[len(members)] += 1
        print(f"Alias map: {len(alias)} listings collapse into "
              f"{sum(sizes.values())} unified courses "
              f"(cluster sizes: {dict(sorted(sizes.items()))}; "
              f"{skipped} oversized clusters skipped)")

    return alias


if __name__ == "__main__":
    if not os.path.exists(CATALOG_DB):
        print(f"catalog.db not found at {CATALOG_DB} — run "
              f"scrape_catalog_details.py on the laptop and push it first.")
    else:
        build_alias_map(verbose=True)
