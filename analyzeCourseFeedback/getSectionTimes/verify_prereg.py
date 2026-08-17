"""Cross-check the pre-registration screen against our scraped section times.

Pre-reg sits behind Okta, so YOU drive the browser: the script opens Chrome,
you log in and pull up a sequence's section list, then press ENTER in the
terminal and it reads the page. It never sees or asks for credentials.

    python verify_prereg.py
        -> browser opens my.uchicago.edu; log in, open pre-registration,
           show a Hum sequence's sections; press ENTER here to capture.
           Repeat for each sequence, then type 'done'.

Ends with a verdict for every target section on the final ballot:
FOUND (time matches), TIME MISMATCH, or NOT SEEN. If parsing fails, it
prints a raw page dump - paste that to Claude and the regexes get fixed.
"""

import re
import sqlite3
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

START_URL = "https://my.uchicago.edu/"
DB_PATH = "times.db"

# The final ballot: (course_id, section) -> expected meeting
TARGETS = {
    (12300, "13"): ("Tue Thu", "12:30 PM"), (12300, "14"): ("Tue Thu", "12:30 PM"),
    (12300, "15"): ("Tue Thu", "12:30 PM"), (12300, "16"): ("Tue Thu", "12:30 PM"),
    (18000, "11"): ("Tue Thu", "12:30 PM"),
    (11500, "15"): ("Tue Thu", "12:30 PM"), (11500, "16"): ("Tue Thu", "12:30 PM"),
    (11500, "17"): ("Tue Thu", "12:30 PM"), (11500, "18"): ("Tue Thu", "12:30 PM"),
    (16000, "14"): ("Tue Thu", "12:30 PM"), (16000, "15"): ("Tue Thu", "12:30 PM"),
}

SECTION_RE = re.compile(r"([A-Z]{4})\s+(\d{5})/(\d+)\s*(?:\[(\d+)\])?")
# Class-Search style: "Tue Thu : 12:30 PM-01:50 PM"
TIME_LONG = re.compile(r"((?:Mon|Tue|Wed|Thu|Fri)(?:\s+(?:Mon|Tue|Wed|Thu|Fri))*)\s*:?\s*"
                       r"(\d{1,2}:\d{2})\s*([AP]M)?\s*[-–]\s*\d{1,2}:\d{2}")
# Compact planner style: "TTh 12:30-1:50" / "MWF 10:30 AM"
TIME_SHORT = re.compile(r"\b(MWF|MW|TTh|TR|T|Th|M|W|F)\s+(\d{1,2}:\d{2})\s*([AP]M)?")
DAYMAP = {"MWF": "Mon Wed Fri", "MW": "Mon Wed", "TTh": "Tue Thu", "TR": "Tue Thu",
          "M": "Mon", "T": "Tue", "W": "Wed", "Th": "Thu", "F": "Fri"}


def norm_time(hhmm, ampm):
    h, m = hhmm.split(":")
    h = int(h)
    if ampm:
        suffix = ampm.upper()
    else:
        # class hours heuristic: 12:xx and 1-7 are PM, 8-11 are AM
        suffix = "PM" if (h == 12 or h <= 7) else "AM"
    return f"{h:02d}:{m} {suffix}"


def parse_page(text):
    """Return {(course_id, section): (days, start)} for every row visible."""
    found = {}
    blocks = SECTION_RE.split(text)
    for i in range(1, len(blocks) - 4, 5):
        dept, num, sec = blocks[i], blocks[i + 1], blocks[i + 2]
        if dept != "HUMA":
            continue
        tail = blocks[i + 4][:400]
        m = TIME_LONG.search(tail)
        if m:
            found[(int(num), sec.lstrip("0") or "0")] = (m.group(1), norm_time(m.group(2), m.group(3)))
            continue
        m = TIME_SHORT.search(tail)
        if m and m.group(1) in DAYMAP:
            found[(int(num), sec.lstrip("0") or "0")] = (DAYMAP[m.group(1)], norm_time(m.group(2), m.group(3)))
    return found


def main():
    options = Options()
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()),
                              options=options)
    driver.get(START_URL)
    print("Browser opened. Log in yourself (Okta/Duo - this script never sees it).")
    print("Navigate to pre-registration and display a Hum sequence's section list.")

    seen = {}
    while True:
        ans = input("\nPress ENTER to capture this page ('done' to finish): ").strip().lower()
        if ans == "done":
            break
        time.sleep(1)
        text = driver.find_element(By.TAG_NAME, "body").text
        rows = parse_page(text)
        fresh = {k: v for k, v in rows.items() if k not in seen}
        seen.update(rows)
        print(f"captured {len(rows)} HUMA rows ({len(fresh)} new; {len(seen)} total)")
        if not rows:
            print("--- nothing parsed; raw page sample (paste to Claude) ---")
            print(text[:2500])
    driver.quit()

    print("\n" + "=" * 64)
    print("TARGET CHECK - the final ballot vs what pre-reg showed:")
    ok = 0
    for (cid, sec), (days, start) in TARGETS.items():
        got = seen.get((cid, sec))
        if got is None:
            print(f"  HUMA {cid}/{sec:<3} NOT SEEN on captured pages")
        elif got == (days, start):
            print(f"  HUMA {cid}/{sec:<3} FOUND  {days} {start}")
            ok += 1
        else:
            print(f"  HUMA {cid}/{sec:<3} TIME MISMATCH: prereg says {got}, "
                  f"we expected {days} {start}")
    print(f"\n{ok}/{len(TARGETS)} targets verified.")

    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        db = {}
        for cid, sec, days, start in conn.execute(
                """SELECT course_id, section, days, start_time FROM section_times
                   WHERE dept='HUMA' AND term='Autumn 2026'"""):
            db[(cid, str(sec).lstrip('0') or '0')] = (days, start)
        extra = {k: v for k, v in seen.items() if k in db and db[k] != v}
        missing = {k for k in seen if k not in db}
        if extra:
            print("\nDisagreements with the Class Search scrape:")
            for k, v in sorted(extra.items()):
                print(f"  HUMA {k[0]}/{k[1]}: prereg {v} vs scrape {db[k]}")
        if missing:
            print(f"\nSections on prereg but absent from the scrape: "
                  f"{sorted(missing)}")
        if not extra and not missing and seen:
            print("Every captured row matches the Class Search scrape exactly.")
    except sqlite3.Error as e:
        print(f"(times.db cross-check skipped: {e})")


if __name__ == "__main__":
    main()
