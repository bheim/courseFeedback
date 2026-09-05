# AGENTS.md — working agreement for this repo

Read this first. Then `ROADMAP.md` (standing goals) and, for the current
registration work, `HANDOFF_PREREG_AUTUMN2026.md`. `RUNBOOK.md` has the
operational scrape steps.

Owner: Christian Bricker, incoming UChicago first-year (Business
Economics + METI minor + Classical Studies minor planned). The project
is a course-feedback intelligence system: scrape UChicago evaluation
reports, catalog, and schedules; forecast offerings/instructors; help
pick courses and sections.

## Hard rules (do not violate)

1. **Never handle credentials.** Never enter, request, store, or ask for
   the user's password or second factor. Any tool that needs an
   authenticated session must open a browser the USER logs into, then
   read the page (see `verify_prereg.py` for the pattern).
2. **Raw student comments never reach the public repo.** `comments.db`
   (342,767 comments) is gitignored and stays local. Only aggregates are
   publishable. Same for `prereg_dump.txt` / `prereg_page.html`.
3. **Branch discipline.** Work on `claude/explore-code-data-x8tkpa`.
   Never push to `main`. Always `git pull --rebase` before pushing.
4. **No automated registration.** Seat *watchers* that poll the public
   guest portal are fine; scripts that submit registration forms are
   not — policy risk to the user and an unfair race against other
   students.
5. **Absence of coverage is not absence in the world.** `N=0` in a
   database means WE have no data, never "the course is new" or "never
   taught." This mistake has been made twice and corrected twice.

## Division of labor

- **User's laptop** (has UChicago network + login): all scraping, all
  authenticated work, pushes updated databases. Needs `source venv/bin/activate`.
- **Agent**: code, analysis, models, documents. Cloud sandboxes are
  EGRESS-BLOCKED from `*.uchicago.edu` — you cannot fetch the catalog,
  Class Search, or the portal. Web search works; some mirrors
  (`humanities-web.s3.us-east-2.amazonaws.com`) are reachable.

## Data

| Path | Contents |
|---|---|
| `analyzeCourseFeedback/course_feedback.db` | `courses` (12 rating dimensions, hours histogram, url, quarter), `professors`, `courses_professors`, `comment_signals` |
| `analyzeCourseFeedback/scrapeFeedback/comments.db` | **GITIGNORED** — raw comments keyed to `section_id` |
| `analyzeCourseFeedback/getCourseIDs/catalog.db` | `catalog_courses` (title, units, terms_offered, prerequisites, description), `program_courses` |
| `analyzeCourseFeedback/getSectionTimes/times.db` | `section_times` — term, dept, course, section, days, times, instructor, enrolled/capacity, class_number |
| `forecasting/signals.db` | `course_signals` — 26 derived columns incl. `p_autumn_2026`, `likely_instructor`, regime |

## Query hygiene (learned the hard way)

- **Join on professor IDs, never surnames.** Multiple people share
  surnames (Benjamin vs Agnes Callard; Arnold vs Benjamin Brooks;
  Jenifer Gifford [BIOS] vs Lindsay Gifford [HMRT]). Also
  `professors.avg_professor_rating` is POOLED BY SURNAME — never use it.
- **Deduplicate by report URL.** Course rows are duplicated 2-3x when a
  report is cross-listed; comment counts inflate the same way. All
  comment counts reported before 2026-08-20 are upper bounds.
- `avg_course_hours` / `avg_course_rating` are course-level aggregates
  replicated onto each section row. Per-instructor values live in
  `courses_professors.avg_prof_course_*`. Per-section values are the 12
  dimension columns and the hours histogram.
- Language courses (LATN, GREK partly) and intro MATH (13100-15300,
  19620) use a form variant with NO numeric tables — comments only or
  nothing. Known dark zone, documented in ROADMAP.

## Scripts

- `analyzeCourseFeedback/getSectionTimes/scrape_section_times.py` —
  PUBLIC guest portal, no login. `python scrape_section_times.py "Autumn 2026" HUMA BIOS`.
  Portal caps results at 250 rows/term; 8 terms are known-truncated.
- `.../verify_prereg.py` — user-driven authenticated browser; reads every
  tab and iframe; never touches credentials.
- `.../backtest_times.py`, `.../slot_report.py` — walk-forward validation.
- `analyzeCourseFeedback/scrapeFeedback/scrapeFeedback.py` — evaluation
  scraper, needs `cookies/getCookies.py` first (sessions last 2-3 hrs).
- `analyzeCourseFeedback/data_quality_check.py` — tripwire; run after scrapes.
- `forecasting/*.py` — offering/instructor prediction.
- `site/app.py` — Flask UI on port 5050.

## Analytical standards

Established through repeated external audit; hold to them.

- **Label heuristics as heuristics.** No calibrated probability model
  exists for instructor assignment. Any percentage is a *heuristic
  scenario weight* unless it comes with a held-out score.
- **Validated findings**: predicting an instructor's NAME from a time
  slot is chance level (8-10% vs a 62% returner ceiling, 143 predictions,
  10 autumns). Aggregate slot-quality effects are NOT significant
  (best p=.077). The usable signal is (a) measured return hazards and
  (b) a handful of individually sticky instructors, plus exclusion of
  slots owned by low-rated regulars.
- **Newcomer distributions matter**: first-time instructors are ~40-50%
  of any Hum section's probability mass. Measured first-year outcomes:
  Poetry 50% good / 25% avoid; PhilPer 43/39; HBC 40/46; BIOS
  non-majors 9/80 (note: thresholds calibrated on Hum, BIOS runs lower).
- Separate **exact-course evidence** from **same-instructor transfer
  evidence** in every report. Say which is which.
- No grade distributions exist anywhere in the data. "GPA-safe" is not a
  claim this system can make.

## Communication style the user wants

Matter-of-fact. Course NAMES not just numbers. Numbers with their
denominators. Caveats stated once, not repeatedly. Give a
recommendation, not a survey of options. When he says "no shortcuts,"
recompute from raw data and show the sweep.
