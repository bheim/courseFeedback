# Forecast and signal rebuild plan

This file records the reproducible work required before Course Copilot may
display probability-like outputs to invited guests. It also distinguishes code
that exists from calculations that were only performed interactively in the
previous Claude conversation.

Audit snapshot: 2026-09-04, aggregate database SHA-256
`43288e0742b9ec68696c538dc0292202187d6dee39832f1c3d82b37472b34203`, current
`signals.db` SHA-256
`b00a92c6db7bc632dd25da528d21ff29e5bab1c94dd2955346ab46a9fc024004`.

## What exists now

- `forecasting/forecast.py` produces a historical course-offering score and a
  top returning-instructor signal.
- Offering membership and instructor histories are stored as sets, so report
  duplication does not change the current score values or winning professor
  IDs.
- The current instructor calculation is by professor ID internally, but
  `signals.db` discards the winning ID and retains only a display name.
- `site/app.py` treats these fields as archived heuristics. List/ranking pages
  no longer show the instructor name; the course page labels it as historical
  concentration and says it excludes first-time instructors.

These are not calibrated exact-section probabilities. The returner-only
`instructor_conf` value is especially not a probability: across nine temporal
folds, 4,671 of 7,022 targets were evaluable; 44.2% of targets contained only
previously unseen instructor IDs, and a stored confidence of 1.0 realized only
87.6% accuracy.

## What existed only in the prior conversation

The exact-section instructor percentages, newcomer/downside distributions,
GOOD/AVOID weights, and robustness sweep preserved in
`HANDOFF_PREREG_AUTUMN2026.md` do not have a committed reproducible
implementation or versioned model artifact. They are heuristic scenario
weights, not production probabilities.

There is no model for a student's probability of receiving a class. The
repository has no historical demand, ranked ballots, priority rules as applied,
or allocation outcomes from which to estimate that event.

## Why the current signal snapshot must be rebuilt

The feedback database contains 23,641 course rows but 19,349 distinct report
URLs: 4,292 rows are duplicate capture/repair rows. These duplicated URLs have
the same raw department, course, and quarter; catalog cross-list
canonicalization is a separate operation. For parseable academic
quarters, 22,263 rows reduce to 17,980 logical reports.

After URL deduplication and the same three-report evidence floor:

| Measure | Current snapshot | Logical-report rebuild |
|---|---:|---:|
| Eligible courses | 1,964 | 1,425 |
| Regime A | 859 | 799 |
| Regime B | 63 | 62 |
| Regime C / one observed instructor | 1,042 | 564 |
| One-observed-instructor flag | 1,047 | 568 |

Correct report-level recomputation also changes 563 of 1,110 comparable course
ratings, 578 of 1,120 workload estimates, 560 challenge averages, and 532
fairness gaps. Twenty-three courses cross the current `-0.2` fairness-warning
threshold. Merely replacing `n_sections` with a distinct count is therefore
not sufficient.

Eleven duplicate URL groups contain complementary null/non-null captures.
Logical reports must coalesce complementary fields and reject conflicting
non-null values; selecting an arbitrary row can discard evidence.

Additional defects to correct in the rebuild:

- `build_signals.py` sorts season names lexically, making `last_quarter` wrong
  for 199 current signal rows.
- 11,137 of 36,746 `courses_professors` links reference absent course rows.
  Forensics account for 6,646 as redundant links left by non-cascading URL
  deduplication; their relationships already exist on surviving report rows.
  The other 4,491 came from an apparently interrupted duplicate scrape, and
  their missing parent metadata cannot be reconstructed safely. All 19,349
  current report URLs nevertheless retain at least one valid professor link.
- Thirty-two canonical courses contain the same display name under multiple
  professor IDs. Names and surnames must never be used to merge identities
  automatically.
- `pressure_test.py` calls 77 same-department surname collisions “name-variant
  splits,” but all 77 have different first names. That interpretation is
  invalid and cannot support a claim that accuracy is understated.
- The existing per-section backtest counts duplicate database rows. After URL
  deduplication, top-1 accuracy for Autumn 2023 through Spring 2026 is 38.7%,
  39.7%, 45.4%, 38.6%, 41.8%, 48.7%, 41.3%, 41.7%, and 49.7%.

