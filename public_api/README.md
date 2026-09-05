# Public extension API v2

This directory contains the hardened, client-compatible API intended for the
public Course Feedback Chrome extension. It is separate from the guest-only
site and does not modify any extension source. The authoritative product and
publication boundary is in [PRODUCT_LAYERS.md](../PRODUCT_LAYERS.md).

## Deployment status

**Do not deploy this API against the current aggregate database.** As of
2026-09-04, `analyzeCourseFeedback/course_feedback.db` contains 36,746 rows in
`courses_professors`, of which 11,137 point to course IDs that no longer exist.
Forensics account for 6,646 as redundant relationships already represented on
surviving report rows. The other 4,491 have lost their parent metadata and
cannot be reattached safely. Excluding every orphan preserves a valid professor
relationship for all 19,349 report URLs currently in our coverage. The source
database must remain unchanged; a normalized derived artifact must exclude,
not guess or reattach, these rows.

That data defect is one release blocker, not the entire publication decision.
A release also requires a sanitized public repository with fresh Git history,
written authority to publish the feedback-derived aggregates plus attribution,
privacy, contact, and takedown terms, verification of the exact currently
deployed PythonAnywhere server artifact and data snapshot, and a live
compatibility check using the exact payload emitted by the published v3
extension. Passing the technical gate below does not satisfy those separate
requirements.

The API never reads raw student comments or credential/session files.

## Normalized-artifact integrity gate

The checker opens SQLite read-only and does not construct the Flask app. It
fails a release artifact that is empty or has any of the following:

- a failed SQLite `quick_check` or any foreign-key violation;
- a nonempty SQLite `-wal`, `-shm`, or `-journal` sidecar;
- a null or blank report URL, more than one row for a report URL, or conflicting
  non-null evidence among duplicate copies;
- a missing course/professor parent, duplicate physical teaching link, or
  duplicate `(report URL, professor ID)` relationship; or
- a report URL without at least one valid professor relationship.

It also calculates the exact database-file SHA-256 and logical hashes for
report evidence, professor identities, and report/professor relationships. A
versioned JSON manifest binds the expected counts and hashes to the artifact;
the live SQL checks still run, so a manifest cannot waive an integrity failure.

Inspect the current source database with:

```sh
source venv/bin/activate
python -m public_api.check_release_data
```

It intentionally exits nonzero. Validate a derived artifact and its manifest
with:

```sh
python -m public_api.check_release_data \
  --database /absolute/path/to/course_feedback.public.db \
  --manifest /absolute/path/to/course_feedback.public.manifest.json
```

Use `--json` for machine-readable output. A normalized build must emit the
manifest; do not hand-edit counts or hashes to make a failed artifact pass.

## Compatibility contract

- `GET /` returns the existing health string: `The Flask app is working!`
- `POST /get-course-feedback` accepts the array produced by
  `courseFeedbackLaunch/courseScrape.js`.
- Every input produces one output in the same order.
- The seven legacy response fields remain present:
  `courseId`, `course_rating`, `professor_rating`,
  `professor_course_rating`, `course_hours`,
  `professor_course_hours`, and `feedback_urls`.
- Staff, surname-only, unknown, or ambiguous instructors receive `null`
  instructor metrics instead of crashing the whole request.
- Additional sample-size and provenance fields are additive; the existing
  extension ignores them safely.

Requests are limited to 256 KiB, 250 items, 20 alternate listings per item, and
750 total course references. Course IDs, instructor strings, and listing strings
also have explicit length bounds.

## Evidence rules

- Evaluation evidence and counts are deduplicated by report URL. Duplicate
  copies may supply complementary null/non-null fields, but two different
  populated values for the same report field are an integrity error. The API
  fails closed instead of choosing a richest or newest row.
- Course ratings are rebuilt from the seven course dimensions.
- Instructor ratings are rebuilt from the five instructor dimensions.
- Instructor-by-course ratings use all twelve dimensions.
- Workload uses the seven stored hours-histogram buckets.
- `professors.avg_professor_rating` is never used because it is pooled by
  surname in this database.
