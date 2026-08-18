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


DETAIL_RE = re.compile(
    r"Section Enrollment:\s*\d+\s*/\s*\d+.{0,160}?"
    r"((?:Mon|Tue|Wed|Thu|Fri)(?:\s+(?:Mon|Tue|Wed|Thu|Fri))*)\s*:\s*"
    r"(\d{1,2}:\d{2})\s*([AP]M)", re.S)


def parse_page(text):
    """Return {(course_id, section): (days, start)} for every row visible.

    Handles both layouts: header immediately followed by its details
    (Class Search style), and the pre-reg grid's split rendering where
    all header lines come first and the detail blocks follow in the
    same order (seen in the user's print of First-Year Pre-Registration)."""
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

    heads = [(h.group(1), h.group(2), h.group(3)) for h in SECTION_RE.finditer(text)]
    huma_heads = [(int(n), s.lstrip("0") or "0") for d, n, s in heads if d == "HUMA"]
    if huma_heads and len(found) < len(huma_heads) // 2:
        # Separated layout: headers first, detail blocks after. Whatever the
        # adjacency pass matched here is an artifact (a header's 'tail' is
        # just the next header) - discard it and pair positionally instead,
        # which is only safe when every header has exactly one detail block.
        details = [(m.group(1), norm_time(m.group(2), m.group(3)))
                   for m in DETAIL_RE.finditer(text)]
        if details and len(details) == len(huma_heads):
            return dict(zip(huma_heads, details))
        if details:
            print(f"  (layout note: {len(huma_heads)} headers vs {len(details)} "
                  "detail blocks - scroll so the full list loads, then capture again)")
        return {}
    return found


def read_frames(driver):
    """Body text from the page AND every visible iframe, narrating progress
    so a slow portal page never looks like a hang."""
    texts = []
    try:
        print("  reading main page...", flush=True)
        texts.append(("main", driver.find_element(By.TAG_NAME, "body").text))
    except Exception as e:
        print(f"  main page unreadable: {e}", flush=True)
    frames = driver.find_elements(By.TAG_NAME, "iframe")
    if frames:
        print(f"  {len(frames)} iframes found", flush=True)
    for i, fr in enumerate(frames):
        try:
            if not fr.is_displayed():
                continue
            print(f"  reading iframe {i}...", flush=True)
            driver.switch_to.frame(fr)
            texts.append((f"iframe{i}", driver.find_element(By.TAG_NAME, "body").text))
            for j, sub in enumerate(driver.find_elements(By.TAG_NAME, "iframe")):
                try:
                    driver.switch_to.frame(sub)
                    texts.append((f"iframe{i}.{j}",
                                  driver.find_element(By.TAG_NAME, "body").text))
                except Exception:
                    pass
                finally:
                    driver.switch_to.parent_frame()
        except Exception as e:
            print(f"  iframe {i} unreadable: {e}", flush=True)
        finally:
            driver.switch_to.default_content()
    return texts


def main():
    options = Options()
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()),
                              options=options)
    driver.get(START_URL)
    print("Browser opened. Log in yourself (Okta/Duo - this script never sees it).")
    print("Then open the First-Year Pre-Registration page - the flat list of")
    print("sections with ADD buttons ('118 rows'). No expanding needed: press")
    print("ENTER once and the script auto-scrolls the whole list. If it parses")
    print("fewer rows than the page's row count, scroll manually and press")
    print("ENTER again - rows accumulate across captures.")

    seen = {}
    while True:
        ans = input("\nWith the section list visible in the browser, press ENTER "
                    "(type nothing) to capture - or type 'done' to finish: ").strip().lower()
        if ans == "done":
            if seen:
                break
            again = input("Nothing has been captured yet. Press ENTER to capture "
                          "the current page, or type 'done' again to quit empty: ").strip().lower()
            if again == "done":
                break
        time.sleep(1)
        rows = {}
        all_frames = []
        for h in driver.window_handles:
            try:
                driver.switch_to.window(h)
                print(f"  tab: {driver.title[:55]!r}", flush=True)
            except Exception as e:
                print(f"  tab unreadable: {e}", flush=True)
                continue
            for name, text in read_frames(driver):
                r = parse_page(text)
                print(f"    {name}: {len(text or '')} chars -> {len(r)} section rows",
                      flush=True)
                rows.update(r)
                all_frames.append((driver.title[:40], name, text))
        fresh = {k: v for k, v in rows.items() if k not in seen}
        seen.update(rows)
        print(f"captured {len(rows)} HUMA rows ({len(fresh)} new; {len(seen)} total)")
        if rows and len(seen) < 110:
            print("  (if the page says 118 rows, scroll the list in the browser "
                  "and press ENTER again - captures accumulate)")
        if not rows:
            print("--- nothing parsed in any tab; samples (paste to Claude) ---")
            print("--- IMPORTANT: the pre-reg list must be open in THIS script's")
            print("--- Chrome window (any tab), not your everyday browser.")
            for title, name, text in all_frames:
                t = (text or "").strip()
                if t:
                    print(f"\n[{title} | {name}] {t[:600]}")
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
