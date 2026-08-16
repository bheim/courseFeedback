"""Print the raw-comment layer for the planned first-year slate.

Runs ONLY on the machine that holds comments.db (raw text never leaves it).
For each course on the slate: keyword-flagged comments (grading, workload,
difficulty) plus recent general ones. For each named instructor: the
comments from their own sections.

    python my_slate_comments.py            # from this folder
    python my_slate_comments.py > slate_comments.txt   # to read/share at will
"""

import re
import sqlite3

COMMENTS_DB = 'comments.db'
MAIN_DB = '../course_feedback.db'

SLATE = [('HUMA', 12300), ('HUMA', 18000), ('HUMA', 12050), ('HUMA', 19100),
         ('LATN', 10100), ('LATN', 10200), ('LATN', 10300),
         ('BIOS', 11140), ('BIOS', 15113), ('BIOS', 11136),
         ('PHIL', 21000), ('PHIL', 20100), ('PHIL', 24096),
         ('ECON', 10000), ('MENG', 20000), ('MENG', 20100), ('MENG', 20400),
         ('PHSC', 13400)]

INSTRUCTORS = ['DeStefano', 'Williams', 'McDaniel', 'Ramsauer', 'Castro',
               'Fenno', 'Brooks', 'Radding', 'Morrissey', 'Broughton',
               'Saltzman', 'Filippaki', 'Zimmer', 'Sanderson', 'Lee',
               'Kuevibulvanich', 'Akers', 'Khare', 'Tirrell']

FLAG = re.compile(r'grad(e|ed|ing)|unfair|harsh|curve|rubric|easy|light|'
                  r'hard(er|est)?\b|difficult|workload|hours|brutal|feedback|'
                  r'clear|unclear|attendance', re.I)


def show(rows, cap_flagged=10, cap_general=4):
    flagged = [r for r in rows if FLAG.search(r[-1])][:cap_flagged]
    general = [r for r in rows if not FLAG.search(r[-1])][:cap_general]
    for tag, subset in (("FLAG", flagged), ("gen ", general)):
        for r in subset:
            quarter, comment = r[0], r[-1]
            print(f"    [{tag}|{quarter}] {comment[:240]}")


def main():
    conn = sqlite3.connect(f"file:{COMMENTS_DB}?mode=ro", uri=True)
    conn.execute(f"ATTACH DATABASE '{MAIN_DB}' AS main_db")

    for dept, cid in SLATE:
        rows = conn.execute("""
            SELECT quarter, comment FROM comments
            WHERE dept=? AND course_id=? ORDER BY section_id DESC""",
            (dept, cid)).fetchall()
        if not rows:
            print(f"\n##### {dept} {cid}: no comments captured")
            continue
        n_flag = sum(1 for r in rows if FLAG.search(r[-1]))
        print(f"\n##### {dept} {cid} — {len(rows)} comments, {n_flag} keyword-flagged")
        show(rows)

    print("\n" + "=" * 70)
    for last in INSTRUCTORS:
        rows = conn.execute("""
            SELECT c.quarter, m.dept || ' ' || m.course_id, c.comment
            FROM comments c
            JOIN main_db.courses m ON m.id = c.section_id
            JOIN main_db.courses_professors cp ON cp.course_id = c.section_id
            JOIN main_db.professors p ON p.id = cp.professor_id
            WHERE p.last_name = ? ORDER BY c.section_id DESC""", (last,)).fetchall()
        if not rows:
            print(f"\n@@@@@ {last}: no captured comments (pre-2025 sections only?)")
            continue
        n_flag = sum(1 for r in rows if FLAG.search(r[-1]))
        print(f"\n@@@@@ {last} — {len(rows)} comments across their sections, {n_flag} flagged")
        flagged = [r for r in rows if FLAG.search(r[-1])][:8]
        general = [r for r in rows if not FLAG.search(r[-1])][:4]
        for quarter, course, comment in flagged + general:
            print(f"    [{quarter}|{course}] {comment[:240]}")

    conn.close()
    print("\nDone. Read it yourself, or paste any part back to Claude for synthesis —")
    print("this file is yours; just never commit raw comments to the public repo.")


if __name__ == "__main__":
    main()
