# This script will scrap all the course ids from the course catalog into all_course_ids.db, which then can be used to automate searching
# for courses on the course search page.

import requests
from bs4 import BeautifulSoup
import sqlite3
import time

# Base URL for UChicago program study page (contains sidebar with departments)
base_url = 'http://collegecatalog.uchicago.edu/thecollege/programsofstudy/'
base_core_url = 'http://collegecatalog.uchicago.edu/thecollege/'
core_urls_add_ons = ['artscore/', 'biologicalsciencescore/', 'civilizationstudies/', 
                     'humanities/', '#languagecompetence/', 'mathematicalsciencescore/',
                      'physicalsciences/', 'socialsciences/']

# SQLite database setup
def setup_database():
    conn = sqlite3.connect('all_course_ids.db')  # Changed database name
    cursor = conn.cursor()
    
    # Create a table to store the course data
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            department TEXT,
            course_id TEXT
        )
    ''')
    
    conn.commit()
    return conn

# Function to save a course to the database
def save_course(conn, department, course_id):
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO courses (department, course_id)
        VALUES (?, ?)
    ''', (department, course_id))
    conn.commit()

# Function to scrape courses from a specific department page
def scrape_courses(conn, department_url, department_name):
    response = requests.get(department_url)
    
    if response.status_code != 200:
        print(f"Failed to retrieve page for {department_name}. Status code: {response.status_code}")
        return
    
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Find all course titles in <p class="courseblocktitle">
    course_elements = soup.find_all('p', class_='courseblocktitle')
    
    for course_element in course_elements:
        # Extract the course ID from the text, e.g., "ANTH 10100"
        course_text = course_element.get_text(strip=True)
        course_id = course_text.split('.')[0].strip()  # Get only the department and course ID
        if ("-" in course_id):
            continue
        
        # Save the course to the database
        save_course(conn, department_name, course_id)

# Function to scrape all departments listed in the sidebar
def scrape_all_departments(conn):
    response = requests.get(base_url)
    
    if response.status_code != 200:
        print(f"Failed to retrieve program study page. Status code: {response.status_code}")
        return
    
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Find all department links in the sidebar
    department_links = soup.select('ul.nav.leveltwo li a')
    
    for link in department_links:
        department_name = link.text.strip()
        department_url = link['href']
        
        # Handle relative URLs by prepending the base URL
        if department_url.startswith('/'):
            department_url = 'http://collegecatalog.uchicago.edu' + department_url
        
        print(f"Scraping department: {department_name}")
        
        # Scrape courses for the current department
        scrape_courses(conn, department_url, department_name)
        
        # Be polite and avoid hammering the server (adjust the delay as needed)
        time.sleep(1)
    for link in core_urls_add_ons:
        core_url = 'http://collegecatalog.uchicago.edu/' + link
        scrape_courses(conn, core_url, link)
        time.sleep(1)

# Main function to set up the database and scrape all departments
def main():
    # Set up the SQLite database
    conn = setup_database()
    
    # Scrape courses from all departments
    scrape_all_departments(conn)
    
    # Close the database connection when done
    conn.close()
    print("Scraping completed and database closed.")

if __name__ == "__main__":
    main()
