"""The registration copilot site (Roadmap W5) — local-first Flask app.

Serves the precomputed signal layer plus course histories:
  /                   search + headline lists
  /course/<dept>/<id> unified course page (aliases collapse onto canonical)
  /explore            goldilocks explorer with tunable weights

Run locally:
    cd site && python app.py     ->  http://127.0.0.1:5050
(5050 because macOS AirPlay squats on 5000.)

Reads all databases read-only; safe to run alongside anything else.
"""

import os
import re
import sys
import sqlite3

from flask import Flask, abort, redirect, render_template, request, url_for

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, "..", "forecasting"))
from identities import build_alias_map  # noqa: E402

SIGNALS_DB = os.path.join(BASE, "..", "forecasting", "signals.db")
FEEDBACK_DB = os.path.join(BASE, "..", "analyzeCourseFeedback", "course_feedback.db")
CATALOG_DB = os.path.join(BASE, "..", "analyzeCourseFeedback", "getCourseIDs", "catalog.db")

app = Flask(__name__)

ALIAS = build_alias_map()
REVERSE_ALIAS = {}
for member, canonical in ALIAS.items():
    REVERSE_ALIAS.setdefault(canonical, []).append(member)

SEASON_ORDER = {"Winter": 0, "Spring": 1, "Summer": 2, "Autumn": 3}

# The Core requirement areas are catalog pages we scraped like any program
CORE_PAGES = {
    'humanities': 'Humanities Core',
    'socialsciences': 'Social Sciences Core',
    'civilizationstudies': 'Civilization Studies',
    'artscore': 'Arts Core',
    'biologicalsciencescore': 'Biological Sciences Core',
    'physicalsciences': 'Physical Sciences Core',
    'mathematicalsciencescore': 'Mathematical Sciences Core',
}
HIDDEN_NAME_CORE = {'humanities', 'socialsciences', 'civilizationstudies'}

CODE_RE = re.compile(r'([A-Z]{4})\s+(\d{5})')


def q(db, sql, args=()):
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, args).fetchall()
    conn.close()
    return rows


# Load once at startup: all signals in memory, program pools, reverse lookup
SIGNALS = {(r["dept"], r["course_id"]): dict(r)
           for r in q(SIGNALS_DB, "SELECT * FROM course_signals")}

# Course titles from the catalog, keyed by canonical identity
TITLES = {}
for _r in q(CATALOG_DB, "SELECT code, title FROM catalog_courses WHERE title != ''"):
    _m = CODE_RE.search(_r["code"])
    if _m:
        _k = ALIAS.get((_m.group(1), int(_m.group(2))), (_m.group(1), int(_m.group(2))))
        TITLES.setdefault(_k, _r["title"])


def ctitle(dept, cid):
    return TITLES.get(ALIAS.get((dept, cid), (dept, cid)), "")


@app.context_processor
def _inject_helpers():
    return dict(ctitle=ctitle)


PROGRAM_POOLS = {}          # program -> [canonical course keys]
PROGRAM_SECTIONS = {}       # program -> {section heading -> [canonical keys]}
PROGRAMS_BY_COURSE = {}     # canonical course -> [program names]
try:
    _rows = q(CATALOG_DB, "SELECT program, section, code FROM program_courses")
except sqlite3.OperationalError:   # pre-upgrade snapshot without sections
    _rows = [{"program": r["program"], "section": "", "code": r["code"]}
             for r in q(CATALOG_DB, "SELECT program, code FROM program_courses")]
for row in _rows:
    m = CODE_RE.search(row["code"])
    if not m:
        continue
    key = ALIAS.get((m.group(1), int(m.group(2))), (m.group(1), int(m.group(2))))
    pool = PROGRAM_POOLS.setdefault(row["program"], [])
    if key not in pool:
        pool.append(key)
    if row["section"]:
        sec = PROGRAM_SECTIONS.setdefault(row["program"], {}).setdefault(row["section"], [])
        if key not in sec:
            sec.append(key)
    PROGRAMS_BY_COURSE.setdefault(key, [])
    if row["program"] not in PROGRAMS_BY_COURSE[key]:
        PROGRAMS_BY_COURSE[key].append(row["program"])

MAJORS = sorted(p for p in PROGRAM_POOLS if p not in CORE_PAGES)


def signal_row(dept, cid):
    return SIGNALS.get((dept, cid))


def ranked_pool(program):
    """Signal rows for a program's requirement pool, best goldilocks first;
    also returns how many pool courses lack enough data to rank."""
    rated, unrated = [], 0
    for key in PROGRAM_POOLS.get(program, []):
        sig = SIGNALS.get(key)
        if sig and sig.get("goldilocks") is not None:
            rated.append(sig)
        else:
            unrated += 1
    rated.sort(key=lambda s: -s["goldilocks"])
    return rated, unrated


