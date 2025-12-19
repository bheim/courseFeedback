import requests
import pickle
from bs4 import BeautifulSoup
import sqlite3
import time
import itertools

# Load the login cookies from the pickle file
with open('../../cookies/cookies.pkl', 'rb') as f:
    cookies = pickle.load(f)

# Create a requests session and load the cookies
session = requests.Session()

# Add the cookies to the session
for cookie in cookies:
    session.cookies.set(cookie['name'], cookie['value'])


# Function to clean and split department and course number
def split_course_id(course):
    parts = course.split("\xa0")  # Split by the non-breaking space
    return parts[0], parts[1] if len(parts) > 1 else None


# Function to extract the year from the quarter column and check if it's 2019 or after
def is_valid_year(quarter_text):
    # Example quarter_text: "(2244) Spring 2024"
    try:
        # Extract quarter and year from the text
        parts = quarter_text.strip().split()
        quarter = parts[-2]  # Example: "Spring"
        year = int(parts[-1])  # Example: "2024"

        # Return False for COVID quarters (Spring 2020 - Spring 2021)
        if (year == 2020 and quarter in ['Spring', 'Summer', 'Autumn']) or \
           (year == 2021 and quarter in ['Winter', 'Spring']):
            return False

        # Otherwise, return True for years 2019 or later
        return year >= 2019

    except (ValueError, IndexError):
        # Return False if parsing fails
        return False

# Function to scrape course feedback links using authenticated requests
def scrape_feedback_links(department, course_number, session):
    url = f"https://coursefeedback.uchicago.edu/?CourseDepartment={department}&CourseNumber={course_number}"
    print("The url is", url)
    try:
        # Make the request using the session object (with cookies)
        response = session.get(url)
        
        # Check if the request was successful
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            feedback_links = []

            # Iterate through each row and extract relevant information
            for row in soup.find_all("tr"):
                quarter_cell = row.find("td", class_="quarter")
                if quarter_cell and is_valid_year(quarter_cell.text):  # Check if the year is >= 2019
                    course_link = row.find("td", class_="course").find("a")
                    if course_link:
                        feedback_links.append(course_link['href'])
            print(f"Course: {department} {course_number}, New links: {feedback_links}")
            return feedback_links
        else:
            print(f"Failed to access {url}: {response.status_code}")
            return []
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return []
    

# Database paths
db_path = '../getCourseIDs/all_course_ids.db' 
output_db_path = 'course_urls.db'

# Open the course database and the output database
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

# Fetch all course entries from the input database
cursor_input.execute("SELECT department, course_id FROM courses")
courses = cursor_input.fetchall()

# Function to process courses in batches
def process_courses_in_batches(courses, batch_size=25):
    # Loop through the courses in chunks of 'batch_size'
    batch_count = 0
    for i in range(0, len(courses), batch_size):
        batch = courses[i:i + batch_size]  # Slice the courses list in batches
        print(f"This is batch {batch_count}")
        print(f"Processing batch of {len(batch)} courses...")
        for department, course_id in batch:
            department, course_number = split_course_id(course_id)
            if course_number:
                feedback_links = scrape_feedback_links(department, course_number, session)
                for link in feedback_links:
                    cursor_output.execute('''
                        INSERT OR IGNORE INTO course_urls (course_id, department, url) 
                        VALUES (?, ?, ?)
                    ''', (course_id, department, link))
            time.sleep(.1)
        batch_count += 1

        # Commit changes after processing each batch
        conn_output.commit()
        print(f"Batch of {len(batch)} courses processed and committed.")




# Process courses in batches of 500
process_courses_in_batches(courses, batch_size=25)

# Close both database connections
conn_output.close()
conn_input.close()

print("Scraping complete!")
