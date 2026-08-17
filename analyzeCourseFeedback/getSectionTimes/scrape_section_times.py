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
from selenium.webdriver.support.ui import Select
from webdriver_manager.chrome import ChromeDriverManager

START_URL = "https://coursesearch.uchicago.edu/"
DB_PATH = "times.db"

# Verified via probe 2026-08-17 (page: UC Classes Self-Service, prd92guest)
SUBJECT_SELECT_ID = "UC_CLSRCH_WRK2_SUBJECT"
SEARCH_BTN_ID = "UC_CLSRCH_WRK2_SEARCH_BTN"

# The Department dropdown shows names, not codes; option values are usually
# the codes, so we try select-by-value first and fall back to these names.
DEPT_NAMES = {
    "HUMA": "Humanities", "SOSC": "Social Sciences",
    "BIOS": "Biological Sciences", "MATH": "Mathematics",
    "LATN": "Latin", "GREK": "Greek", "CMSC": "Computer Science",
    "ECON": "Economics", "PHIL": "Philosophy", "PHSC": "Physical Sciences",
    "MENG": "Molecular Engineering", "CLCV": "Classical Civilization",
    "WRIT": "Writing",
}

SECTION_RE = re.compile(r"([A-Z]{4})\s+(\d{5})/(\d+)\s*\[(\d+)\]")
COUNT_RE = re.compile(r"\b(\d+)\s*(?:-|–|to)\s*(\d+)\s+of\s+(\d+)\b")
RESULTS_RE = re.compile(r"\b(\d+)\s+Results?\b", re.I)
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

    rows = collect_all_rows(driver, verbose=True)
    print(f"\nBest-effort parse: {len(rows)} rows")
    for r in rows[:8]:
        print("  ", r)

    body = driver.find_element(By.TAG_NAME, "body").text
    m = COUNT_RE.search(body) or RESULTS_RE.search(body)
    print(f"\nresult-count text on page: {m.group(0) if m else 'NONE FOUND'}")
    print("candidate pagination controls:")
    shown = 0
    for tag in ("a", "button", "img", "span"):
        for el in driver.find_elements(By.TAG_NAME, tag):
            meta = " ".join(filter(None, [el.get_attribute("id") or "",
                                          el.get_attribute("aria-label") or "",
                                          el.get_attribute("title") or "",
                                          el.get_attribute("alt") or "",
                                          (el.text or "")[:30]]))
            if any(k in meta.lower() for k in ("hdown", "hup", "hviewall", "view all",
                                               "show next", "show following", "next set")):
                print(f"  <{tag}> {meta[:90]!r}")
                shown += 1
        if shown >= 12:
            break

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


def select_subject(driver, subject, verbose=False):
    """Pick the Department dropdown entry for a subject code or name.

    Keyword search is NOT equivalent — 'HUMA' as a keyword matches every
    course with 'human' in the title (AASR, ANTH, BIOS...)."""
    try:
        sel = Select(driver.find_element(By.ID, SUBJECT_SELECT_ID))
    except Exception:
        print("no Department dropdown found on page")
        return False
    try:
        sel.select_by_value(subject)
        if verbose:
            print(f"department selected by value: {subject}")
        return True
    except Exception:
        pass
    want = DEPT_NAMES.get(subject.upper(), subject).lower()
    for o in sel.options:
        if o.text.strip().lower().startswith(want):
            sel.select_by_visible_text(o.text)
            if verbose:
                print(f"department selected by name: {o.text}")
            return True
    print(f"department {subject!r} not matched. The dropdown offers:")
    for o in sel.options:
        if o.text.strip():
            print(f"  value={o.get_attribute('value')!r} text={o.text!r}")
    return False


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

    if not select_subject(driver, subject, verbose=verbose):
        return
    time.sleep(2)

    try:
        driver.find_element(By.ID, SEARCH_BTN_ID).click()
        if verbose:
            print("clicked SEARCH")
    except Exception:
        for tag in ("a", "button", "input", "span"):
            for el in driver.find_elements(By.TAG_NAME, tag):
                label = " ".join(filter(None, [el.text,
                                               el.get_attribute("value") or "",
                                               el.get_attribute("aria-label") or ""]))
                if label.strip().lower() == "search" and el.is_displayed():
                    try:
                        el.click()
                        if verbose:
                            print(f"clicked <{tag}> search control (fallback)")
                    except Exception as e:
                        print(f"search click failed: {e}")
                        return
                    break
            else:
                continue
            break
    time.sleep(6)


def find_next_control(driver):
    """The results grid pages 25 at a time. PeopleSoft's next-page control
    carries 'hdown' in its id or a 'next' aria/title/alt."""
    best, best_score = None, 0
    for tag in ("a", "button", "img", "span"):
        for el in driver.find_elements(By.TAG_NAME, tag):
            if not el.is_displayed():
                continue
            eid = (el.get_attribute("id") or "").lower()
            meta = " ".join(filter(None, [el.get_attribute("aria-label") or "",
                                          el.get_attribute("title") or "",
                                          el.get_attribute("alt") or ""])).lower()
            score = 0
            if "hdown" in eid:
                score += 3
            if meta.startswith("show next") or meta.startswith("next") or meta == "next":
                score += 2
            if score > best_score:
                best, best_score = el, score
    return best


def collect_all_rows(driver, verbose=False):
    """Parse every results page: View All if offered, else click next-page
    until the counted total is reached or nothing new appears."""
    for el in driver.find_elements(By.TAG_NAME, "a"):
        try:
            if el.is_displayed() and (el.text.strip().lower() == "view all"
                                      or "hviewall" in (el.get_attribute("id") or "")):
                el.click()
                time.sleep(8)
                if verbose:
                    print("clicked View All")
                break
        except Exception:
            continue

    seen, rows = set(), []
    stale_pages = 0
    for page in range(80):
        new = 0
        for r in parse_results(driver):
            if r["class_number"] not in seen:
                seen.add(r["class_number"])
                rows.append(r)
                new += 1
        body = driver.find_element(By.TAG_NAME, "body").text
        m = COUNT_RE.search(body) or RESULTS_RE.search(body)
        total = int(m.groups()[-1]) if m else None
        if verbose:
            print(f"  page {page + 1}: +{new}, {len(rows)} rows total"
                  + (f" (page says {total})" if total else ""))
        if total and len(rows) >= total:
            break
        stale_pages = stale_pages + 1 if new == 0 else 0
        if stale_pages >= 2:
            break
        nxt = find_next_control(driver)
        if nxt is None:
            break
        try:
            nxt.click()
        except Exception:
            break
        time.sleep(4)
    return rows


def parse_results(driver, verbose=False):
    """Parse result rows from the page text; resilient to id changes.

    Each result's text block contains the section header line
    (DEPT NNNNN/S [class#] - ... Open/Closed), the title, enrollment,
    instructor line, and 'Days : time-time'."""
    rows = []
    # Scroll to settle any lazy rendering (grid is paginated, so this is quick)
    last_height = 0
    for _ in range(12):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.0)
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
            rows = collect_all_rows(driver)
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