def prereq_codes(text):
    if not text:
        return []
    seen, out = set(), []
    for m in CODE_RE.finditer(text):
        key = (m.group(1), int(m.group(2)))
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


# canonical "DEPT NNNNN" -> [prerequisite course keys], from the catalog
PREREQS = {}
for _row in q(CATALOG_DB, "SELECT code, prerequisites FROM catalog_courses "
                          "WHERE prerequisites != ''"):
    _m = CODE_RE.search(_row["code"])
    if not _m:
        continue
    _key = ALIAS.get((_m.group(1), int(_m.group(2))), (_m.group(1), int(_m.group(2))))
    _codes = prereq_codes(_row["prerequisites"])
    if _codes:
        PREREQS.setdefault(f"{_key[0]} {_key[1]}", _codes)


def catalog_entry(dept, cid):
    codes = [f"{dept} {cid}"] + [f"{d} {c}" for d, c in REVERSE_ALIAS.get((dept, cid), [])]
    for code in codes:
        rows = q(CATALOG_DB, "SELECT * FROM catalog_courses WHERE code=? LIMIT 1", (code,))
        if rows:
            return rows[0]
    return None


@app.route("/")
def home():
    query = request.args.get("q", "").strip()
    results = None
    if query:
        results = search(query)
    return render_template("index.html", query=query, results=results,
                           majors=MAJORS, core_pages=CORE_PAGES)


def rank_keys(keys):
    rated = [SIGNALS[k] for k in keys if k in SIGNALS
             and SIGNALS[k].get("goldilocks") is not None]
    rated.sort(key=lambda s: -s["goldilocks"])
    unrated = len(keys) - len(rated)
    return rated, unrated


