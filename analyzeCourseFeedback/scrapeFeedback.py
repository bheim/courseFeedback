import sqlite3
import time
import pickle
import re
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from imageProcessor import process_image  # Assuming you have the process_image function in process_image.py

# Load cookies from file and add to Selenium browser session
def load_cookies(driver, cookies_file):
    with open(cookies_file, 'rb') as file:
        cookies = pickle.load(file)

    for cookie in cookies:
        if 'expiry' in cookie:
            cookie['expiry'] = int(cookie['expiry'])
        driver.add_cookie(cookie)

# Check if the quarter falls in the COVID-era (Spring 2020, Autumn 2020, Winter 2021, Spring 2021)
def is_covid_era(quarter):
    covid_quarters = ['Spring 2020', 'Autumn 2020', 'Winter 2021', 'Spring 2021']
    return quarter in covid_quarters

# Extract the course header information (course name, instructors, quarter)
def extract_header_info(driver):
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    header = soup.find('div', class_='header')

    # Get course name and instructors
    course_info = header.find('h2').text.strip()
    course_name = course_info.split(" - ")[0].strip()  # Extract course name
    if "Instructor(s)" in course_info:
        # Split on 'Instructor(s)' to get the part after it
        instructor_part = course_info.split("Instructor(s)")[1].strip()

        # Remove any leading colons if they exist (to handle both formats)
        if instructor_part.startswith(":") or instructor_part.startswith("-"):
            instructor_part = instructor_part[1:].strip()

        # Split by comma if there are multiple instructors, else just return a single instructor
        instructors = [instructor.strip() for instructor in instructor_part.split(",")]
    else:
        instructors = []  # Default to empty list if no instructors are found

    # Get quarter information by looking for the correct <span> tag or by the Project Title field
    project_title_element = header.find('span', id=lambda x: x and 'ProjectTitle' in x)
    
    if project_title_element:
        quarter_info = project_title_element.find_next('dd').text.strip()
        quarter = " ".join(quarter_info.split()[-2:])  # Extract the last two words (e.g., 'Autumn 2022')
    else:
        quarter = "Unknown Quarter"

    return course_name, instructors, quarter

# Extract rating tables with questions and ratings
def extract_rating_tables(driver):
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    tables = {}
    
    # Loop through all report blocks
    for block in soup.find_all('div', class_='report-block'):
        title = block.find(['h3', 'h4'], class_='ReportBlockTitle')
        if title:
            table_title = title.text.strip()
            table_data = []

            # Find the table within the block
            table = block.find('table', class_='CondensedTabular')
            if table:
                headers = [th.text.strip() for th in table.find_all('th')[1:]]
                for row in table.find_all('tr')[1:]:
                    cells = row.find_all(['th', 'td'])
                    if cells:
                        row_data = {
                            'question': cells[0].text.strip(),
                            **{headers[i]: cells[i+1].text.strip() for i in range(len(headers)) if i+1 < len(cells)}
                        }
                        table_data.append(row_data)
            
            tables[table_title] = table_data

    return tables

# Extract the instructor rating value from "The Instructor . . ." table
def extract_instructor_rating_value(tables, question_title):
    rating_table = tables.get('The Instructor . . .', [])
    
    for row in rating_table:
        if row['question'] == question_title:
            return float(row.get('Mean', 0))
    
    return None

# Extract the image URL based on the question title
def extract_image_url(driver):
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    
    question_title = "How many hours per week outside of attending required sessions did you spend on this course?"

    # Try to find the question in h3 or span tags
    question_block = soup.find('h3', string=re.compile(re.escape(question_title), re.IGNORECASE))

    if not question_block:
        question_block = soup.find('span', string=re.compile(re.escape(question_title), re.IGNORECASE))
        if not question_block:
            return None

    # Find the next div with class 'FrequencyBlock_chart' after the question block
    image_chart_div = question_block.find_next('div', class_='FrequencyBlock_chart')
    if image_chart_div:
        img_tag = image_chart_div.find('img')
        if img_tag and 'src' in img_tag.attrs:
            return img_tag['src']
    return None

# Insert professors into the professors table with error handling for missing names
def insert_professors(professors, dept, conn):
    cursor = conn.cursor()
    professor_ids = []
    
    for professor in professors:
        name_parts = professor.split()
        
        if len(name_parts) == 0:
            print(f"No professor name found for department: {dept}. Skipping insertion.")
            continue  # Skip this professor if no name is provided

        if len(name_parts) > 2:
            first_name = name_parts[0]
            last_name = " ".join(name_parts[1:])
        elif len(name_parts) == 2:
            first_name, last_name = name_parts
        else:
            # If there's only one part (unlikely but possible), we'll treat it as the last name
            first_name = ""
            last_name = name_parts[0]
            print(f"Only one name part found ('{last_name}') for department: {dept}. Inserting as last name only.")

        cursor.execute("""
            SELECT id FROM professors WHERE first_name = ? AND last_name = ? AND dept = ?
        """, (first_name, last_name, dept))
        result = cursor.fetchone()

        if result is None:
            cursor.execute("""
                INSERT INTO professors (dept, first_name, last_name) 
                VALUES (?, ?, ?)
            """, (dept, first_name, last_name))
            professor_id = cursor.lastrowid
        else:
            professor_id = result[0]
        
        professor_ids.append(professor_id)
    
    return professor_ids


# Insert course-professor mappings into courses_professors table
def insert_course_professors(course_id, professor_ids, conn):
    cursor = conn.cursor()
    
    for professor_id in professor_ids:
        cursor.execute("""
            INSERT INTO courses_professors (course_id, professor_id) 
            VALUES (?, ?)
        """, (course_id, professor_id))

    conn.commit()