## Rebuild sequence

1. Create an immutable derived logical-report layer keyed by report URL. Keep
   source-row provenance, coalesce complementary fields, and fail on conflicting
   non-null evidence. Never mutate the source database.
2. Build a normalized `report_professors` relation only from valid inner joins,
   unique on `(report_url, professor_id)`. Exclude—not reattach—the 11,137
   legacy orphans, and record their count plus source hashes in an anomaly
   manifest. This yields 20,909 distinct valid report/professor pairs from
   25,609 valid child rows without losing any currently covered report. Never
   mutate the source database.
3. Recompute `n_reports`, course ratings, dimension-specific denominators,
   response-weighted workload, percentiles, fairness gaps, and flags from the
   logical-report layer. Regenerate `signals.db` rather than patching columns.
4. Store professor IDs alongside display names. Add only a reviewed identity
   crosswalk for demonstrated splits; never infer identity from a surname.
5. Keep the current offering result named a historical score until offering
   truth is rebuilt from demonstrably complete schedule snapshots. Absence from
   feedback coverage is not a negative label.
6. Build instructor assignment at the correct event level. Preserve section
   frequencies, include an explicit newcomer/unknown class, and keep
   course-pool and exact-section events separate.
7. Evaluate with rolling as-of cutoffs and immutable input hashes. Report Brier
   score, log loss, calibration, coverage/abstention, and newcomer performance,
   each with denominators. Do not leak current catalog terms into historical
   folds unless an as-of catalog snapshot exists.
8. Only expose a percentage when the displayed event, evidence window,
   denominator, calibration status, and held-out result accompany it.

## Validation event definitions and release gate

- **Offering event:** for every course in a universe frozen before the cutoff,
  the positive outcome is at least one scheduled section in the target term.
  Only schedule snapshots demonstrated complete for that term may supply
  negatives; absence from feedback reports is never a negative label.
- **Exact-section instructor event:** the unit is a scheduled class number in a
  coverage-complete snapshot. The outcome is the listed professor ID set. For a
  co-taught section, evaluation uses a fractional target split equally across
  the listed IDs. Any listed ID unseen for that course before the cutoff maps to
  the explicit newcomer/unknown class. No-history and newcomer outcomes remain
  in every denominator.
- Predeclare seasonal-frequency and last-offering baselines for offering, and
  incumbent-frequency plus historical-newcomer-rate baselines for instructor
  assignment. Model selection and any calibration mapping use only an inner
  time split; the final held-out quarter is never used for tuning.
- On locked rolling folds, a percentage may ship only if both multiclass Brier
  score and log loss beat the best predeclared baseline, the course-clustered
  95% bootstrap interval for each improvement excludes zero, and the upper
  95% interval for expected calibration error is at most 0.10. Otherwise the
  interface must show a descriptive tier or abstain. Report reliability plots,
  raw and calibrated scores, coverage, and every denominator.
- Each fold records immutable hashes and as-of timestamps for the feedback,
  schedule, alias/cross-list map, reviewed identity map, and catalog inputs.
  A current catalog snapshot may not enter a historical fold.

## Required regression tests

- Duplicate-injection invariance.
- Complementary-field coalescing and conflicting-field rejection.
- Snapshot checks for 19,349 logical reports, 1,425 eligible courses, and 568
  one-observed-instructor courses on the audited database.
- Normalized relation checks for 20,909 unique report/professor pairs, zero
  dangling foreign keys, zero duplicate pairs, zero merge conflicts, and at
  least one professor link for every logical report.
- Distinct professor IDs for Benjamin and Agnes Callard and other shared
  surnames.
- Future-row mutation cannot change an earlier-fold prediction.
- Candidate assignment probabilities plus newcomer mass sum to one.
- Deterministic ties and complete artifact metadata/input hashes.
- Metric-specific sample sizes match the rows actually used by each output.

Aggregated comment signals cannot be deduplicated from the published
`comment_signals` table because it no longer retains report provenance. They
must be regenerated on the user's laptop from the local private comment store,
exporting only deduplicated aggregates and never raw text.
