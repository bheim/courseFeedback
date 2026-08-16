"""W3 rich-capture pass: written comments, interest levels, response counts.

Visits the post-migration quarters' report pages (Spring 2025 - Spring 2026)
and captures what the original scraper ignored:

- WRITTEN COMMENTS -> comments.db in this folder. That file is GITIGNORED on
  purpose: the repo is public and raw student comments must never be
  republished (ROADMAP principle 2). It stays on this machine; only
  aggregated signals derived from it are committed.
- Aggregate signals -> course_feedback.db (safe to publish):
    * per-section interest_before / interest_after means (where the report
      exposes a statistics table for them) and response_count
    * per-course comment_signals: comment counts and keyword-based
      grading / easy / hard / workload mention counts

Preview-gated like the repair script. Safe to interrupt and rerun — captured
sections are skipped. Run from this folder with fresh cookies:

    python capture_rich.py
"""

import re
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup

from scrapeFeedback import create_driver

MAIN_DB = '../course_feedback.db'
COMMENTS_DB = 'comments.db'
QUARTERS = ('Spring 2025', 'Autumn 2025', 'Winter 2026', 'Spring 2026')
NUM_WORKERS = 10

INTEREST_BEFORE = "Prior to starting this class, your interest level was?"
INTEREST_AFTER = "Now that this class is over, your interest is?"

KEYWORDS = {
    'grading_mentions': ['grade', 'grading', 'graded', 'curve', 'rubric', 'unfair', 'harsh'],
    'easy_mentions': ['easy', 'light workload', 'manageable', 'not much work', 'chill'],
    'hard_mentions': ['hard', 'difficult', 'brutal', 'heavy', 'intense', 'time-consuming',
                      'time consuming', 'a lot of work', 'workload is'],
}

db_lock = threading.Lock()

# The old-domain links still render pages but serve them best on the new domain
OLD_PREFIX = 'https://uchicago.bluera.com/uchicago/'
NEW_PREFIX = 'https://my-uchicago-bc.bluera.com/'


def setup():
    conn = sqlite3.connect(MAIN_DB)
    existing = {row[1] for row in conn.execute("PRAGMA table_info(courses)")}
    for col, typ in [("interest_before", "REAL"), ("interest_after", "REAL"),
                     ("response_count", "INTEGER")]:
        if col not in existing:
            conn.execute(f"ALTER TABLE courses ADD COLUMN {col} {typ}")
    conn.execute('''CREATE TABLE IF NOT EXISTS comment_signals (
        dept TEXT, course_id INTEGER, n_comments INTEGER,
        grading_mentions INTEGER, easy_mentions INTEGER, hard_mentions INTEGER,
        PRIMARY KEY (dept, course_id))''')
    conn.commit()
    conn.close()

    cconn = sqlite3.connect(COMMENTS_DB)
    cconn.execute('''CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        section_id INTEGER, dept TEXT, course_id INTEGER, quarter TEXT,
        question TEXT, comment TEXT)''')
    cconn.execute('''CREATE TABLE IF NOT EXISTS sections_captured (
        section_id INTEGER PRIMARY KEY)''')
    cconn.commit()
    cconn.close()


def targets():
    mconn = sqlite3.connect(f"file:{MAIN_DB}?mode=ro", uri=True)
    rows = mconn.execute(f"""
        SELECT id, dept, course_id, quarter, url FROM courses
        WHERE quarter IN (?,?,?,?)""", QUARTERS).fetchall()
    mconn.close()
    cconn = sqlite3.connect(f"file:{COMMENTS_DB}?mode=ro", uri=True)
    done = {r[0] for r in cconn.execute("SELECT section_id FROM sections_captured")}
    cconn.close()
    return [r for r in rows if r[0] not in done]


def extract_comments(soup):
    """All comment-table rows, tagged with the question block they answer."""
    out = []
    for table in soup.find_all('table'):
        classes = table.get('class', [])
        if 'CondensedTabular' not in classes or 'CondensedTabularFixedHalfWidth' in classes:
            continue
        rows = table.find_all('tr')
        if not rows or rows[0].get_text(' ', strip=True) != 'Comment':
            continue
        title_el = table.find_previous(['h3', 'h4'], class_='ReportBlockTitle')
        question = title_el.get_text(' ', strip=True) if title_el else ''
        for row in rows[1:]:
            text = row.get_text(' ', strip=True)
            if text:
                out.append((question, text))
    return out


def stat_from_block(soup, title_text, stat_name):
    """Find a titled block and read one statistic from its in-block stats
    table. Returns None if the block renders as a chart image instead."""
    el = soup.find(string=lambda s: s and title_text in s)
    if not el:
        return None
    block = el.find_parent('div', class_='FrequencyBlock_FullMain') or \
        el.find_parent('div', class_='report-block')
    if not block:
        return None
    for table in block.find_all('table'):
        if 'CondensedTabularFixedHalfWidth' not in table.get('class', []):
            continue
        for row in table.find_all('tr'):
            cells = row.find_all(['th', 'td'])
            if len(cells) == 2 and cells[0].get_text(strip=True) == stat_name:
                try:
                    return float(cells[1].get_text(strip=True))
                except ValueError:
                    return None
    return None


def response_count(soup):
    best = None
    for table in soup.find_all('table'):
        if 'CondensedTabularFixedHalfWidth' not in table.get('class', []):
            continue
        for row in table.find_all('tr'):
            cells = row.find_all(['th', 'td'])
            if len(cells) == 2 and cells[0].get_text(strip=True) == 'Response Count':
                try:
                    val = int(float(cells[1].get_text(strip=True)))
                    best = max(best or 0, val)
                except ValueError:
                    pass
    return best


