# Course Copilot (invitation-only layer)

This Flask application is Layer 2 of the project. It is separate from the
public Chrome extension and must not share the extension's production process,
database copy, or availability boundary.

## Current deployment status

**Local prototype only. Do not expose this application to the internet yet.**
It has no server-side invitation authentication. An unlisted URL, a robots
rule, or a client-side password would not satisfy the access requirement.

The current `forecasting/signals.db` snapshot was built before report-URL
deduplication. The interface now uses distinct report URLs for visible coverage
counts and evidence thresholds, suppresses instructor guesses on ranking pages,
and labels the archived forecast fields as heuristics. Its stored aggregate
ratings, percentiles, flags, and forecasts still require a reproducible
deduplicated rebuild before deployment.

## Local run

From the repository root:

```sh
source venv/bin/activate
python site/app.py
```

Open `http://127.0.0.1:5050`. The checked-in databases are opened read-only.
Raw comments, authenticated captures, credentials, and session material are
not application inputs and must never be copied into a deployment.

Run the site regression tests with:

```sh
source venv/bin/activate
python -m unittest -v tests.test_guest_site
```

Before an invitation deployment, complete the Layer 2 gates in
`PRODUCT_LAYERS.md`: rebuild the aggregates/models, add server-side invitation
access, isolate configuration and data, add production error handling and safe
logging, and deploy to staging before inviting anyone.
