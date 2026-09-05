# Product layers and release boundary

**Decision recorded 2026-09-04:** continue the project as two related but
separately released products. The existing Chrome extension remains the stable
public/community product. Course Copilot remains an invitation-only product
while its data, security, and probability work matures.

This boundary is a standing constraint for future work. A change to Course
Copilot must not silently change the extension or its API.

## Layer 1 — stable public/community extension

Layer 1 is the existing simple Chrome extension and the aggregate API that
serves it. It should continue doing the job it has done for UChicago students:
showing course and instructor feedback context inside Class Search.

- Preserve the installed extension's current API route, request shape,
  response fields, field meanings, and handling of missing values.
- Treat backward compatibility as a release gate. Additive fields are allowed
  only when old clients continue to work unchanged.
- Keep the production extension untouched while changes are developed and
  tested against a staging API and a copy of the production data.
- Publish only permitted aggregate outputs. Never return raw student comments,
  authenticated page captures, or credentials.
- Data refreshes and defect fixes are in scope. Advanced planning, forecasting,
  preregistration, and personalized recommendation features are not added to
  this layer merely because they exist in the same repository.

The extension code and its aggregate backend currently live in the
`courseFeedbackLaunch/`, `courseFeedbackExtension/`, and
`courseFeedBackExtensionProduction/` areas. Before changing any of them, first
identify the exact deployed client and server artifacts and freeze their
observable API behavior with compatibility tests.

## Layer 2 — invitation-only Course Copilot

Layer 2 is the advanced application under `site/` plus the catalog, forecasting,
schedule, preregistration, reveal, and future planning tools that support it.
It is for explicitly invited guests, on a separate deployment and access
boundary from Layer 1.

- Use a separate host or service, configuration, database copy, and deployment
  process. A Layer 2 failure must not interrupt the extension.
- Require real server-side access control before hosting it. An unlisted URL is
  not access control.
- Keep experimental signals visibly labeled and dated. Invitation-only access
  does not relax evidence, privacy, or accuracy standards.
- Do not automate course registration or submit registration forms. The product
  may analyze choices and may watch the public guest portal for seats.
- Do not treat an invited guest's inputs, schedule, or academic plans as
  publishable data. Retain as little personalized data as the feature permits.

Invitation-only is the current product decision, not a temporary euphemism for
public access. Any later expansion requires an explicit decision after the
publication gates below are satisfied.

## Data boundary

| Data class | Layer 1 | Layer 2 | Repository/release rule |
|---|---|---|---|
| Aggregate ratings, workload, and defensible sample sizes | Allowed after publication review | Allowed | Publish only corrected, deduplicated aggregates |
| Catalog and public Class Search schedule data | Only if needed for the extension | Allowed | Record source and as-of date |
| Derived forecasts and recommendation signals | Out of scope | Experimental, with evidence labels | Never present a heuristic as a calibrated probability |
| Raw student comments (`comments.db`) | Never | Never | Local and gitignored; do not ship or expose |
| Passwords and second factors | Never | Never | The agent never requests, enters, reads, or stores them |
| User-created session cookies and other authenticated session material | Never deploy or expose | Never deploy or expose | User-laptop only, transient, gitignored, and never inspected or published by the agent |
| Authenticated captures (`prereg_dump.txt`, `prereg_page.html`) | Never | Never | Local only and gitignored |
| Personal ballots, schedules, plans, and internal handoffs | Never | Only for the invited user's session when needed | Exclude from public release artifacts and logs |

Aggregating restricted source material does not by itself settle whether it may
be published. Written confirmation on publishing feedback-derived aggregates is
a gate for any new or refreshed public release.

## Probability and recommendation language

There are three separate questions, and the product must keep them separate:

1. **Will the course be offered?** A generic historical offering score exists.
   It is a heuristic, not a calibrated probability.
2. **Who may teach it?** A historical likely-instructor guess exists. It is not
   an exact-section assignment probability, does not adequately model newcomers,
   and must not be displayed as one.
3. **Will this student receive it?** No allocation-probability model exists. We
   do not have the demand, rankings, priority rules, and allocation outcomes
   required to estimate this honestly.

The detailed Autumn 2026 instructor/downside weights in
`HANDOFF_PREREG_AUTUMN2026.md` preserve a previous interactive analysis. The
repository does not currently contain a reproducible implementation or model
artifact for those calculations. They remain heuristic scenario weights until
rebuilt from raw aggregate evidence, versioned, and evaluated on held-out data.

Every probability-like output must state what event it estimates, its evidence
window and denominator, whether it is calibrated, and its out-of-sample score.
If those are unavailable, use descriptive evidence or a clearly named
heuristic tier instead of a percentage.

## Publication gates

Layer 1 maintenance and Layer 2 invitations move forward only through explicit
gates:

