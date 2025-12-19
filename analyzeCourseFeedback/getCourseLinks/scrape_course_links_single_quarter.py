import requests
import pickle
from bs4 import BeautifulSoup
import sqlite3
import time

# Load the login cookies from the pickle file
with open('../../cookies/cookies.pkl', 'rb') as f:
    cookies = pickle.load(f)

# Create a requests session and load the cookies
session = requests.Session()

# Add the cookies to the session
for cookie in cookies:
    session.cookies.set(cookie['name'], cookie['value'])


# Set the quarter you want to scrape
target_quarter = "Spring 2025"
target_term, target_year = target_quarter.split()

if target_term in ["Winter", "Spring"]:
    target_year = int(target_year) - 1


# Function to scrape course feedback links for an entire department in a specific quarter
def scrape_department_feedback_links(department, year, term, session):
    url = f"https://coursefeedback.uchicago.edu/?Department={department}&AcademicYear={year}&AcademicTerm={term}"
    print(f"Scraping URL: {url}")
    
    try:
        # Make the request using the session object (with cookies)
        response = session.get(url)
        
        # Check if the request was successful
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            feedback_data = []

            # Iterate through each row and extract relevant information
            for row in soup.find_all("tr"):
                course_cell = row.find("td", class_="course")
                if course_cell:
                    course_link = course_cell.find("a")
                    if course_link:
                        # Extract course ID (e.g., "ECON 11020" from "ECON 11020 1")
                        course_text = course_link.get_text(strip=True)
                        course_id = " ".join(course_text.split()[:2])
                        feedback_url = course_link['href']
                        feedback_data.append((course_id, feedback_url))
            
            print(f"Department: {department}, Found {len(feedback_data)} feedback links")
            return feedback_data
        else:
            print(f"Failed to access {url}: {response.status_code}")
            return []
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return []


# Database paths
db_path = '../getCourseIDs/all_course_ids.db'
output_db_path = 'course_urls.db'

# Open the course database to get unique department abbreviations
conn_input = sqlite3.connect(db_path)
cursor_input = conn_input.cursor()

# Connect to the output SQLite database
conn_output = sqlite3.connect(output_db_path)
cursor_output = conn_output.cursor()

# Create table in the output database for storing course URLs
cursor_output.execute('''
    CREATE TABLE IF NOT EXISTS course_urls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_id TEXT,
        department TEXT,
        url TEXT
    )
''')

# Fetch unique department abbreviations from course_id (e.g., "ANTH" from "ANTH 1000")
cursor_input.execute("SELECT DISTINCT course_id FROM courses")
course_ids = [row[0] for row in cursor_input.fetchall()]
dept_abbreviations = list(set(cid.split('\xa0')[0] for cid in course_ids if cid))

print(f"Found {len(dept_abbreviations)} unique department abbreviations to scrape")


# Function to process departments in batches
def process_departments_in_batches(departments, batch_size=25):
    batch_count = 0
    for i in range(0, len(departments), batch_size):
        batch = departments[i:i + batch_size]
        print(f"\nProcessing batch {batch_count} ({len(batch)} departments)...")
        
        for department in batch:
            feedback_data = scrape_department_feedback_links(
                department, target_year, target_term, session
            )
            
            if feedback_data:
                # Batch insert all links for this department
                cursor_output.executemany('''
                    INSERT OR IGNORE INTO course_urls (course_id, department, url) 
                    VALUES (?, ?, ?)
                ''', [(course_id, department, url) for course_id, url in feedback_data])
            
            time.sleep(0.1)
        
        batch_count += 1
        
        # Commit changes after processing each batch
        conn_output.commit()
        print(f"Batch {batch_count - 1} processed and committed.")


# Process departments in batches of 25
process_departments_in_batches(dept_abbreviations, batch_size=25)

# Close both database connections
conn_output.close()
conn_input.close()

print("\nScraping complete!")