@app.route("/plan")
def plan():
    # Any number of paths: majors, second majors, minors-in-waiting — the
    # multi-select has no restrictions
    paths = [p for p in request.args.getlist("path") if p in PROGRAM_POOLS]
    legacy = request.args.get("major", "")
    if legacy in PROGRAM_POOLS and legacy not in paths:
        paths.append(legacy)
    core = request.args.get("core", "")

    path_views = []
    for program in paths:
        sections = PROGRAM_SECTIONS.get(program)
        groups, unrated_total = [], 0
        if sections:
            # Requirement-section grouping: tracks, specializations, minors.
            # Track definitions ("Summary of Requirements...") lead; sample
            # schedules are advisory duplicates and are skipped.
            def sec_key(name):
                low = name.lower()
                if "summary of requirements" in low:
                    return (0, name)
                if "minor" in low:
                    return (1, name)
                return (2, name)

            for sec_name in sorted(sections, key=sec_key):
                if "sample program" in sec_name.lower():
                    continue
                rated, unrated = rank_keys(sections[sec_name])
                unrated_total += unrated
                if rated:
                    groups.append((sec_name, rated))
        else:
            rated, unrated_total = ranked_pool(program)
            by_level = {}
            for sig in rated:
                level = f"{(sig['course_id'] // 10000) * 10000}-level"
                by_level.setdefault(level, []).append(sig)
            groups = sorted(by_level.items())
        path_views.append({"name": program, "groups": groups,
                           "unrated": unrated_total,
                           "has_sections": bool(sections)})

    core_sections = []
    selected_cores = [core] if core in CORE_PAGES else list(CORE_PAGES)
    for page in selected_cores:
        rated, unrated = ranked_pool(page)
        if not rated:
            continue
        pool_ratings = [s["avg_rating"] for s in rated if s["avg_rating"]]
        median = sorted(pool_ratings)[len(pool_ratings) // 2] if pool_ratings else None
        core_sections.append({
            "page": page, "label": CORE_PAGES[page],
            "hidden": page in HIDDEN_NAME_CORE,
            "rows": rated[:15], "n_total": len(rated), "unrated": unrated,
            "median": median,
        })

    return render_template("plan.html", paths=paths, majors=MAJORS,
                           path_views=path_views, core_sections=core_sections,
                           core=core, core_pages=CORE_PAGES,
                           prereqs_by_code=PREREQS)


def search(query):
    m = re.match(r"^([A-Za-z]{4})\s*(\d{0,5})$", query)
    if m:
        dept = m.group(1).upper()
        if m.group(2):
            like = f"{m.group(2)}%"
            return q(SIGNALS_DB, """SELECT * FROM course_signals
                WHERE dept=? AND CAST(course_id AS TEXT) LIKE ?
                ORDER BY course_id LIMIT 40""", (dept, like))
        return q(SIGNALS_DB, """SELECT * FROM course_signals WHERE dept=?
            ORDER BY course_id LIMIT 60""", (dept,))
    # Title/description search through the catalog, joined back to signals
    like = f"%{query}%"
    hits = q(CATALOG_DB, """SELECT code FROM catalog_courses
        WHERE title LIKE ? OR description LIKE ? LIMIT 120""", (like, like))
    out, seen = [], set()
    for hit in hits:
        m2 = re.match(r"([A-Z]{4})\s+(\d{5})", hit["code"])
        if not m2:
            continue
        key = (m2.group(1), int(m2.group(2)))
        key = ALIAS.get(key, key)
        if key in seen:
            continue
        seen.add(key)
        row = signal_row(*key)
        if row:
            out.append(row)
        if len(out) >= 40:
            break
    return out


@app.route("/course/<dept>/<int:cid>")
def course(dept, cid):
    dept = dept.upper()
    canonical = ALIAS.get((dept, cid))
    if canonical:
        return redirect(url_for("course", dept=canonical[0], cid=canonical[1]))

    sig = signal_row(dept, cid)
    cat = catalog_entry(dept, cid)
    if not sig and not cat:
        abort(404)

    members = [(dept, cid)] + REVERSE_ALIAS.get((dept, cid), [])
    placeholders = " OR ".join("(c.dept=? AND c.course_id=?)" for _ in members)
    params = [x for m in members for x in m]

    history = q(FEEDBACK_DB, f"""
        SELECT c.quarter,
               COUNT(DISTINCT c.id) AS n_sections,
               ROUND(AVG(c.excellence), 2) AS avg_excellence,
               GROUP_CONCAT(DISTINCT p.first_name || ' ' || p.last_name) AS instructors
        FROM courses c
        LEFT JOIN courses_professors cp ON cp.course_id = c.id
        LEFT JOIN professors p ON p.id = cp.professor_id
        WHERE ({placeholders})
          AND (c.quarter LIKE 'Autumn %' OR c.quarter LIKE 'Winter %'
               OR c.quarter LIKE 'Spring %' OR c.quarter LIKE 'Summer %')
        GROUP BY c.quarter""", params)

    def quarter_key(row):
        season, year = row["quarter"].split()
        return int(year) * 4 + SEASON_ORDER[season]

    history = sorted(history, key=quarter_key, reverse=True)
    listings = ", ".join(f"{d} {c}" for d, c in REVERSE_ALIAS.get((dept, cid), []))
    feedback_url = (f"https://coursefeedback.uchicago.edu/?CourseDepartment={dept}"
                    f"&CourseNumber={cid}")
    programs = [CORE_PAGES.get(p, p) for p in PROGRAMS_BY_COURSE.get((dept, cid), [])]
    prereqs = prereq_codes(cat["prerequisites"] if cat else "")
    return render_template("course.html", dept=dept, cid=cid, sig=sig, cat=cat,
                           history=history, listings=listings,
                           feedback_url=feedback_url, programs=programs,
                           prereqs=prereqs)


def risk_profile(sig):
    """0-100 risk that this pick disappoints, with human-readable reasons."""
    score, reasons = 0, []
    if sig["regime"] == "B":
        score += 30
        reasons.append("hidden-name Core — your instructor is a lottery draw")
    elif (sig.get("instructor_conf") or 0) < 0.5:
        score += 25
        reasons.append("uncertain instructor forecast")
    if (sig.get("grading_pct") or 0) >= 15:
        score += 20
        reasons.append(f"grading raised in {sig['grading_pct']}% of comments")
    if sig["monopoly"] and (sig.get("fairness_gap") or 0) <= -0.2:
        score += 25
        reasons.append("monopoly with depressed fairness rating")
    if sig["n_sections"] < 4:
        score += 15
        reasons.append("thin history")
    if sig.get("p_autumn_2026") is not None and sig["p_autumn_2026"] < 0.5:
        score += 10
        reasons.append("may not be offered in Autumn")
    return min(score, 100), reasons


def retake_profile(sig):
    """How costly is it to drop this course and take it later?"""
    nq = sig["n_quarters"]
    if nq >= 10:
        return "runs constantly — cheap to drop", 3
    if nq >= 5:
        return "runs regularly", 2
    return "rare offering — avoid dropping", 1


@app.route("/prereg")
def prereg():
    raw = request.args.get("candidates", "")
    keep = int(request.args.get("keep", 3) or 3)
    try:
        max_load = float(request.args.get("max_load", 45) or 45)
    except ValueError:
        max_load = 45.0

    entries, missing, seen = [], [], set()
    for m in CODE_RE.finditer(raw.upper()):
        key = ALIAS.get((m.group(1), int(m.group(2))), (m.group(1), int(m.group(2))))
        if key in seen:
            continue
        seen.add(key)
        sig = SIGNALS.get(key)
        if not sig:
            missing.append(f"{key[0]} {key[1]}")
            continue
        risk, reasons = risk_profile(sig)
        retake_text, retake_score = retake_profile(sig)
        entries.append({"sig": sig, "risk": risk, "reasons": reasons,
                        "retake_text": retake_text, "retake_score": retake_score})
        if len(entries) >= 12:
            break

    entries.sort(key=lambda e: -(e["sig"]["rating_pctl"] or 0))

    hedge = None
    if len(entries) > keep:
        top = entries[:keep]
        rest = entries[keep:]
        riskiest = max(top, key=lambda e: e["risk"])
        hedge_pick = max(rest, key=lambda e: (e["retake_score"],
                                              e["sig"]["rating_pctl"] or 0,
                                              -(e["sig"]["avg_hours"] or 99)))
        trial_load = sum(e["sig"]["avg_hours"] or 0 for e in top) + \
            (hedge_pick["sig"]["avg_hours"] or 0)
        drop_order = sorted(top + [hedge_pick],
                            key=lambda e: -e["retake_score"])
        hedge = {"riskiest": riskiest, "pick": hedge_pick,
                 "trial_load": round(trial_load, 1),
                 "over_budget": trial_load > max_load,
                 "worth_it": riskiest["risk"] >= 35,
                 "drop_order": drop_order}

    return render_template("prereg.html", raw=raw, keep=keep, max_load=max_load,
                           entries=entries, missing=missing, hedge=hedge)


@app.route("/reveal")
def reveal():
    dept = request.args.get("dept", "").strip().upper()
    cid_raw = request.args.get("cid", "").strip()
    name = request.args.get("name", "").strip()

    pool, match, course_key = None, None, None
    if dept and cid_raw.isdigit():
        course_key = ALIAS.get((dept, int(cid_raw)), (dept, int(cid_raw)))
        members = [course_key] + REVERSE_ALIAS.get(course_key, [])
        placeholders = " OR ".join("(c.dept=? AND c.course_id=?)" for _ in members)
        params = [x for m in members for x in m]
        pool = q(FEEDBACK_DB, f"""
            SELECT p.first_name || ' ' || p.last_name AS name,
                   COUNT(DISTINCT c.id) AS n_sections,
                   ROUND(AVG(c.excellence), 2) AS course_exc,
                   ROUND(MAX(p.avg_professor_rating), 2) AS prof_rating
            FROM courses c
            JOIN courses_professors cp ON cp.course_id = c.id
            JOIN professors p ON p.id = cp.professor_id
            WHERE ({placeholders})
            GROUP BY p.id
            HAVING course_exc IS NOT NULL OR n_sections >= 1
            ORDER BY (course_exc IS NULL), course_exc DESC""", params)
        if name and pool:
            low = name.lower()
            for i, row in enumerate(pool, 1):
                if low in row["name"].lower():
                    match = {"row": row, "rank": i, "of": len(pool)}
                    break

    return render_template("reveal.html", dept=dept, cid=cid_raw, name=name,
                           pool=pool, match=match, course_key=course_key)


@app.route("/explore")
def explore():
    def num(name, default):
        try:
            return float(request.args.get(name, default))
        except ValueError:
            return default

    wq = num("wq", 5)          # quality weight
    wl = num("wl", 3)          # lightness weight
    wc = num("wc", 2)          # challenge weight
    max_hours = num("max_hours", 40)
    min_sections = int(num("min_sections", 4))
    dept = request.args.get("dept", "").strip().upper()
    regime = request.args.get("regime", "")
    hide_pleasers = request.args.get("hide_pleasers", "")

    rows = q(SIGNALS_DB, """SELECT * FROM course_signals
        WHERE rating_pctl IS NOT NULL AND hours_pctl IS NOT NULL
          AND challenge_pctl IS NOT NULL AND avg_hours <= ?
          AND n_sections >= ?""", (max_hours, min_sections))

    total_w = max(wq + wl + wc, 1)
    scored = []
    for r in rows:
        if dept and r["dept"] != dept:
            continue
        if regime and r["regime"] != regime:
            continue
        if hide_pleasers and (r["crowd_pleaser"] or 0) >= 40:
            continue
        score = (wq * r["rating_pctl"] + wl * (100 - r["hours_pctl"])
                 + wc * r["challenge_pctl"]) / total_w
        scored.append((round(score), r))
    scored.sort(key=lambda t: -t[0])

    return render_template("explore.html", scored=scored[:60], wq=wq, wl=wl, wc=wc,
                           max_hours=max_hours, min_sections=min_sections,
                           dept=dept, regime=regime, hide_pleasers=hide_pleasers,
                           n_total=len(scored))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=False)
