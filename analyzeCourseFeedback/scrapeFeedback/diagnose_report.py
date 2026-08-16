"""Diagnose the new (my-uchicago-bc.bluera.com) feedback report format.

The scraper's question-text matching half-broke when the feedback platform
migrated (everything scraped since mid-2025 is missing 5 of 12 ratings and
all hours data). This script loads a few sample reports and prints their
structure — block titles, question wordings, table layouts, chart markup —
so the extraction code can be updated to match the new pages.

Run from this folder, with fresh cookies (run getCookies.py first if your
last login was more than a few hours ago):

    python diagnose_report.py

Then paste the ENTIRE output back into the Claude session.
"""

import sqlite3
import time

from bs4 import BeautifulSoup

from scrapeFeedback import create_driver


def pick_urls():
    conn = sqlite3.connect("file:../course_feedback.db?mode=ro", uri=True)
    cur = conn.cursor()
    queries = [
        ("standard form, partial ratings",
         "SELECT dept, course_id, url FROM courses WHERE quarter='Winter 2026' "
         "AND standards IS NOT NULL AND dept != 'BIOS' LIMIT 1"),
        ("unknown form, zero ratings",
         "SELECT dept, course_id, url FROM courses WHERE quarter='Winter 2026' "
         "AND standards IS NULL AND dept NOT IN ('BIOS','SOSC','HUMA') LIMIT 1"),
        ("BIOS form",
         "SELECT dept, course_id, url FROM courses WHERE quarter='Winter 2026' "
         "AND dept = 'BIOS' LIMIT 1"),
    ]
    samples = []
    for label, q in queries:
        row = cur.execute(q).fetchone()
        if row:
            samples.append((label, row))
    conn.close()
    return samples


def dump_structure(html, label):
    soup = BeautifulSoup(html, "html.parser")
    print(f"\n{'=' * 70}\nSAMPLE: {label}\n{'=' * 70}")

    header = soup.find("div", class_="header")
    if header and header.find("h2"):
        print(f"header h2: {header.find('h2').text.strip()[:130]}")

    print("\nAll h3/h4 titles:")
    for tag in soup.find_all(["h3", "h4"]):
        text = tag.get_text(strip=True)
        if text:
            print(f"  [{tag.name} class={tag.get('class')}] {text[:110]}")

    print("\nDistinct table classes:")
    counts = {}
    for t in soup.find_all("table"):
        key = " ".join(t.get("class", ["<no class>"]))
        counts[key] = counts.get(key, 0) + 1
    for k, v in counts.items():
        print(f"  '{k}': x{v}")

    print("\nTables (headers + first cell of each row = question wordings):")
    for t in soup.find_all("table"):
        cls = " ".join(t.get("class", []))
        rows = t.find_all("tr")
        if len(rows) < 2:
            continue
        headers = [c.get_text(strip=True)[:20] for c in rows[0].find_all(["th", "td"])]
        print(f"  TABLE class='{cls}' headers={headers[:9]}")
        for r in rows[1:8]:
            cells = r.find_all(["th", "td"])
            if cells:
                first = cells[0].get_text(strip=True)[:105]
                rest = [c.get_text(strip=True)[:10] for c in cells[1:7]]
                print(f"    '{first}' -> {rest}")

    print("\nDivs with 'Frequency' or 'report' in class:")
    seen = set()
    for div in soup.find_all("div", class_=True):
        key = " ".join(div.get("class", []))
        if ("Frequency" in key or "report" in key.lower()) and key not in seen:
            seen.add(key)
            print(f"  div class: '{key}'")

    print("\nImages (potential hours charts):")
    imgs = soup.find_all("img")
    if not imgs:
        print("  (none found)")
    for img in imgs[:12]:
        print(f"  img src: {str(img.get('src'))[:110]}")

    print("\nSpans with Title/Preview ids (question titles):")
    for span in soup.find_all("span", id=True):
        if "Title" in span["id"] or "Preview" in span["id"]:
            text = span.get_text(strip=True)
            if text:
                print(f"  [{span['id'][:55]}] {text[:105]}")


def main():
    samples = pick_urls()
    if not samples:
        print("No sample URLs found in ../course_feedback.db — is the path right?")
        return
    print(f"Found {len(samples)} sample reports to inspect.")
    print("Creating browser (same cookie flow as the scraper)...")
    driver = create_driver()
    for label, (dept, cid, url) in samples:
        print(f"\nLoading {dept} {cid} ...")
        driver.get(url)
        time.sleep(4)
        final = driver.current_url
        print(f"  final URL: {final[:100]}")
        if "login" in final.lower() or "signin" in final.lower():
            print("  !! Redirected to a login page — rerun getCookies.py and try again.")
            continue
        dump_structure(driver.page_source, f"{label}: {dept} {cid}")
    driver.quit()
    print("\nDone. Paste this ENTIRE output back into the Claude session.")


if __name__ == "__main__":
    main()
