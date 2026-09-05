# ROADMAP — The UChicago Registration Copilot

**Standing instruction: when told to "continue the roadmap," open this file,
pick the highest-priority unblocked item, do it, update the statuses here,
commit, and push. This file is the project's memory and its to-do list.**

---

## Product boundary (decision recorded 2026-09-04)

The project now has two separately released layers. The existing simple Chrome
extension and its aggregate API are the stable public/UChicago-community layer;
they must remain backward-compatible. The advanced Course Copilot site and its
planning, forecasting, preregistration, and reveal tools are invitation-only and
must run behind a separate access and deployment boundary.

See `PRODUCT_LAYERS.md` for the authoritative data boundary, publication gates,
probability language, staged rollout, and current implementation status. In
particular: raw comments and credentials never publish, neither layer automates
registration, and invitation-only access does not make an unvalidated
probability claim acceptable.

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
- **Regime C — observed single-instructor histories** (~201 of 664 established
  courses have one instructor in our coverage): no observed instructor choice,
  so optimize *timing and preparation* — which quarter and what to pair it
  with. Do not infer that no other instructor exists outside our coverage.

The regime is detectable from our own data (instructor history + dept lists).

## Non-negotiable principles

1. **Evidence, never accusations.** Show "sole observed instructor in our
   coverage since 2021" and "grading-fairness rated 0.3 below the course's
   other qualities; N grading-related comments." Never assert unverifiable
   claims about named people ("caps grades at B"). Everything displayed must
   trace to data.
2. **Comments are collected but never republished verbatim.** Display only
   aggregated/synthesized themes; link to the official feedback page for raw
   text so reading actual quotes requires the same UChicago login it does
   today. Students wrote them believing they'd stay behind that login.
3. **Sample sizes on every number.** A 4.9 from one section is not a 4.9 from
   twelve. Percentile ranks over raw scores where distributions are compressed.
4. **Honest uncertainty.** Every probability-like output names the event,
   evidence window, denominator, calibration status, and held-out score. When
   those are unavailable, display descriptive evidence or a clearly labeled
   heuristic tier, not a percentage. Multi-section courses get pool evidence,
   never a false single-name assignment probability.
5. **Never damage the source data.** Additive passes and in-place updates
   only; no deletes; `main` branch stays the untouched original; all work on
   `claude/explore-code-data-x8tkpa`. The installed extension and its API
   contract also remain untouched until a compatible change passes staging.
6. **No silent failures.** The 2025 platform migration silently cost two
   quarters of ratings before anyone noticed. Every scrape ends with a
   data-quality check (fraction of new rows with ratings/hours/instructors)
   that fails loudly.
7. **Student-serving posture.** Aggregate data, workload planning, and
   informed choice — not "beat the registrar" framing.

## Data foundation (current state)

- **course_feedback.db**: 23,641 course rows, 4,528 professors, 36,746
  teaching links; Autumn 2019 – Spring 2026 (COVID quarters excluded).
  These are raw database-row counts, not unique-report denominators: duplicate
  capture/repair rows remain to be merged by report URL before public display.
  Catalog cross-list canonicalization is a separate operation.
  The 2026-09-04 release gate also finds 11,137 teaching links whose course row
  no longer exists. Forensics account for 6,646 as redundant links whose
  relationships already survive elsewhere; the other 4,491 lack enough parent
  metadata to attach safely. A normalized derived database can exclude all of
  them while retaining a valid professor link for every one of the 19,349
  currently covered report URLs. The raw database remains blocked for release.
- Every surviving report row has at least one valid instructor link, and new
  scrape rows have 100% instructor/quarter coverage. The relational history is
  not clean because 11,137 legacy child links have missing course parents.
- Ratings (12 questions) + hours: healed through Spring 2026 as of
  2026-08-16. All rated rows are column-complete with hours; the only gap
  is ~2,596 graduate-form rows (W6) plus historical pre-2020 hours holes.
- Known quirks: ~1,378 rows with "Form N" quarter labels (excluded from
  time-based analysis); 77 same-department surname-collision groups whose
  members all have different first names (not evidence of identity splits);
  32 canonical courses with the same display name under multiple professor IDs
  require review; cross-listed courses remain fragmented across department
  listings (fix in W2/W4).

## Historical backtest baselines (the bar future work must beat)

Backtested on 9 held-out quarters (Autumn 2023 – Spring 2026):

