# ROADMAP — The UChicago Registration Copilot

**Standing instruction: when told to "continue the roadmap," open this file,
pick the highest-priority unblocked item, do it, update the statuses here,
commit, and push. This file is the project's memory and its to-do list.**

---

## North Star

UChicago students can no longer freely pick their professors — Sosc and Civ
hide instructor names at pre-registration (Hum too for first-years), a third
of the catalog only ever has one instructor, and allocation is a lottery. The
goal: **a system that gives a student the best possible decision at every
point where they still have control** — which courses to plan a year around,
exactly what to rank at pre-registration, and what to swap to at add/drop.
"Guaranteed best choices" is impossible (the lottery guarantees nothing);
provably best *decisions* under uncertainty is the buildable version.

The product loop, matched to how registration actually works (rank up to 10
courses in My Planner, multiple sections of one course rankable, algorithm
allocates, add/drop opens Monday of finals week):

1. **PLAN** (quarters ahead): forecast when each course will run and who will
   likely teach it, so students sequence their year around the good draws.
2. **RANK** (at pre-reg): build the optimal 10-slot ranked list.
3. **STRIKE** (at add/drop): the moment hidden instructor names publish,
   report the student's draw quality and the best available swap.
4. **TRIAL** (weeks 1–3): carry a 4-course hedged portfolio, then drop the
   weakest by the Friday-of-week-3 no-penalty deadline — converting the
   registration lottery into a three-week test drive (see W5 hedged mode).

## Regime-aware behavior (the system must adapt per course type)

- **Regime A — names visible** (most department courses): section-level
  scoring; rank exact sections; advise where the professor gap is big enough
  to fight for and where it's noise.
- **Regime B — names hidden** (Sosc + Civ for all, Hum for first-years):
  rank the *lotteries* — each sequence's instructor-pool median, spread, and
  workload; then own the add/drop reveal moment with alerts + swap advice.
- **Regime C — monopolies** (~201 of 664 established courses have exactly one
  instructor ever): nothing to choose, so optimize *timing and preparation* —
  which quarter, what to pair it with, what the grading reputation is.

The regime is detectable from our own data (instructor history + dept lists).

## Non-negotiable principles

1. **Evidence, never accusations.** Show "sole instructor since 2021;
   grading-fairness rated 0.3 below the course's other qualities; N
   grading-related comments." Never assert unverifiable claims about named
   people ("caps grades at B"). Everything displayed must trace to data.
2. **Comments are collected but never republished verbatim.** Display only
   aggregated/synthesized themes; link to the official feedback page for raw
   text so reading actual quotes requires the same UChicago login it does
   today. Students wrote them believing they'd stay behind that login.
3. **Sample sizes on every number.** A 4.9 from one section is not a 4.9 from
   twelve. Percentile ranks over raw scores where distributions are compressed.
4. **Honest uncertainty.** Every prediction ships with confidence, and
   confidence tiers are backtested (see baselines below). Multi-section
   courses get pool predictions, never a false single name.
5. **Never damage the source data.** Additive passes and in-place updates
   only; no deletes; `main` branch stays the untouched original; all work on
   `claude/explore-code-data-x8tkpa`.
6. **No silent failures.** The 2025 platform migration silently cost two
   quarters of ratings before anyone noticed. Every scrape ends with a
   data-quality check (fraction of new rows with ratings/hours/instructors)
   that fails loudly.
7. **Student-serving posture.** Aggregate data, workload planning, and
   informed choice — not "beat the registrar" framing.

## Data foundation (current state)

- **course_feedback.db**: 23,641 sections, 4,528 professors, 36,746
  teaching links; Autumn 2019 – Spring 2026 (COVID quarters excluded).
- Instructor + quarter data: complete and clean (100% coverage on new rows).
- Ratings (12 questions) + hours: healed through Spring 2026 as of
  2026-08-16. All rated rows are column-complete with hours; the only gap
  is ~2,596 graduate-form rows (W6) plus historical pre-2020 hours holes.
- Known quirks: ~1,378 rows with "Form N" quarter labels (excluded from
  time-based analysis); 77 professor identities split by name variants;
  cross-listed courses fragmented across dept listings (fix in W2/W4).

## Measured baselines (the bar future work must beat)

Backtested on 9 held-out quarters (Autumn 2023 – Spring 2026):

- Course-offering forecast: 65–71% top-1 precision at p>=0.5 (beats
  "same as last year" baseline on most quarters).
- Instructor prediction: 84–88% top-1 accuracy when model confidence >=70%
  (covers ~half of courses); 77–83% top-3 pool hit rate.
- Per-section honesty split: single-section courses 70–77% top-1;
  multi-section courses 35–52% per section — hence pool display for
  multi-section, single name only for single-section.
- Fairness-gap signal: average gap between the fairness rating and a
  course's other ratings is ~0.00 across 664 established courses, so
  deficits of 0.25+ are true outliers (harsh-grading fingerprint).

## Workstreams (priority order; check off and date as completed)

### W1. Heal & guard the data — DONE 2026-08-16
- [x] Diagnose post-migration damage (5/12 questions dead, hours dead,
      grad forms never supported)
- [x] Patch scraper for both question wordings, new image domain, cookies
- [x] Repair script with preview gate (`repair_rescrape.py`)
- [x] Full repair run completed on laptop (6,800 rows healed across two
      passes); healed DB pushed
- [x] Verify healed data end to end: the four damaged quarters now at
      70-75% coverage (reference quarters 82-84%; gap = grad forms). Of
      rated rows, 100% have all 12 columns and 100% have hours. 2,596
      grad-form rows remain empty pending W6. Production copy identical.
- [x] Post-scrape data-quality tripwire: `data_quality_check.py`
      (RUNBOOK step 5) — per-column and hours checks that would have
      caught the migration same-day
