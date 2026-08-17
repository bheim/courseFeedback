"""Scrape section meeting times + instructors from UChicago Class Search.

Class Search has a PUBLIC guest portal (no login), and its term dropdown
retains past terms — so one run can backfill the entire time/instructor
history that feedback reports never carry (Roadmap: times capture).

Times and instructor names are public schedule data: times.db is safe to
commit to the main repo.

Because the PeopleSoft page structure can't be tested from the cloud side,
start with a probe so the selectors can be verified once:

    python scrape_section_times.py --probe "Autumn 2025" HUMA
        -> prints the page structure + best-effort parsed rows.
           Paste the output to Claude; if rows parse, run for real:

    python scrape_section_times.py "Autumn 2025" HUMA SOSC PHIL ...
    python scrape_section_times.py --all-terms HUMA
"""

import re
import sqlite3
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from webdriver_manager.chrome import ChromeDriverManager

START_URL = "https://coursesearch.uchicago.edu/"
DB_PATH = "times.db"

SECTION_RE = re.compile(r"([A-Z]{4})\s+(\d{5})/(\d+)\s*\[(\d+)\]")
TIME_RE = re.compile(r"((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)(?:\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun))*)\s*:\s*"
                     r"(\d{1,2}:\d{2}\s*[AP]M)-(\d{1,2}:\d{2}\s*[AP]M)")
ENROLL_RE = re.compile(r"Section Enrollment:\s*(\d+)/(\d+)")