These are historical experiment results preserved from the 2026-08 work. They
do not establish that `p_autumn_2026` or `instructor_conf` is a calibrated
probability, and they do not support exact-section assignment or registration-
allocation probabilities. A 2026-09 audit found that the generic production
labels overstate what the committed implementation proves; W4 now separates
the existing heuristics from the missing reproducible probability model.

- Course-offering forecast: 63–74% precision at p>=0.5 across five test
  quarters with the Terms-Offered exclusion signal (was 61–70% without;
  costs a few recall points; current-catalog terms on past quarters carry
  mild hindsight bias, so forward predictions are the honest use).
- Instructor prediction: 84–88% top-1 accuracy when model confidence >=70%
  (covers ~half of courses); 77–83% top-3 pool hit rate.
- URL-deduplicated per-section split: single-section courses 69.7–74.3%
  top-1; multi-section courses 16.3–26.0% across Autumn 2023 through Spring
  2026. The older 35–52% multi-section range was duplicate-biased and is
  invalid. These results do not justify a single-name exact-section inference.
- Archived pre-dedup fairness-gap baseline: average gap was ~0.00 across 664
  courses. It is not a release statistic: URL-level recomputation changes 532
  of 1,110 comparable gaps, with 23 courses crossing the current `-0.2` flag.

## Workstreams (priority order; check off and date as completed)

### W0. Preserve the public layer; isolate the advanced layer — IN PROGRESS 2026-09-04

- [x] Record the two-layer product decision, data boundaries, probability
      language, publication gates, and staged rollout in `PRODUCT_LAYERS.md`
- [x] Freeze the exact Chrome Web Store v3.0 extension source in a hash-pinned,
      deterministic allowlist package; capture its request and response shape
      in sanitized compatibility fixtures without changing the five source
      files (2026-09-04)
- [ ] Verify the exact deployed PythonAnywhere server artifact and data
      snapshot before any endpoint cutover
- [ ] Create a sanitized public release path that excludes credentials,
      authenticated captures, raw comments, personal plans, ballots, and
      internal handoffs from both release artifacts and history. The extension
      packager is complete; a fresh sanitized Git history/repository is not.
- [ ] Obtain written confirmation for publishing feedback-derived aggregates;
      add attribution, privacy, affiliation, contact, and takedown terms
- [ ] Correct public aggregates: URL deduplication, ID-based instructor joins,
      normalized teaching relationships, denominators, sample sizes, coverage
      wording, and as-of dates; run the data-quality tripwire. A route/schema-
      compatible read-only v2 API and release gate exist, but deployment is
      blocked until a derived artifact excludes the 11,137 legacy orphans and
      passes zero-dangling/zero-duplicate integrity gates. Surname-only identity
      input must remain null unless a reviewed full-name/ID path is available.
- [ ] Stage Layer 2 separately with server-side invitation access, isolated
      configuration/data, health checks, validation, safe logging, and no
      dependency on the extension's production service
- [x] Harden Layer 2's current interface: URL-deduplicated visible coverage
      counts, minimum evidence floors, tie-aware reveal ranks, bounded inputs,
      POSTed personal choices, unique program coverage counts, and suppression
      of the uncalibrated returner-only instructor guess on ranking pages
      (2026-09-04)
- [ ] Keep all registration actions advisory/read-only; seat watching may use
      the public guest portal, but no code may submit registration forms

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

### W2. Catalog enrichment — DONE 2026-08-16
- [x] Catalog details captured (`getCourseIDs/scrape_catalog_details.py`,
      snapshot in catalog.db): 6,255 entries — 6,028 descriptions, 5,708
      Terms Offered, 4,565 equivalents
- [x] Program requirement lists captured (4,150 references)
- [x] Cross-listing merge (`forecasting/identities.py`): 6,659 listings ->
      2,566 unified courses. Measured effect on instructor accuracy: ~zero
      (reports consistently file under their primary listing), so this is
      a product feature (unified course pages) not an accuracy lever.
- [x] Terms Offered in the forecaster — as an EXCLUSION signal only:
      trusting listed seasons as positive evidence hurt precision
      (aspirational data); halving probability for unlisted seasons raised
      precision in all 5 test quarters. Boost variant tested and rejected.
Still to use downstream: descriptions (topic search, W5), prerequisites
(planning, W5), requirement lists (monopoly warnings, W4/W5).

### W3. Rich capture pass (laptop run with cookies)
Script ready: `scrapeFeedback/capture_rich.py` (preview-gated, resumable,
session guard). Privacy architecture: raw comments -> gitignored local
comments.db, NEVER pushed (public repo, principle 2); only aggregates
(interest means, response counts, keyword comment_signals) go into
course_feedback.db for committing.
- [x] capture_rich.py run 2026-08-16: 9,396/9,396 sections, 342,767
      comments banked locally, ZERO errors; comment_signals aggregated for
      3,055 courses and pushed
