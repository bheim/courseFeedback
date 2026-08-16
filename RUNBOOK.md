# Quarterly Data Update — Runbook

Run this on your own computer (the Okta login step needs you). Everything is
manual-start but hands-off once running. Full detail lives in README.txt; this
is the short version.

## One-time setup

1. Install [Google Chrome](https://www.google.com/chrome/) if you don't have it.
2. Install Tesseract (used to read the hours-per-week histogram images):
   - Mac: `brew install tesseract`
   - Windows: https://github.com/UB-Mannheim/tesseract/wiki
3. Clone the working branch and install Python deps:

   ```bash
   git clone -b claude/explore-code-data-x8tkpa https://github.com/bheim/courseFeedback.git
   cd courseFeedback
   python3 -m venv venv && source venv/bin/activate
   pip install -r requirements.txt
   ```

## Per-quarter update (run once per missing quarter)

Currently missing: **Winter 2026** and **Spring 2026**.

```bash
# 1. Get fresh cookies (~2 min). A Chrome window opens; log into Okta
#    normally, then leave the window alone until the script closes it.
cd cookies
python getCookies.py

# 2. Collect feedback links for the quarter (~10 min per quarter)
cd ../analyzeCourseFeedback/getCourseLinks
python scrape_course_links_single_quarter.py "Winter 2026"
python scrape_course_links_single_quarter.py "Spring 2026"

# 3. Scrape the feedback reports (the long one — roughly 1-3 hours,
#    unattended; 12 Chrome windows will open and work in parallel).
#    If it starts erroring partway through, cookies expired: rerun
#    getCookies.py, then rerun this — it automatically skips anything
#    already scraped.
cd ../scrapeFeedback
python scrapeFeedback.py

# 4. Recompute the precalculated averages (~1 min)
cd ..
python calculate_averages.py

# 5. Copy the updated database to where the backend reads it
cp course_feedback.db ../courseFeedBackExtensionProduction/course_feedback.db
```

## Push the results

```bash
cd ..   # repo root
git add analyzeCourseFeedback courseFeedBackExtensionProduction
git commit -m "data update: Winter 2026 + Spring 2026"
git push
```

Note: `cookies/cookies.pkl` is untracked on purpose (it's your login
session) — don't force-add it.