- A surname-only value is never converted into a professor identity, even when
  the requested course has one historical surname match. The page may be
  showing a different or first-time instructor with that surname. Full names
  may be matched exactly to a professor ID within the requested course or
  department, but two matching IDs are treated as ambiguous rather than merged
  by name.
- Some real people have separate professor IDs across departments or name
  variants. Until an audited identity map exists, v2 deliberately returns null
  when more than one ID matches instead of merging records by name. This can
  suppress legitimate history, but it cannot assign one person's evaluations
  to another person.
- Multi-instructor metrics are report-weighted over the deduplicated union of
  reports, so their displayed report count is the true report-level denominator.
  If any named instructor cannot be resolved, all legacy instructor metrics are
  null rather than silently describing only the resolved subset.

## Local development

The local/test factory defaults to `analyzeCourseFeedback/course_feedback.db`
relative to the repository. It accepts an explicit path or the
`COURSE_FEEDBACK_DB_PATH` override so the current blocked source can still be
inspected and exercised locally:

```sh
source venv/bin/activate
export COURSE_FEEDBACK_DB_PATH=/absolute/path/to/course_feedback.db
flask --app public_api.app run
```

SQLite is opened with `mode=ro` and `PRAGMA query_only = ON`; the API cannot
create or modify database objects. The local factory is not the production
entrypoint and its ability to open the raw source database is not release
authorization.

## Guarded production startup

Production must import `public_api.release_wsgi:app`. Before creating the Flask
application, that entrypoint requires both environment variables below to be
explicit absolute paths and runs the manifest and live integrity checks:

```sh
export COURSE_FEEDBACK_DB_PATH=/absolute/path/to/course_feedback.public.db
export COURSE_FEEDBACK_ARTIFACT_MANIFEST=/absolute/path/to/course_feedback.public.manifest.json
```

Missing, relative, unreadable, malformed, mismatched, or structurally invalid
artifacts abort import before the service can listen. Configure the production
WSGI server to import `public_api.release_wsgi:app`; do not deploy
`public_api.app` as a way around this guard. `COURSE_FEEDBACK_RELEASE_MODE=1`
applies the same guard when the general factory must be used by a host.

Run the focused tests with:

```sh
source venv/bin/activate
python -m unittest -v tests.test_public_api_v2
```

Run the entire current test suite with:

```sh
source venv/bin/activate
python -m unittest discover -s tests -v
```

## Pre-deployment checklist

1. Verify and archive the exact deployed PythonAnywhere server artifact, its
   data snapshot, and the published extension's live request/response behavior.
2. Build a sanitized public repository with fresh history; do not publish this
   operating repository or assume deleting a file removes it from Git history.
3. Obtain written publication authority and add the required attribution,
   privacy, contact, and takedown terms.
4. Build the normalized derived database, excluding all 11,137 legacy orphan
   links without rewriting or guessing missing parents. Run
   `analyzeCourseFeedback/data_quality_check.py` as the source/scrape tripwire
   and the complete test suite; that tripwire does not replace the normalized
   artifact validator in step 5.
5. Generate the artifact manifest and require
   `python -m public_api.check_release_data --database ... --manifest ...` to
   pass with zero dangling links, duplicate reports/pairs, merge conflicts,
   unlinked reports, or sidecars.
6. Configure the production WSGI service with absolute database and manifest
   paths and import only `public_api.release_wsgi:app`.
7. Smoke-test the exact live payload emitted by the published v3 extension and
   compare the old and staged responses before cutover.
8. If the current Class Search page supplies only surnames, keep professor
   metrics null until a reviewed full-name/ID mapping is available; do not
   restore surname guessing for coverage.
9. Deploy separately from the guest-only application and keep the old endpoint
   available until the replacement passes a live compatibility check.

`tests/fixtures/public_api_v2_contract_cases.json` is a sanitized contract
fixture covering the legacy payload shapes and null behavior. It intentionally
does not claim to freeze production numeric values: those should change when the
aggregate database is refreshed. A final live payload/response capture remains
part of step 7 and must be performed by the user without sharing credentials.