- [x] Written comments -> local comments.db (keyword aggregates committed)
- [ ] Interest before/after -> columns (291 sections in v1 — stats-table
      forms only; College-form interest renders as chart images -> OCR
      variant is v2)
- [x] Response counts per section (2,841 sections; stats-table forms)
- [ ] Extend capture to pre-2025 quarters + fold into quarterly RUNBOOK
- [ ] New College-form questions worth keeping (class time value, lectures,
      discussions, stimulated interest)

### W4. Intelligence layer (no new data needed to start)
- [x] Generic historical offering heuristic v1 (`forecasting/forecast.py`);
      the stored `p_*` field is not yet a calibrated probability
- [x] Generic historical likely-instructor guess + backtest harness; it is
      course-level/pool evidence, not an exact-section assignment probability
- [x] Backtest + pressure-test harnesses (keep green as models change)
- [ ] Rebuild and calibrate reproducible offering and instructor-assignment
      models: rolling held-out evaluation, newcomer mass, stable professor IDs,
      assignment constraints, uncertainty intervals, and Brier/log scores
- [ ] Implement any exact-section Autumn 2026 scenario analysis now preserved
      only as prose in `HANDOFF_PREREG_AUTUMN2026.md`; until then its percentages
      remain heuristic scenario weights, not production model outputs
- [ ] Registration-allocation probability requires a new demand/rankings/
      priority-rules/outcomes dataset; no such model exists today
- [x] Pre-dedup one-instructor and fairness-gap signals exist in
      `forecasting/build_signals.py` -> `signals.db`; their current values are
      archived inputs, not release-ready aggregates
- [x] Pre-dedup regime classifier v1 exists (B = SOSC/HUMA for now; Civ needs
      W5 refinement). Its archived 859/63/1,042 split over 1,964 courses is
      inflated. The measured logical-report rebuild expectation is 799/62/564
      over 1,425 eligible courses, with 568 one-observed-instructor flags.
- [ ] Review the 32 canonical courses with the same display name under multiple
      professor IDs; never merge the 77 surname-collision groups automatically
- [x] Pre-dedup crowd-pleaser and Goldilocks scoring code exists (default
      weights 50/30/20). The archived 154 crowd-pleaser flags fall to 109 in
      the measured logical-report rebuild; all percentiles and flags must be
      regenerated before release.
- [ ] Comment parsing (after W3): themes, workload descriptions, grading
      complaints, "easy/hard" mentions -> structured signals + per-course
      synthesized summaries (LLM batch; respect principle 2)
- [x] Historical W2 terms-offered experiment and pressure-test rerun completed
      (2026-08-16). Its baselines are archived pending the ID-safe,
      logical-report rebuild; surname collisions are not merge evidence.

### W5. Product surfaces
- [x] Site v1 shipped 2026-08-16 (`site/`, run: `cd site && python app.py`
      -> 127.0.0.1:5050): search by code/topic, unified course pages with
      forecasts + comment signals + histories, goldilocks explorer with
      weight controls, regime/monopoly/crowd-pleaser badges
- [x] Site v2 (2026-08-16): path-first redesign — home starts from "pick
      your major"; /plan ranks each program's requirement pool (levels,
      prereq links, flags) and renders every Core area as a ranked
      lottery with pool medians. Courses show "counts toward" programs.
- [x] Unrestricted multi-select for majors, possible second majors, and minors
      on the home and `/plan` views (verified in code 2026-09-04)
- [ ] Site v3 remaining: professor pages, per-sequence lottery detail
      (variance, full instructor pool with ratings), "my remaining
      requirements" checklist, and an invitation-only deployment isolated from
      the extension's production service
- [x] Pre-reg list builder v1 (2026-08-16, /prereg): candidates -> ranked
      list with an additive risk heuristic, historical offering/instructor
      fields, and retakeability. Its percentages are not calibrated odds.
- [x] Hedged registration UI v1 (2026-08-16, `/prereg`): selects a fourth
      candidate using retakeability, rating percentile, and hours; totals the
      trial load; and sorts a drop order by retakeability
