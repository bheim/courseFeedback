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


def q(db, sql, args=()):
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, args).fetchall()
    conn.close()
    return rows


def signal_row(dept, cid):
    rows = q(SIGNALS_DB, "SELECT * FROM course_signals WHERE dept=? AND course_id=?",
             (dept, cid))
    return rows[0] if rows else None


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
    top = q(SIGNALS_DB, """SELECT * FROM course_signals
        WHERE goldilocks IS NOT NULL AND n_sections >= 4
        ORDER BY goldilocks DESC LIMIT 10""")
    talked = q(SIGNALS_DB, """SELECT * FROM course_signals
        WHERE n_comments > 0 ORDER BY n_comments DESC LIMIT 10""")
    return render_template("index.html", query=query, results=results,
                           top=top, talked=talked)


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
    return render_template("course.html", dept=dept, cid=cid, sig=sig, cat=cat,
                           history=history, listings=listings,
                           feedback_url=feedback_url)


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
