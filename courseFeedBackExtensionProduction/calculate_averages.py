import sqlite3
import logging
import os

# ----------------------------
# Configuration
# ----------------------------

DATABASE_PATH = 'course_feedback_new.db'  # Replace with your actual database file
ERROR_LOG_PATH = 'error.log'

REQUIRED_COLUMNS = {
    "courses_professors": ["avg_prof_course_hours", "avg_prof_course_rating"],
    "courses": ["avg_course_hours", "avg_course_rating"],
    "professors": ["avg_professor_rating"]
}

def add_missing_columns(db_path, required_columns):
    """Ensures all required columns exist in the database."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        for table, columns in required_columns.items():
            cursor.execute(f"PRAGMA table_info({table});")
            existing_columns = {row[1] for row in cursor.fetchall()}
            
            for column in columns:
                if column not in existing_columns:
                    print(f"Adding missing column: {table}.{column}")
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} REAL;")
                    conn.commit()
        
        conn.close()
        print("All missing columns added successfully.")
    except sqlite3.Error as e:
        logging.error(f"Error adding missing columns: {e}")
        print("Database error occurred while adding missing columns. Check the log for details.")

# Run the function to add missing columns
add_missing_columns(DATABASE_PATH, REQUIRED_COLUMNS)

# ----------------------------
# Execution Function
# ----------------------------

def execute_sql_queries(db_path, queries):
    if not os.path.exists(db_path):
        logging.error(f"Database file '{db_path}' does not exist.")
        print(f"Error: Database file '{db_path}' does not exist. Check the log for details.")
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        print("Connected to the database.")

        conn.execute('BEGIN TRANSACTION;')

        for name, query in queries.items():
            try:
                print(f"Executing: {name}")
                cursor.execute(query)
                print(f"Executed: {name}")
            except sqlite3.Error as e:
                logging.error(f"Error executing '{name}': {e}")
                print(f"Error executing '{name}'. Check the log.")

        conn.commit()
        print("All queries executed and committed successfully.")

    except sqlite3.Error as e:
        logging.error(f"Database error: {e}")
        print("Database error occurred. Check the log for details.")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        print("An unexpected error occurred. Check the log for details.")
    finally:
        if 'conn' in locals():
            conn.close()
            print("Database connection closed.")


SQL_QUERIES = {
    "avg_prof_course_hours": """
        UPDATE courses_professors
        SET avg_prof_course_hours = (
            SELECT 
                (
                    COALESCE(SUM(c.less_five * 2.5), 0) +
                    COALESCE(SUM(c.five_to_ten * 7.5), 0) +
                    COALESCE(SUM(c.ten_to_fifteen * 12.5), 0) +
                    COALESCE(SUM(c.fifteen_to_twenty * 17.5), 0) +
                    COALESCE(SUM(c.twenty_to_twenty_five * 22.5), 0) +
                    COALESCE(SUM(c.twenty_five_to_thirty * 27.5), 0) +
                    COALESCE(SUM(c.more_thirty * 32.5), 0)
                ) / NULLIF(
                    (
                        COALESCE(SUM(c.less_five), 0) +
                        COALESCE(SUM(c.five_to_ten), 0) +
                        COALESCE(SUM(c.ten_to_fifteen), 0) +
                        COALESCE(SUM(c.fifteen_to_twenty), 0) +
                        COALESCE(SUM(c.twenty_to_twenty_five), 0) +
                        COALESCE(SUM(c.twenty_five_to_thirty), 0) +
                        COALESCE(SUM(c.more_thirty), 0)
                    ), 0
                )
            FROM courses_professors cp_inner
            JOIN courses c ON cp_inner.course_id = c.id
            WHERE cp_inner.professor_id = courses_professors.professor_id
              AND c.dept = (SELECT dept FROM courses WHERE id = courses_professors.course_id)
              AND c.course_id = (SELECT course_id FROM courses WHERE id = courses_professors.course_id)
        )
        WHERE EXISTS (
            SELECT 1
            FROM courses_professors cp_inner
            JOIN courses c ON cp_inner.course_id = c.id
            WHERE cp_inner.professor_id = courses_professors.professor_id
              AND c.dept = (SELECT dept FROM courses WHERE id = courses_professors.course_id)
              AND c.course_id = (SELECT course_id FROM courses WHERE id = courses_professors.course_id)
        );
    """,
    "avg_prof_course_rating": """
        UPDATE courses_professors
        SET avg_prof_course_rating = (
            SELECT 
                (
                    COALESCE(SUM(c.challenge_intellect), 0) +
                    COALESCE(SUM(c.purpose), 0) +
                    COALESCE(SUM(c.standards), 0) +
                    COALESCE(SUM(c.feedback), 0) +
                    COALESCE(SUM(c.fairness), 0) +
                    COALESCE(SUM(c.respect), 0) +
                    COALESCE(SUM(c.excellence), 0) +
                    COALESCE(SUM(c.organization), 0) +
                    COALESCE(SUM(c.challenge), 0) +
                    COALESCE(SUM(c.available), 0) +
                    COALESCE(SUM(c.inclusive), 0) +
                    COALESCE(SUM(c.significant), 0)
                ) / NULLIF(
                    (
                        COUNT(c.challenge_intellect) +
                        COUNT(c.purpose) +
                        COUNT(c.standards) +
                        COUNT(c.feedback) +
                        COUNT(c.fairness) +
                        COUNT(c.respect) +
                        COUNT(c.excellence) +
                        COUNT(c.organization) +
                        COUNT(c.challenge) +
                        COUNT(c.available) +
                        COUNT(c.inclusive) +
                        COUNT(c.significant)
                    ), 0
                )
            FROM courses_professors cp_inner
            JOIN courses c ON cp_inner.course_id = c.id
            WHERE cp_inner.professor_id = courses_professors.professor_id
              AND c.dept = (
                  SELECT dept FROM courses WHERE id = courses_professors.course_id
              )
              AND c.course_id = (
                  SELECT course_id FROM courses WHERE id = courses_professors.course_id
              )
        )
        WHERE EXISTS (
            SELECT 1
            FROM courses_professors cp_inner
            JOIN courses c ON cp_inner.course_id = c.id
            WHERE cp_inner.professor_id = courses_professors.professor_id
              AND c.dept = (
                  SELECT dept FROM courses WHERE id = courses_professors.course_id
              )
              AND c.course_id = (
                  SELECT course_id FROM courses WHERE id = courses_professors.course_id
              )
        );
    """,
    "avg_course_hours": """
        UPDATE courses
        SET avg_course_hours = (
            SELECT
                SUM(weighted_hours) / NULLIF(SUM(total_responses), 0)
            FROM (
                SELECT
                    (
                        COALESCE(c2.less_five, 0) * 2.5 +
                        COALESCE(c2.five_to_ten, 0) * 7.5 +
                        COALESCE(c2.ten_to_fifteen, 0) * 12.5 +
                        COALESCE(c2.fifteen_to_twenty, 0) * 17.5 +
                        COALESCE(c2.twenty_to_twenty_five, 0) * 22.5 +
                        COALESCE(c2.twenty_five_to_thirty, 0) * 27.5 +
                        COALESCE(c2.more_thirty, 0) * 32.5
                    ) AS weighted_hours,
                    (
                        COALESCE(c2.less_five, 0) +
                        COALESCE(c2.five_to_ten, 0) +
                        COALESCE(c2.ten_to_fifteen, 0) +
                        COALESCE(c2.fifteen_to_twenty, 0) +
                        COALESCE(c2.twenty_to_twenty_five, 0) +
                        COALESCE(c2.twenty_five_to_thirty, 0) +
                        COALESCE(c2.more_thirty, 0)
                    ) AS total_responses
                FROM courses c2
                WHERE c2.dept = courses.dept AND c2.course_id = courses.course_id
            ) sub
            WHERE sub.total_responses > 0
        );
    """,
    "avg_course_rating": """
        UPDATE courses
        SET avg_course_rating = (
            SELECT AVG(rating)
            FROM (
                SELECT
                    (
                        COALESCE(c2.challenge_intellect, 0) +
                        COALESCE(c2.purpose, 0) +
                        COALESCE(c2.standards, 0) +
                        COALESCE(c2.feedback, 0) +
                        COALESCE(c2.fairness, 0) +
                        COALESCE(c2.respect, 0) +
                        COALESCE(c2.excellence, 0)
                    ) /
                    NULLIF(
                        (c2.challenge_intellect IS NOT NULL) +
                        (c2.purpose IS NOT NULL) +
                        (c2.standards IS NOT NULL) +
                        (c2.feedback IS NOT NULL) +
                        (c2.fairness IS NOT NULL) +
                        (c2.respect IS NOT NULL) +
                        (c2.excellence IS NOT NULL),
                        0
                    ) AS rating
                FROM courses AS c2
                INNER JOIN courses_professors AS cp ON c2.id = cp.course_id
                INNER JOIN professors AS p ON cp.professor_id = p.id
                WHERE p.dept = courses.dept AND p.last_name = courses_professors.last_name
            ) sub
            WHERE rating IS NOT NULL
        );
    """,
    "avg_professor_rating": """
        UPDATE professors AS p_outer
        SET avg_professor_rating = (
            SELECT AVG(rating)
            FROM (
                SELECT
                    (
                        COALESCE(c.organization, 0) +
                        COALESCE(c.challenge, 0) +
                        COALESCE(c.available, 0) +
                        COALESCE(c.inclusive, 0) +
                        COALESCE(c.significant, 0)
                    ) /
                    NULLIF(
                        (c.organization IS NOT NULL) +
                        (c.challenge IS NOT NULL) +
                        (c.available IS NOT NULL) +
                        (c.inclusive IS NOT NULL) +
                        (c.significant IS NOT NULL),
                        0
                    ) AS rating
                FROM courses AS c
                INNER JOIN courses_professors AS cp ON c.id = cp.course_id
                INNER JOIN professors AS p ON cp.professor_id = p.id
                WHERE p.dept = p_outer.dept AND p.last_name = p_outer.last_name
            ) sub
            WHERE rating IS NOT NULL
        );
    """
}

# ----------------------------
# Logging Configuration
# ----------------------------

logging.basicConfig(
    filename=ERROR_LOG_PATH,
    filemode='a',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# ----------------------------
# Main Execution
# ----------------------------

if __name__ == "__main__":
    print("Starting updates...")
    execute_sql_queries(DATABASE_PATH, SQL_QUERIES)
    print("Updates completed.")