- [x] Expired-session guard ported into scrapeFeedback.py
- [x] Averages recomputed; Autumn 2026 predictions regenerated on healed
      data (981 courses at p>=0.5 with rating/hours context attached)

### W2. Catalog enrichment (public data, no login, ~minutes to run)
The catalog pages we already scrape for course IDs also contain, per course:
full **description**, **prerequisites**, **"Terms Offered"**, **"Equivalent
Course(s)"**, and the requirements lists for each major. Capture all of it.
- [ ] Extend catalog scraper: descriptions, prereqs, terms, equivalents
      (script ready: `getCourseIDs/scrape_catalog_details.py` — run on
      laptop, ~5 min, no login; then push catalog.db)
- [ ] Scrape major-requirement course lists per program page (same script,
      `program_courses` table)
- [ ] Merge equivalent/cross-listed courses into unified course identities
      (fixes fragmented history; improves forecasts and coverage)
- [ ] Feed "Terms Offered" into the offering forecaster
Unlocks: topic search, prerequisite-chain planning, required-course flags,
better forecasts.

### W3. Rich capture pass (laptop run with cookies)
The new report pages expose data we never stored. Additive backfill pass +
capture in all future quarterly scrapes:
- [ ] Written comments -> new `comments` table keyed to section
- [ ] Interest before/after questions -> two new columns (direct
      "interestingness" = interest delta)
- [ ] Response counts per section (true sample sizes)
- [ ] New College-form questions worth keeping (class time value, lectures,
      discussions, stimulated interest)

### W4. Intelligence layer (no new data needed to start)
- [x] Offering forecaster v1 (`forecasting/forecast.py`)
- [x] Instructor prediction with calibrated confidence
- [x] Backtest + pressure-test harnesses (keep green as models change)
- [x] Monopoly detection; fairness-gap (harsh grading) signal — as queries;
      productize into precomputed tables
- [ ] Regime classifier (A/B/C per course)
- [ ] Merge split professor identities (77 name-variant pairs)
- [ ] Crowd-pleaser index (high rating + low challenge + low hours + small
      class: the niche-survival pattern)
- [ ] Goldilocks scoring: percentile ranks on workload / challenge /
      interest / rating with user-tunable weights
- [ ] Comment parsing (after W3): themes, workload descriptions, grading
      complaints, "easy/hard" mentions -> structured signals + per-course
      synthesized summaries (LLM batch; respect principle 2)
- [ ] Improve forecaster with W2 terms-offered + merged identities;
      re-run pressure test and update baselines above

### W5. Product surfaces
- [ ] Site (Flask, deployable on PythonAnywhere like the existing backend):
      search, course pages, professor pages, goldilocks explorer with
      sliders, sequence-lottery ranker for Regime B, monopoly warnings
- [ ] Pre-reg list builder: user picks candidate courses -> optimal 10-slot
      ranked list with per-slot reasoning
- [ ] Hedged registration mode ("4-over-3"): the system permits 400 units
      (4 courses) and drops are penalty-free online until 5pm Friday of
      week 3 (adds/swaps until the same deadline; instructor consent needed
      late in the window) — so register 4 intending to drop 1. Components:
      (a) portfolio construction — pair each risky slot (hidden-name Core
      draw, new/unknown instructor, harsh-grader monopoly) with a hedge
      course, choosing the 4th course that maximizes expected quality of
      the best 3-course subset; (b) trial-window workload budget — carrying
      4 courses for 3 weeks must be survivable per our hours data; (c)
      week-3 drop advisor — weighs revealed instructors, the student's own
      impressions, and retakeability asymmetry (drop the course that runs
      every quarter; keep the rare offering or the rare great-professor
      pairing, per the forecaster). Etiquette: drop promptly once decided
      so the seat returns to the pool.
- [ ] Verify current-year hedge mechanics each autumn: exact drop/add
      deadlines, tuition and financial-aid treatment of a 4th course
- [ ] Add/drop reveal report: names just published -> draw quality +
      best-available swaps (start manual/on-demand, automate later)
- [ ] Extension upgrades: sample sizes in the widget; predicted
      instructor/pool display when the name field is hidden or "Staff";
      keep production extension untouched until the new one is tested
- [ ] Four-year planner (needs W2 requirements): remaining requirements ->
      which quarter to take what, workload-balanced

### W6. Graduate-form support
- [ ] Map the "Graduate Course Feedback" questionnaire onto our schema
      (needs a mapping decision — its questions differ semantically)
- [ ] Backfill the ~2,500 grad-form rows across recent quarters

### W7. Later / exploratory
- [ ] Section meeting times from course search -> conflict-free schedule
      optimizer ("maximize quality per hour that fits my calendar")
- [ ] Professor trajectory (improving/declining over quarters)
- [ ] Score Autumn 2026 predictions against reality when its feedback drops
      (~Dec 2026) — the first true out-of-sample test

## Division of labor

- **Christian (laptop, anything needing UChicago login or network):**
  cookie refresh (`cookies/getCookies.py`), scrape/repair/capture runs,
  pushing updated databases. Each run: `git pull`, run the script named in
  the current workstream, follow its printed wrap-up, `git push`.
- **Claude (this branch):** everything else — code, models, analysis,
  verification, the site, this roadmap. Claude's cloud environment cannot
  reach UChicago sites (network policy) and cannot log in; scrapers are
  therefore written and tested-by-preview here, executed on the laptop.

## Quarterly rhythm (after feedback drops: late Dec / late Mar / mid Jul)

1. `RUNBOOK.md` update run (catalog -> cookies -> links -> feedback ->
   averages -> copy -> push)
2. Data-quality tripwire must pass (W1)
3. Claude: verify, retrain/re-backtest, regenerate predictions, update site
