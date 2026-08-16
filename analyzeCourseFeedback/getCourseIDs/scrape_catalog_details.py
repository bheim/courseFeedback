"""Capture the catalog data we've been throwing away (Roadmap W2).

The college catalog pages we already visit for course IDs also contain, per
course: the full description, prerequisites, "Terms Offered", "Equivalent
Course(s)", and instructor listings — plus each program page's requirement
course lists. This scrape stores all of it into catalog.db.

Public pages, no login needed. Takes ~5 minutes. Rerunning replaces the
snapshot (the catalog is republished yearly, so full refresh is correct).

    python scrape_catalog_details.py
"""

import re
import sqlite3
import time

import requests
from bs4 import BeautifulSoup

BASE_URL = 'http://collegecatalog.uchicago.edu/thecollege/programsofstudy/'
CORE_URL_ADD_ONS = ['artscore/', 'biologicalsciencescore/', 'civilizationstudies/',
                    'humanities/', 'mathematicalsciencescore/',
                    'physicalsciences/', 'socialsciences/']

DB_PATH = 'catalog.db'

DETAIL_FIELDS = {
    'terms_offered': r'Terms Offered:\s*([^\n]*)',
    'prerequisites': r'Prerequisite\(s\):\s*([^\n]*)',
    'equivalents': r'Equivalent Course\(s\):\s*([^\n]*)',
    'instructors': r'Instructor\(s\):\s*([^\n]*)',
    'note': r'Note\(s\):\s*([^\n]*)',
}


def setup_database():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Full refresh each run: the catalog is a yearly snapshot
    cur.execute('DROP TABLE IF EXISTS catalog_courses')
    cur.execute('DROP TABLE IF EXISTS program_courses')
    cur.execute('''
        CREATE TABLE catalog_courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_page TEXT,
            code TEXT,
            title TEXT,
            units TEXT,
            description TEXT,
            terms_offered TEXT,
            prerequisites TEXT,
            equivalents TEXT,
            instructors TEXT,
            note TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE program_courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            program TEXT,
            section TEXT,
            code TEXT,
            UNIQUE(program, section, code)
        )
    ''')
    conn.commit()
    return conn


def parse_courseblock(block):
    title_el = block.find('p', class_='courseblocktitle')
    if not title_el:
        return None
    title_text = title_el.get_text(' ', strip=True).replace('\xa0', ' ')

    # Typical shape: "ANTH 10100. Course Title. 100 Units."
    m = re.match(r'([A-Z]{4}\s+\d{5})\.\s*(.*?)\.\s*(\d+(?:-\d+)?\s*Units?)?\.?\s*$', title_text)
    if m:
        code, title, units = m.group(1), m.group(2), m.group(3) or ''
    else:
        parts = title_text.split('.')
        code = parts[0].strip()
        title = parts[1].strip() if len(parts) > 1 else ''
        units = ''
        if not re.match(r'^[A-Z]{4}\s+\d{5}$', code):
            return None

    desc_el = block.find('p', class_='courseblockdesc')
    description = desc_el.get_text(' ', strip=True) if desc_el else ''

    fields = {k: '' for k in DETAIL_FIELDS}
    detail_el = block.find('p', class_='courseblockdetail')
    if detail_el:
        detail_text = detail_el.get_text('\n', strip=True).replace('\xa0', ' ')
        for key, pattern in DETAIL_FIELDS.items():
            m = re.search(pattern, detail_text)
            if m:
                fields[key] = m.group(1).strip()

    return {
        'code': code, 'title': title, 'units': units,
        'description': description, **fields,
    }


def scrape_page(conn, url, page_name):
    try:
        response = requests.get(url, timeout=30)
    except Exception as e:
        print(f"  request failed for {page_name}: {e}")
        return 0, 0
    if response.status_code != 200:
        print(f"  HTTP {response.status_code} for {page_name}")
        return 0, 0

    soup = BeautifulSoup(response.content, 'html.parser')
    cur = conn.cursor()

    n_courses = 0
    for block in soup.find_all('div', class_='courseblock'):
        parsed = parse_courseblock(block)
        if parsed:
            cur.execute('''
                INSERT INTO catalog_courses
                (source_page, code, title, units, description, terms_offered,
                 prerequisites, equivalents, instructors, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (page_name, parsed['code'], parsed['title'], parsed['units'],
                  parsed['description'], parsed['terms_offered'],
                  parsed['prerequisites'], parsed['equivalents'],
                  parsed['instructors'], parsed['note']))
            n_courses += 1

    # Requirement tables: course codes referenced by this program's plan,
    # tagged with the nearest preceding heading — which is how the catalog
    # marks tracks/specializations/minors within a program page
    n_reqs = 0
    for cell in soup.find_all('td', class_='codecol'):
        heading = cell.find_previous(['h2', 'h3', 'h4', 'h5'])
        section = heading.get_text(' ', strip=True)[:90] if heading else ''
        code = cell.get_text(' ', strip=True).replace('\xa0', ' ')
        for one in re.findall(r'[A-Z]{4}\s+\d{5}', code):
            cur.execute('INSERT OR IGNORE INTO program_courses (program, section, code) '
                        'VALUES (?, ?, ?)', (page_name, section, one))
            n_reqs += 1

    conn.commit()
    return n_courses, n_reqs


def main():
    conn = setup_database()

    response = requests.get(BASE_URL, timeout=30)
    if response.status_code != 200:
        print(f"Could not load programs-of-study index (HTTP {response.status_code}). Aborting.")
        return
    soup = BeautifulSoup(response.content, 'html.parser')

    pages = []
    for link in soup.select('ul.nav.leveltwo li a'):
        href = link['href']
        if href.startswith('/'):
            href = 'http://collegecatalog.uchicago.edu' + href
        pages.append((href, link.text.strip()))
    for add_on in CORE_URL_ADD_ONS:
        pages.append(('http://collegecatalog.uchicago.edu/thecollege/' + add_on, add_on.strip('/')))

    total_c = total_r = 0
    for url, name in pages:
        print(f"Scraping {name}...")
        nc, nr = scrape_page(conn, url, name)
        total_c += nc
        total_r += nr
        time.sleep(1)

    print(f"\nDone: {total_c} course entries and {total_r} program-requirement "
          f"references saved to {DB_PATH}")
    n_desc = conn.execute(
        "SELECT COUNT(*) FROM catalog_courses WHERE LENGTH(description) > 40").fetchone()[0]
    n_terms = conn.execute(
        "SELECT COUNT(*) FROM catalog_courses WHERE terms_offered != ''").fetchone()[0]
    n_equiv = conn.execute(
        "SELECT COUNT(*) FROM catalog_courses WHERE equivalents != ''").fetchone()[0]
    print(f"  with real descriptions: {n_desc} | with Terms Offered: {n_terms} "
          f"| with equivalents: {n_equiv}")
    print("\nNext: git add analyzeCourseFeedback/getCourseIDs/catalog.db && "
          "git commit -m 'catalog details snapshot' && git pull --rebase && git push")
    conn.close()


if __name__ == "__main__":
    main()