def setup_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS section_times (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        term TEXT, dept TEXT, course_id INTEGER, section TEXT,
        class_number TEXT, instructor TEXT, days TEXT,
        start_time TEXT, end_time TEXT,
        enrolled INTEGER, capacity INTEGER, status TEXT,
        UNIQUE(term, class_number))""")
    conn.commit()
    return conn


def make_driver():
    options = Options()
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()),
                              options=options)
    driver.get(START_URL)
    time.sleep(6)
    return driver


def find_term_select(driver):
    for sel in driver.find_elements(By.TAG_NAME, "select"):
        texts = [o.text for o in Select(sel).options]
        if any(re.match(r"(Autumn|Winter|Spring|Summer)\s+\d{4}", t) for t in texts):
            return sel
    return None


def probe(term, subject):
    driver = make_driver()
    print(f"title: {driver.title}")
    print(f"url:   {driver.current_url[:120]}")

    term_sel = find_term_select(driver)
    if term_sel:
        opts = [o.text for o in Select(term_sel).options if o.text.strip()]
        print(f"TERM DROPDOWN FOUND — {len(opts)} options: {opts[:12]}...")
    else:
        print("NO term dropdown found — dumping all selects:")
        for sel in driver.find_elements(By.TAG_NAME, "select"):
            print("  select id=", sel.get_attribute("id"),
                  [o.text for o in Select(sel).options][:6])

    dump_controls(driver)
    run_search(driver, term, subject, verbose=True)

    rows = parse_results(driver, verbose=True)
    print(f"\nBest-effort parse: {len(rows)} rows")
    for r in rows[:8]:
        print("  ", r)
    if not rows:
        print("\nNothing parsed — body text after search (first 3500 chars):")
        print(driver.find_element(By.TAG_NAME, "body").text[:3500])
        for i, fr in enumerate(driver.find_elements(By.TAG_NAME, "iframe")):
            try:
                driver.switch_to.frame(fr)
                print(f"\n--- iframe {i} body (first 1500 chars) ---")
                print(driver.find_element(By.TAG_NAME, "body").text[:1500])
            except Exception as e:
                print(f"iframe {i}: {e}")
            finally:
                driver.switch_to.default_content()
    driver.quit()
    print("\nPaste ALL of this output to Claude.")


def dump_controls(driver):
    print("\n--- visible inputs ---")
    for el in driver.find_elements(By.TAG_NAME, "input"):
        if not el.is_displayed():
            continue
        print(f"  input id={el.get_attribute('id')!r} type={el.get_attribute('type')!r} "
              f"placeholder={el.get_attribute('placeholder')!r} "
              f"aria={el.get_attribute('aria-label')!r} value={el.get_attribute('value')!r}")
    print("--- clickables containing 'search' ---")
    for tag in ("button", "a", "span", "div"):
        for el in driver.find_elements(By.TAG_NAME, tag):
            label = " ".join(filter(None, [el.text, el.get_attribute("title") or "",
                                           el.get_attribute("aria-label") or ""]))
            if "search" in label.lower() and el.is_displayed():
                print(f"  <{tag}> id={el.get_attribute('id')!r} label={label[:60]!r}")
    print("--- selects ---")
    for sel in driver.find_elements(By.TAG_NAME, "select"):
        if not sel.is_displayed():
            continue
        opts = [o.text for o in Select(sel).options][:5]
        print(f"  select id={sel.get_attribute('id')!r} options={opts}")
    frames = driver.find_elements(By.TAG_NAME, "iframe")
    print(f"--- iframes: {len(frames)} ---")


def find_keyword_box(driver):
    """The guest search page uses a free-text box, not a department dropdown."""
    candidates = []
    for el in driver.find_elements(By.TAG_NAME, "input"):
        if not el.is_displayed():
            continue
        itype = (el.get_attribute("type") or "").lower()
        if itype not in ("text", "search", ""):
            continue
        meta = " ".join(filter(None, [el.get_attribute("id") or "",
                                      el.get_attribute("placeholder") or "",
                                      el.get_attribute("aria-label") or ""])).lower()
        score = sum(k in meta for k in ("search", "keyword", "contain", "class"))
        candidates.append((score, el))
    candidates.sort(key=lambda t: -t[0])
    return candidates[0][1] if candidates else None


def run_search(driver, term, subject, verbose=False):
    term_sel = find_term_select(driver)
    if term_sel:
        try:
            Select(term_sel).select_by_visible_text(term)
            time.sleep(3)
            if verbose:
                print(f"selected term: {term}")
        except Exception as e:
            print(f"could not select term '{term}': {e}")

    box = find_keyword_box(driver)
    if not box:
        print("no keyword box found")
        return
    box.clear()
    box.send_keys(subject)
    time.sleep(1)
    if verbose:
        print(f"typed {subject!r} into input id={box.get_attribute('id')!r}")
    box.send_keys(Keys.ENTER)
    time.sleep(6)

    # If ENTER didn't trigger it (no section rows visible), click anything labeled search
    if not SECTION_RE.search(driver.find_element(By.TAG_NAME, "body").text):
        for tag in ("button", "a", "input", "span"):
            for el in driver.find_elements(By.TAG_NAME, tag):
                label = " ".join(filter(None, [el.text,
                                               el.get_attribute("value") or "",
                                               el.get_attribute("aria-label") or ""]))
                if label.strip().lower() == "search" and el.is_displayed():
                    try:
                        el.click()
                        time.sleep(6)
                        if verbose:
                            print(f"clicked <{tag}> search control")
                    except Exception as e:
                        print(f"search click failed: {e}")
                    return


def parse_results(driver, verbose=False):
    """Parse result rows from the page text; resilient to id changes.

    Each result's text block contains the section header line
    (DEPT NNNNN/S [class#] - ... Open/Closed), the title, enrollment,
    instructor line, and 'Days : time-time'."""
    rows = []
    # Scroll to force lazy loading of all results
    last_height = 0
    for _ in range(30):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.2)
        height = driver.execute_script("return document.body.scrollHeight")
        if height == last_height:
            break
        last_height = height

    text = driver.find_element(By.TAG_NAME, "body").text
    blocks = SECTION_RE.split(text)
    # split() yields: [pre, dept, num, sec, class#, tail, dept, num, ...]
    for i in range(1, len(blocks) - 4, 5):
        dept, num, sec, classnum = blocks[i], blocks[i + 1], blocks[i + 2], blocks[i + 3]
        tail = blocks[i + 4][:600]
        status = "Closed" if "Closed" in tail[:120] else ("Open" if "Open" in tail[:120] else "")
        enroll = ENROLL_RE.search(tail)
        tmatch = TIME_RE.search(tail)
        # Instructor: the line between enrollment and the time line
        instructor = ""
        if enroll and tmatch:
            between = tail[enroll.end():tmatch.start()]
            lines = [ln.strip() for ln in between.splitlines() if ln.strip()]
            if lines:
                instructor = lines[-1]
        rows.append({
            "dept": dept, "course_id": int(num), "section": sec,
            "class_number": classnum, "status": status,
            "enrolled": int(enroll.group(1)) if enroll else None,
            "capacity": int(enroll.group(2)) if enroll else None,
            "instructor": instructor,
            "days": tmatch.group(1) if tmatch else "",
            "start_time": tmatch.group(2) if tmatch else "",
            "end_time": tmatch.group(3) if tmatch else "",
        })
    if verbose and rows:
        print(f"parsed {len(rows)} section blocks from page text")
    return rows


def main():
    args = [a for a in sys.argv[1:] if a != "--probe"]
    if "--probe" in sys.argv:
        term = args[0] if args else "Autumn 2025"
        subject = args[1] if len(args) > 1 else "HUMA"
        probe(term, subject)
        return

    if not args:
        sys.exit(__doc__)
    all_terms = args[0] == "--all-terms"
    subjects = args[1:] if not all_terms else args[1:]
    terms = [] if all_terms else [args[0]]

    conn = setup_db()
    driver = make_driver()
    if all_terms:
        sel = find_term_select(driver)
        terms = [o.text for o in Select(sel).options
                 if re.match(r"(Autumn|Winter|Spring)\s+\d{4}", o.text)]
        print(f"terms discovered: {terms}")

    total = 0
    for term in terms:
        for subject in subjects:
            driver.get(START_URL)
            time.sleep(5)
            run_search(driver, term, subject)
            rows = parse_results(driver)
            for r in rows:
                conn.execute("""INSERT OR REPLACE INTO section_times
                    (term, dept, course_id, section, class_number, instructor,
                     days, start_time, end_time, enrolled, capacity, status)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (term, r["dept"], r["course_id"], r["section"],
                     r["class_number"], r["instructor"], r["days"],
                     r["start_time"], r["end_time"], r["enrolled"],
                     r["capacity"], r["status"]))
            conn.commit()
            total += len(rows)
            print(f"{term} / {subject}: {len(rows)} sections (running total {total})")
    driver.quit()
    print(f"\nDone: {total} sections in {DB_PATH}")
    print("Push: git add analyzeCourseFeedback/getSectionTimes/times.db && "
          "git commit -m 'section times' && git pull --rebase && git push")


if __name__ == "__main__":
    main()