# Insert course data into the courses table
def insert_course_data(course_data, conn):
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO courses 
        (dept, quarter, course_id, challenge_intellect, purpose, standards, feedback, fairness, respect, excellence, organization, challenge, available, inclusive, significant, less_five, five_to_ten, ten_to_fifteen, fifteen_to_twenty, twenty_to_twenty_five, twenty_five_to_thirty, more_thirty)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        course_data['dept'], course_data['quarter'], course_data['course_id'], 
        course_data['challenge_intellect'], course_data['purpose'], course_data['standards'], 
        course_data['feedback'], course_data['fairness'], course_data['respect'], 
        course_data['excellence'], course_data['organization'], course_data['challenge'], 
        course_data['available'], course_data['inclusive'], course_data['significant'], 
        course_data['less_five'], course_data['five_to_ten'], course_data['ten_to_fifteen'], 
        course_data['fifteen_to_twenty'], course_data['twenty_to_twenty_five'], 
        course_data['twenty_five_to_thirty'], course_data['more_thirty']
    ))

    course_id = cursor.lastrowid
    conn.commit()
    return course_id

# Extract specific rating values dynamically
def extract_rating_value(tables, question_title):
    rating_table = tables.get('Please respond to the following:', [])
    
    for row in rating_table:
        if row['question'] == question_title:
            return float(row.get('Mean', 0))
    
    return None


def processLink(driver, link):
    driver.get(link)
    time.sleep(2)

    # Step 1: Extract header info (course name, instructors, quarter)
    course_name, instructors, quarter = extract_header_info(driver)

    # Ignore the data if it falls within the COVID-19 quarters
    if is_covid_era(quarter):
        print(f"Skipping {course_name} for {quarter} (COVID-19 era)")
        return None

    dept = course_name.split()[0]  # Extract the department dynamically from course name

    # Step 2: Extract rating tables
    rating_tables = extract_rating_tables(driver)

    # Step 3: Extract image URL for hours worked and process it
    image_url = extract_image_url(driver)
    if image_url:
        counts = process_image(image_url)  # Process the image to get the counts
        # Convert counts to percentages
        total_responses = sum(counts.values())
        percentages = {key: round((value / total_responses) * 100, 2) for key, value in counts.items()}
    else:
        percentages = {}

    # Step 4: Extract dynamic rating values for specific questions
    allData = {
    "instructors": instructors,
    "dept": dept,
    "quarter": quarter,
    "course_data": {
        'dept': dept,
        'quarter': quarter,
        'course_id': int(course_name.split()[1]),
        'challenge_intellect': extract_rating_value(rating_tables, "This course challenged me intellectually."),
        'purpose': extract_rating_value(rating_tables, "I understood the purpose of this course and what I was expected to gain from it."),
        'standards': extract_rating_value(rating_tables, "I understood the standards for success on assignments."),
        'feedback': extract_rating_value(rating_tables, "I received feedback on my performance that helped me improve my subsequent work."),
        'fairness': extract_rating_value(rating_tables, "My work was evaluated fairly."),
        'respect': extract_rating_value(rating_tables, "I felt respected in this class."),
        'excellence': extract_rating_value(rating_tables, "Overall, this was an excellent course."),
        'organization': extract_instructor_rating_value(rating_tables, "Organized the course clearly."),
        'challenge': extract_instructor_rating_value(rating_tables, "Challenged you to learn."),
        'available': extract_instructor_rating_value(rating_tables, "Was available and helpful outside of class."),
        'inclusive': extract_instructor_rating_value(rating_tables, "Worked to create an inclusive and welcoming learning environment."),
        'significant': extract_instructor_rating_value(rating_tables, "Helped you gain significant learning from the course content."),
        'less_five': percentages.get('<5 hours', 0),
        'five_to_ten': percentages.get('5-10 hours', 0),
        'ten_to_fifteen': percentages.get('10-15 hours', 0),
        'fifteen_to_twenty': percentages.get('15-20 hours', 0),
        'twenty_to_twenty_five': percentages.get('20-25 hours', 0),
        'twenty_five_to_thirty': percentages.get('25-30 hours', 0),
        'more_thirty': percentages.get('>30 hours', None)
    }
    }

    return allData


# Main function to control Selenium
def main():
        
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Enable headless mode
    chrome_options.add_argument("--disable-gpu") 
    driver_service = Service("/opt/homebrew/bin/chromedriver")
    driver = webdriver.Chrome(service=driver_service, options=chrome_options)

    driver.get('https://uchicago.bluera.com/uchicago/')  # Open the base URL first
    cookies_file = 'cookies.pkl'  # Path to your cookies.pkl
    load_cookies(driver, cookies_file)
    driver.refresh()

    # Open database connection
    conn = sqlite3.connect('course_feedback.db')
    connToLinks = sqlite3.connect('course_urls.db')

    cursorToLinks = connToLinks.cursor()
    cursorToLinks.execute("SELECT url FROM course_urls")
    urls = cursorToLinks.fetchall()

    for url_tuple in urls:
        url = url_tuple[0]
        print(url)
        allData = processLink(driver, url)

        if allData is None:
            continue

        # Step 5: Insert the course data into the courses table
        course_id = insert_course_data(allData.get("course_data"), conn)

        # Step 6: Insert professors and course-professor mappings
        professor_ids = insert_professors(allData.get("instructors"), allData.get("dept"), conn)
        if professor_ids:
            insert_course_professors(course_id, professor_ids, conn)
        else:
            print(f"No professors found for course {allData['course_data']['course_id']}. Skipping course-professor mapping.")

    conn.close()
    driver.quit()

if __name__ == "__main__":
    main()