- [ ] Hedged portfolio model. The original 2026-08 roadmap entry described
      components (a)-(c) as implemented, but the 2026-09 code audit found no
      expected-best-three calculation, uncertainty propagation, or formal
      portfolio optimizer. Preserve these as the design target: (a) pair risky
      slots with a hedge that maximizes expected quality of the best three;
      (b) enforce a survivable trial-window workload budget; (c) combine
      revealed instructors, the student's impressions, and retakeability in a
      week-3 drop advisor. Etiquette: drop promptly once decided so the seat
      returns to the pool.
- [ ] Verify current-year hedge mechanics each autumn: exact drop/add
      deadlines, tuition and financial-aid treatment of a 4th course
- [x] Add/drop reveal check v1 (2026-08-16, /reveal): enter your revealed
      instructor -> rank in the course's historical pool + keep/swap
      advice (on-demand; automated alerts later)
- [ ] Extension maintenance/upgrades: first add API compatibility fixtures and
      fix missing/`Staff` instructor handling; then consider sample sizes as an
      additive field. Keep forecasts and advanced tools in Layer 2, and keep the
      production extension untouched until backward compatibility is verified
- [ ] Four-year planner (needs W2 requirements): remaining requirements ->
      which quarter to take what, workload-balanced

### W6. Graduate-form support
- [ ] Map the "Graduate Course Feedback" questionnaire onto our schema
      (needs a mapping decision — its questions differ semantically)
- [ ] Backfill the ~2,500 grad-form rows across recent quarters

### Coverage map (known dark zones — display honestly, never infer world absence)
- Intro MATH (13100-15300, 19620): our captured numeric/report coverage is
  effectively absent (35 links in the whole 15xxx band, 33 of them 15910).
  Label this "absent from our numeric coverage"; do not claim the sections were
  not surveyed or that reports do not exist outside the dataset.
- WRIT 10100: zero reports in the current database. This is a coverage fact,
  not proof that writing seminars do not run a survey.
- Language courses (LATN etc.): reports exist but use a form without the
  numeric tables our parser reads — comments capture works, ratings don't.
- SOSC-primary sections: numeric extraction sparse — form variant, queued.

### W7. Later / exploratory
- [x] SHIPPED (2026-08-18): section times. Class Search has a PUBLIC guest
      portal with terms back to Autumn 2016 — no login needed. Built in
      `analyzeCourseFeedback/getSectionTimes/`:
      `scrape_section_times.py` (dept-dropdown + pagination; times.db has
      HUMA 2016-2026 + BIOS/LATN Autumn 2026), `backtest_times.py`
      (verdict: slot->instructor NAMING is chance level, 8-10% vs a 62%
      returner ceiling), `slot_report.py` (cluster-quality tilt at four
      granularities: NOT significant, best p=.077 — ballots must not
      pretend otherwise; only sticky individuals matter: Fenno TTh 11
      x7yr, Martinez TTh 9:30 x4, Williams TTh 3:30 x3, Davey PhilPer
      9:30 x3), `verify_prereg.py` (user-driven browser, reads every
      tab/frame, confirmed the final Autumn 2026 ballot 11/11 against the
      live pre-reg system on 2026-08-18). Learned the hard way: the
      portal caps results at exactly 250 rows (8 terms incomplete —
      weekday-partitioned re-scrape queued), keyword search is NOT a dept
      filter, and pre-reg opens components in a second browser tab.
- [ ] Backfill the 8 terms clipped by the 250-row cap (partition queries
      by weekday checkboxes); then SOSC/PHIL/ECON times for winter tools.
- [ ] Conflict-free schedule optimizer ("maximize quality per hour that
      fits my calendar") — times.db + signals.db now make this buildable.
- [ ] Professor trajectory (improving/declining over quarters)
- [ ] Score Autumn 2026 predictions against reality when its feedback drops
      (~Dec 2026) — the first true out-of-sample test

## Division of labor

- **Christian (laptop, anything needing UChicago login or network):**
  cookie refresh (`cookies/getCookies.py`), scrape/repair/capture runs,
  pushing updated databases. Each run: `git pull`, run the script named in
  the current workstream, follow its printed wrap-up, `git push`.
- **Codex/agent (this branch):** everything else — code, models, analysis,
  verification, the site, this roadmap. The agent environment cannot
  reach UChicago sites (network policy) and cannot log in; scrapers are
  therefore written and tested-by-preview here, executed on the laptop.

## Quarterly rhythm (after feedback drops: late Dec / late Mar / mid Jul)

1. `RUNBOOK.md` update run (catalog -> cookies -> links -> feedback ->
   averages -> copy -> push)
2. Data-quality tripwire must pass (W1)
3. Agent: verify, retrain/re-backtest, regenerate predictions, update site
