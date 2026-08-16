"""Repair ratings and hours for quarters scraped after the platform migration.

Everything scraped since mid-2025 (Spring 2025, Autumn 2025, Winter 2026,
Spring 2026) is missing 5 of 12 ratings and all hours data because the
feedback platform reworded its questions. scrapeFeedback.py has been patched
to understand both wordings; this script re-visits the damaged rows and
UPDATES their rating/hours columns in place. It never deletes rows and never
touches instructor data, so nothing can be lost.

It starts with a 3-report preview so you can sanity-check the extraction
before committing to the full multi-hour run.

Run from this folder with fresh cookies:

    python repair_rescrape.py
"""

import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from scrapeFeedback import create_driver, processLink, processBioLink

DB_PATH = '../course_feedback.db'
BROKEN_QUARTERS = ('Spring 2025', 'Autumn 2025', 'Winter 2026', 'Spring 2026')
NUM_WORKERS = 10

RATING_COLS = ["challenge_intellect", "purpose", "standards", "feedback", "fairness",
               "respect", "excellence", "organization", "challenge", "available",
               "inclusive", "significant"]
HOUR_COLS = ["less_five", "five_to_ten", "ten_to_fifteen", "fifteen_to_twenty",
             "twenty_to_twenty_five", "twenty_five_to_thirty", "more_thirty"]

db_lock = threading.Lock()


def broken_rows():
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    rows = conn.execute(f"""
        SELECT id, dept, quarter, course_id, url FROM courses
        WHERE quarter IN (?,?,?,?) AND challenge_intellect IS NULL
    """, BROKEN_QUARTERS).fetchall()
    conn.close()
    return rows


# Reports scraped before the platform migration carry old-domain links. The
# old domain still renders the page but no longer serves the chart images, so
# hours extraction fails there. The same report ID resolves on the new domain
# — try that first, and fall back to the original link if it doesn't.
OLD_PREFIX = 'https://uchicago.bluera.com/uchicago/'
NEW_PREFIX = 'https://my-uchicago-bc.bluera.com/'


def migrate_url(url):
    if url.startswith(OLD_PREFIX):
        return url.replace(OLD_PREFIX, NEW_PREFIX, 1)
    return url


def scrape_one(driver, dept, url):
    process = processBioLink if dept == "BIOS" else processLink
    migrated = migrate_url(url)
    if migrated != url:
        try:
            result = process(driver, migrated)
            if result:
                return result
        except Exception:
            pass  # report not available on the new domain; use the old link
    return process(driver, url)


def has_data(course_data):
    if any(course_data.get(c) is not None for c in RATING_COLS):
        return True
    return any(course_data.get(c) for c in HOUR_COLS)


def update_row(row_id, course_data):
    cols = RATING_COLS + HOUR_COLS
    assignments = ", ".join(f"{c} = ?" for c in cols)
    values = [course_data.get(c) for c in cols] + [row_id]
    with db_lock:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.execute(f"UPDATE courses SET {assignments} WHERE id = ?", values)
        conn.commit()
        conn.close()


def preview(driver):
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    picks = []
    queries = [
        ("College form, Winter 2026",
         "SELECT id, dept, quarter, course_id, url FROM courses WHERE quarter='Winter 2026' "
         "AND standards IS NOT NULL AND dept != 'BIOS' LIMIT 1"),
        ("BIOS form, Winter 2026",
         "SELECT id, dept, quarter, course_id, url FROM courses WHERE quarter='Winter 2026' "
         "AND dept='BIOS' LIMIT 1"),
        ("College form, Spring 2025 (old-domain URL — tests that old links still resolve)",
         "SELECT id, dept, quarter, course_id, url FROM courses WHERE quarter='Spring 2025' "
         "AND standards IS NOT NULL AND dept != 'BIOS' LIMIT 1"),
    ]
    for label, q in queries:
        row = conn.execute(q).fetchone()
        if row:
            picks.append((label, row))
    conn.close()

    print("\n--- PREVIEW: extracting 3 sample reports (no database writes yet) ---")
    for label, (row_id, dept, quarter, cid, url) in picks:
        print(f"\n[{label}] {dept} {cid} ({quarter})")
        try:
            all_data = scrape_one(driver, dept, url)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue
        if not all_data:
            print("  -> no data extracted")
            continue
        cd = all_data["course_data"]
        ratings = {c: cd.get(c) for c in RATING_COLS if cd.get(c) is not None}
        hours = {c: cd.get(c) for c in HOUR_COLS if cd.get(c)}
        print(f"  ratings extracted ({len(ratings)}/12): {ratings}")
        print(f"  hours distribution: {hours if hours else 'NONE — hours/OCR still broken'}")
    print("\n--- END PREVIEW ---")


def worker(worker_id, driver, rows):
    fixed = empty = errors = consecutive = 0
    for row_id, dept, quarter, cid, url in rows:
        try:
            all_data = scrape_one(driver, dept, url)
            consecutive = 0
            if all_data and has_data(all_data["course_data"]):
                update_row(row_id, all_data["course_data"])
                fixed += 1
            else:
                empty += 1  # e.g. graduate-form reports the parser doesn't cover
        except Exception as e:
            errors += 1
            consecutive += 1
            print(f"[Worker {worker_id}] Error on {dept} {cid}: {e}")
            if consecutive >= 12:
                print(f"[Worker {worker_id}] {consecutive} failures in a row — this browser's "
                      f"login session has likely expired. Stopping this worker; its remaining "
                      f"rows stay marked as damaged. Rerun repair_rescrape.py after a fresh "
                      f"getCookies.py to finish them.")
                break
    print(f"[Worker {worker_id}] done: {fixed} fixed, {empty} no-data, {errors} errors")
    return fixed, empty, errors


def main():
    rows = broken_rows()
    print(f"{len(rows)} damaged rows across {BROKEN_QUARTERS}")
    if not rows:
        print("Nothing to repair.")
        return

    print("Creating one browser for the preview...")
    driver = create_driver()
    preview(driver)

    answer = input("\nContinue with the FULL repair (roughly 1-3 hours, unattended)? [y/N] ").strip().lower()
    if answer != "y":
        driver.quit()
        print("Stopped after preview. If the preview output looked wrong, paste it to Claude.")
        return

    print(f"Creating {NUM_WORKERS - 1} more browsers...")
    drivers = [driver] + [create_driver() for _ in range(NUM_WORKERS - 1)]

    chunks = [[] for _ in range(NUM_WORKERS)]
    for i, row in enumerate(rows):
        chunks[i % NUM_WORKERS].append(row)

    totals = [0, 0, 0]
    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as pool:
        futures = [pool.submit(worker, i, drivers[i], chunks[i]) for i in range(NUM_WORKERS)]
        for f in as_completed(futures):
            try:
                fixed, empty, errors = f.result()
                totals = [a + b for a, b in zip(totals, (fixed, empty, errors))]
            except Exception as e:
                print(f"Worker crashed: {e}")

    for d in drivers:
        d.quit()

    print(f"\nRepair complete: {totals[0]} rows fixed, {totals[1]} had no extractable data "
          f"(mostly graduate-form reports), {totals[2]} errors.")
    print("\nNext steps:")
    print("  cd ..")
    print("  python calculate_averages.py")
    print("  cp course_feedback.db ../courseFeedBackExtensionProduction/course_feedback.db")
    print("  cd ..")
    print("  git add analyzeCourseFeedback courseFeedBackExtensionProduction")
    print('  git commit -m "repair ratings/hours for post-migration quarters"')
    print("  git push")


if __name__ == "__main__":
    main()