def capture_one(driver, url):
    if url.startswith(OLD_PREFIX):
        url = url.replace(OLD_PREFIX, NEW_PREFIX, 1)
    driver.get(url)
    import time
    time.sleep(2)
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    if not soup.find('div', class_='header'):
        raise RuntimeError("no report header (login page?)")
    return {
        'comments': extract_comments(soup),
        'interest_before': stat_from_block(soup, INTEREST_BEFORE, 'Mean'),
        'interest_after': stat_from_block(soup, INTEREST_AFTER, 'Mean'),
        'response_count': response_count(soup),
    }


def save(section_id, dept, cid, quarter, data):
    with db_lock:
        cconn = sqlite3.connect(COMMENTS_DB, timeout=30)
        cconn.execute("DELETE FROM comments WHERE section_id = ?", (section_id,))
        cconn.executemany(
            "INSERT INTO comments (section_id, dept, course_id, quarter, question, comment) "
            "VALUES (?,?,?,?,?,?)",
            [(section_id, dept, cid, quarter, q, c) for q, c in data['comments']])
        cconn.execute("INSERT OR REPLACE INTO sections_captured (section_id) VALUES (?)",
                      (section_id,))
        cconn.commit()
        cconn.close()

        mconn = sqlite3.connect(MAIN_DB, timeout=30)
        mconn.execute(
            "UPDATE courses SET interest_before=?, interest_after=?, response_count=? WHERE id=?",
            (data['interest_before'], data['interest_after'], data['response_count'], section_id))
        mconn.commit()
        mconn.close()


def worker(worker_id, driver, rows):
    captured = errors = consecutive = n_comments = 0
    for section_id, dept, cid, quarter, url in rows:
        try:
            data = capture_one(driver, url)
            consecutive = 0
            save(section_id, dept, cid, quarter, data)
            captured += 1
            n_comments += len(data['comments'])
        except Exception as e:
            errors += 1
            consecutive += 1
            print(f"[Worker {worker_id}] Error on {dept} {cid}: {e}")
            if consecutive >= 12:
                print(f"[Worker {worker_id}] session likely expired — stopping. "
                      f"Rerun after getCookies.py; captured sections are skipped.")
                break
    print(f"[Worker {worker_id}] done: {captured} sections, {n_comments} comments, {errors} errors")
    return captured, n_comments, errors


def rebuild_comment_signals():
    """Aggregate keyword signals per course into the main (publishable) db."""
    cconn = sqlite3.connect(f"file:{COMMENTS_DB}?mode=ro", uri=True)
    rows = cconn.execute("SELECT dept, course_id, comment FROM comments").fetchall()
    cconn.close()

    agg = {}
    for dept, cid, comment in rows:
        key = (dept, cid)
        entry = agg.setdefault(key, {'n': 0, 'grading_mentions': 0,
                                     'easy_mentions': 0, 'hard_mentions': 0})
        entry['n'] += 1
        low = comment.lower()
        for signal, words in KEYWORDS.items():
            if any(w in low for w in words):
                entry[signal] += 1

    mconn = sqlite3.connect(MAIN_DB)
    mconn.execute("DELETE FROM comment_signals")
    mconn.executemany(
        "INSERT INTO comment_signals VALUES (?,?,?,?,?,?)",
        [(d, c, v['n'], v['grading_mentions'], v['easy_mentions'], v['hard_mentions'])
         for (d, c), v in agg.items()])
    mconn.commit()
    mconn.close()
    print(f"comment_signals rebuilt: {len(agg)} courses aggregated "
          f"(raw text stays in the gitignored {COMMENTS_DB})")


def main():
    setup()
    rows = targets()
    print(f"{len(rows)} sections to capture across {QUARTERS}")
    if not rows:
        rebuild_comment_signals()
        print("Nothing new to capture; aggregates refreshed.")
        return

    print("Creating one browser for the preview...")
    driver = create_driver()
    print("\n--- PREVIEW: 3 samples, no database writes ---")
    for section_id, dept, cid, quarter, url in rows[:3]:
        try:
            data = capture_one(driver, url)
        except Exception as e:
            print(f"[{dept} {cid}] ERROR: {e}")
            continue
        print(f"[{dept} {cid} {quarter}] {len(data['comments'])} comments | "
              f"interest {data['interest_before']} -> {data['interest_after']} | "
              f"responses {data['response_count']}")
        if data['comments']:
            q, c = data['comments'][0]
            print(f"   e.g. ({q[:50]}...): {c[:90]}")
    print("--- END PREVIEW ---\n")

    answer = input("Continue with the FULL capture (roughly 1-2 hours, unattended)? [y/N] ").strip().lower()
    if answer != "y":
        driver.quit()
        print("Stopped after preview. If the preview looked wrong, paste it to Claude.")
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
                totals = [a + b for a, b in zip(totals, f.result())]
            except Exception as e:
                print(f"Worker crashed: {e}")
    for d in drivers:
        d.quit()

    print(f"\nCapture done: {totals[0]} sections, {totals[1]} comments banked locally, "
          f"{totals[2]} errors.")
    rebuild_comment_signals()
    print("\nNext steps:")
    print("  cd ../..")
    print("  git add analyzeCourseFeedback/course_feedback.db")
    print('  git commit -m "rich capture: interest, response counts, comment signals"')
    print("  git pull --rebase")
    print("  git push")
    print("(comments.db is intentionally NOT pushed — raw student text stays local)")


if __name__ == "__main__":
    main()