1. **Credential and history hygiene:** release artifacts and Git history contain
   no cookies, authenticated captures, raw comments, or personal plans. Use a
   sanitized release repository/history rather than assuming a later deletion
   erases an earlier secret.
2. **Publication authority:** obtain written confirmation for the intended use
   of feedback-derived aggregates and document attribution, privacy, contact,
   and takedown terms.
3. **Aggregate correctness:** merge duplicate captures by report URL,
   canonicalize catalog cross-lists as a separate step, join instructors by
   stable IDs rather than surnames, derive a normalized relationship table that
   excludes unresolvable legacy orphans, recalculate denominators, run the
   scrape data-quality tripwire, and separately require a normalized-artifact
   manifest and integrity gate. The scrape tripwire alone does not validate a
   release database.
4. **Honest interface:** show sample sizes and as-of dates; say "not present in
   our coverage" rather than inferring that a course is new or never taught;
   make no grade-distribution or GPA-safety claims.
5. **Layer 1 compatibility:** contract and regression tests pass against the
   deployed extension's request/response behavior, including `Staff`, missing
   instructors, cross-lists, and missing feedback.
6. **Layer 2 isolation:** invitation enforcement, separate configuration and
   deployment, input validation, health checks, error handling, and logs that do
   not capture sensitive user data are in place.
7. **Model evidence:** experimental forecasts are reproducible and their labels
   match their validation. Exact percentages remain hidden when calibration has
   not been demonstrated.
8. **Operational safety:** no registration submission automation is present;
   authenticated scraping remains user-driven on the user's laptop.

## Staged rollout

1. **Freeze and verify Layer 1.** Inventory the deployed extension/API, add
   compatibility fixtures, fix correctness and missing-instructor failures, and
   refresh aggregates without changing the user-visible contract.
2. **Create a sanitized release path.** Separate public artifacts from private
   operating documents and local-only data; complete publication review.
3. **Stage Layer 2 privately.** Deploy Course Copilot behind invitation access
   on infrastructure isolated from the extension. Initially emphasize search,
   catalog, aggregates, and clearly labeled descriptive evidence.
4. **Rebuild the probability layer.** Implement the previous one-off analysis as
   reproducible code, include newcomer mass and assignment constraints, and use
   rolling held-out evaluation and calibration metrics.
5. **Expand only by decision.** After observing the private product and clearing
   the gates, decide feature by feature whether anything beyond the original
   extension belongs in the community layer.

## Current status (2026-09-04)

- Layer 1 exists as the long-running Chrome extension and PythonAnywhere
  aggregate backend. Version 3.0 of the production client is now frozen by an
  exact file/hash manifest and deterministic allowlisted packager; none of its
  five source files changed. A route/schema-compatible staging API and sanitized
  contract fixtures now cover ordinary, cross-listed, `Staff`, unknown,
  ambiguous, multi-instructor, and no-numeric-feedback cases.
- The staging API deliberately returns null professor metrics for surname-only
  instructor text rather than guessing an identity. Before cutover, verify what
  the live Class Search DOM supplies and design a reviewed full-name/ID path if
  needed; correctness takes precedence over preserving a misattribution.
- The replacement API is not deployable against the raw current database yet.
  Its integrity gate finds 11,137 dangling course links among 36,746
  `courses_professors` rows. Of these, 6,646 are redundant relationships from
  non-cascading URL deduplication and 4,491 cannot be safely reattached because
  their parent metadata is gone. Excluding all of them in a normalized derived
  database preserves every one of the 19,349 currently covered report URLs.
  That derived artifact, its anomaly manifest, the exact PythonAnywhere server
  artifact, and the cutover data snapshot still need to be built or verified.
- Layer 2 is a working local prototype, not an invitation-ready deployment. It
  has search, course pages, program/Core views, unrestricted major/minor
  multi-select, an explorer, a preregistration toolkit, and reveal lookup.
- Layer 2 now displays report-URL-deduplicated coverage counts, requires at
  least three distinct reports in ranking pools, suppresses the uncalibrated
  returner-only instructor guess on list/ranking pages, uses metric-specific evidence
  counts and tie-aware ranks in reveal, bounds inputs, and keeps personal plan,
  preregistration, and reveal values out of query strings. The stored ratings,
  percentiles, flags, and forecast snapshot itself still requires a fully
  deduplicated rebuild.
- The preregistration risk score and 4-over-3 hedge are simple deterministic
  rules. They do not implement the roadmap's previously claimed expected-best-
  three optimizer, uncertainty propagation, or formal portfolio optimization.
- Generic offering and likely-instructor heuristics exist. Reproducible
  exact-section instructor probabilities and registration-allocation
  probabilities do not.
- Raw comments and authenticated preregistration captures remain local-only.
  A fresh sanitized public Git history, publication confirmation, a normalized
  aggregate artifact, invitation access, isolated staging, and a reproducible
  probability engine remain open work.
