# Release notes

## Public API v2 — unreleased

This release introduces a hardened replacement backend for the existing public
Chrome extension without changing the extension package, routes, or response
schema. Surname-only instructor inputs deliberately return null rather than a
potentially misattributed rating.

### Added

- Environment-configurable aggregate database path with a safe repository
  default.
- SQLite URI read-only mode plus query-only enforcement.
- Bounded, typed JSON validation while retaining the 250-row portal capacity.
- One ordered response per request item, including Staff and unknown
  instructors.
- Report-URL deduplication before metrics and evidence counts are calculated.
- Professor-ID-based metrics with explicit ambiguity handling and no broad
  surname fallback.
- Null professor metrics for surname-only inputs rather than guessing a person
  from historical course evidence.
- Null instructor metrics for partially resolved multi-instructor fields, plus
  report-weighted multi-instructor metrics whose report count is the actual
  report-level denominator.
- Fail-closed duplicate handling: complementary null/non-null report fields are
  coalesced, while conflicting populated values block the release gate and
  produce a service-unavailable response instead of an arbitrary winner.
- Additive report counts, known response counts, match status, methodology, and
  data-through provenance.
- Bulk request prefetching to keep the maximum accepted course-reference
  workload bounded; the regression test completes well under its 10-second
  ceiling on the development machine.
- A standalone, side-effect-free normalized-artifact checker covering SQLite
  health, nonempty sidecars, empty artifacts, report-URL uniqueness, dangling
  parents, physical and logical relationship duplicates, conflicting report
  evidence, and reports without a valid professor relationship.
- A strict, versioned artifact manifest binding file size, exact database
  SHA-256, logical report/professor/relationship hashes, and integrity counts;
  manifest validation never replaces the live SQL checks.
- A fail-closed production WSGI entrypoint that requires explicit absolute
  database and manifest paths and rejects an invalid artifact before Flask can
  serve requests. The permissive default database remains available only to
  the local/test factory.
- Integration tests against the checked-in aggregate database.

### Removed from the request path

- Use of the pooled-by-surname `professors.avg_professor_rating` field.
- Per-request wildcard profiling and profiler output.
- Write-capable SQLite connections.
- Silent dropping of malformed course IDs that shifted response indexes.

### Remaining release blockers

The 2026-09-04 aggregate database has **11,137 dangling course links among
36,746 `courses_professors` rows**. Of these, 6,646 are redundant relationships
already present on surviving report rows; the remaining 4,491 cannot be safely
reattached because their parent metadata is gone. Excluding every orphan still
leaves all 19,349 covered report URLs with a valid professor relationship. Do
not deploy v2 against the raw database: first generate a normalized derived
artifact and matching manifest, then pass the expanded gate with zero dangling
links, duplicate reports or pairs, merge conflicts, unlinked reports, and
SQLite sidecars.

That normalized artifact is only one publication gate. Release remains blocked
until the exact deployed PythonAnywhere server and data snapshot are archived,
the published extension's live payload/response behavior is verified, a
sanitized public repository with fresh Git history is prepared, and written
authority plus attribution, privacy, contact, and takedown terms cover the
feedback-derived aggregates. See [PRODUCT_LAYERS.md](../PRODUCT_LAYERS.md) for
the complete Layer 1/Layer 2 boundary and staged rollout.
