# Quarterly Data Update — Runbook

Run this on your own computer (the Okta login step needs you). Everything is
manual-start but hands-off once running. Full detail lives in README.txt; this
is the short version.

## One-time setup (~10 min)

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

   (Windows: `venv\Scripts\activate` instead of `source venv/bin/activate`.)

## The update (run per feedback drop)

Currently missing: **Winter 2026** and **Spring 2026**.

```bash
# 1. Refresh the course catalog list (~3 min, no login needed).
#    Prints each department as it goes.
cd analyzeCourseFeedback/getCourseIDs
python scrape_courses.py

# 2. Get fresh cookies (~2 min). A Chrome window opens; log into Okta
#    normally (password + Duo), then leave the window alone — it closes
#    itself about a minute after opening.
cd ../../cookies
python getCookies.py

# 3. Collect feedback links for each missing quarter (~10 min per quarter)
cd ../analyzeCourseFeedback/getCourseLinks
python scrape_course_links_single_quarter.py "Winter 2026"
python scrape_course_links_single_quarter.py "Spring 2026"

# 4. Scrape the feedback reports (the long one — roughly 1-3 hours,
#    unattended; 12 Chrome windows will open and work in parallel).
#    If it starts erroring partway through, cookies expired: redo step 2,
#    then rerun this — it automatically skips anything already scraped.
cd ../scrapeFeedback
python scrapeFeedback.py

# 5. Data-quality tripwire (~seconds). If this FAILS, stop and investigate
#    (paste its output to Claude) before pushing anything.
cd ..
python data_quality_check.py

# 6. Recompute the precalculated averages (~1 min)
python calculate_averages.py

# 7. Copy the updated database to where the backend reads it
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
