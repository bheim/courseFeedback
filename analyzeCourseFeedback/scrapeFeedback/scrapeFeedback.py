import sqlite3
import time
import pickle
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from imageProcessor import process_image
from webdriver_manager.chrome import ChromeDriverManager

# Number of parallel workers (I pushed 10 one time but you could probably go even higher. This speeds things up significantly)
NUM_WORKERS = 1

# Threading lock for database writes
db_lock = threading.Lock()

# Load cookies from file and add to Selenium browser session
def load_cookies(driver, cookies_file):
    with open(cookies_file, 'rb') as file:
        cookies = pickle.load(file)

    for cookie in cookies:
        if 'expiry' in cookie:
            cookie['expiry'] = int(cookie['expiry'])
        driver.add_cookie(cookie)

# Create a new WebDriver instance
def create_driver():
    chrome_options = Options()
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    
    # Navigate to the domain first
    driver.get('https://uchicago.bluera.com/uchicago/')
    time.sleep(1)
    
    # Load cookies
    with open('../../cookies/cookies.pkl', 'rb') as file:
        cookies = pickle.load(file)
    
    for cookie in cookies:
        if 'domain' in cookie:
            del cookie['domain']
        if 'expiry' in cookie:
            cookie['expiry'] = int(cookie['expiry'])
        try:
            driver.add_cookie(cookie)
        except Exception as e:
            print(f"Could not add cookie: {e}")
    
    driver.refresh()
    time.sleep(1)
    
    # DEBUG: Check if we're authenticated
    print(f"DEBUG: Page title after login: {driver.title}")
    
    return driver

# Check if the quarter falls in the COVID-era
def is_covid_era(quarter):
    covid_quarters = ['Winter 2019', 'Spring 2020', 'Summer 2020', 'Autumn 2020', 'Winter 2021', 'Spring 2021']
    return quarter in covid_quarters

# Extract the course header information (course name, instructors, quarter)
def extract_header_info(driver):
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    header = soup.find('div', class_='header')

    course_info = header.find('h2').text.strip()
    course_name = course_info.split(" - ")[0].strip()
    if "Instructor(s)" in course_info:
        instructor_part = course_info.split("Instructor(s)")[1].strip()
        if instructor_part.startswith(":") or instructor_part.startswith("-"):
            instructor_part = instructor_part[1:].strip()
        instructors = [instructor.strip() for instructor in instructor_part.split(",")]
    else:
        instructors = []

    project_title_element = header.find('span', id=lambda x: x and 'ProjectTitle' in x)
    
    if project_title_element:
        quarter_info = project_title_element.find_next('dd').text.strip()
        quarter = " ".join(quarter_info.split()[-2:])
    else:
        quarter = "Unknown Quarter"

    return course_name, instructors, quarter

# Extract rating tables with questions and ratings
def extract_rating_tables(driver):
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    tables = {}

    for block in soup.find_all('div', class_='report-block'):
        title = block.find(['h3', 'h4'], class_='ReportBlockTitle')
        if title:
            table_title = title.text.strip()
            table_data = []

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

    for block in soup.find_all('div', class_='FrequencyBlock_FullMain'):
        title_element = block.find('div', class_='FrequencyQuestionTitle')
        if title_element is None:
            continue
        title_element = block.find('div', class_='FrequencyQuestionTitle').find('span')
        if title_element:
            table_title = title_element.text.strip()
            table_data = []

            table = block.find('table', class_='CondensedTabularFixedHalfWidth')
            if table:
                for row in table.find_all('tr'):
                    stat_name_cell = row.find('th')
                    stat_value_cell = row.find('td')
                    if stat_name_cell and stat_value_cell:
                        stat_name = stat_name_cell.text.strip()
                        stat_value = stat_value_cell.text.strip()
                        table_data.append({stat_name: stat_value})
            
            tables[table_title] = table_data

    return tables

def extract_bio_rating_tables(driver):
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    tables = {}

    report_blocks = soup.find_all('div', class_='report-block')
    for block in report_blocks:
        title_tag = block.find('h3', class_='ReportBlockTitle')
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True)

        stats_table = block.find('table', class_='CondensedTabularFixedHalfWidth')
        table_data = {}
        if stats_table:
            for row in stats_table.find_all('tr'):
                cells = row.find_all(['th', 'td'])
                if len(cells) == 2:
                    key = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    table_data[key] = value

        chart_div = block.find('div', class_='FrequencyBlock_chart')
        image_url = None
        if chart_div:
            img_tag = chart_div.find('img')
            if img_tag and 'src' in img_tag.attrs:
                image_url = img_tag['src']

        tables[title] = {
            'statistics': table_data,
            'image_url': image_url,
        }

    frequency_blocks = soup.find_all('div', class_='FrequencyBlock_FullMain')
    for block in frequency_blocks:
        title_tag = block.find('span', id=lambda x: x and "BaseReportBlockUCPreview" in x)
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True)

        stats_table = block.find('table', class_='block-table CondensedTabularFixedHalfWidth')
        table_data = {}
        if stats_table:
            for row in stats_table.find_all('tr'):
                cells = row.find_all(['th', 'td'])
                if len(cells) == 2:
                    key = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    table_data[key] = value

        chart_div = block.find('div', class_='FrequencyBlock_chart')
        image_url = None
        if chart_div:
            img_tag = chart_div.find('img')
            if img_tag and 'src' in img_tag.attrs:
                image_url = img_tag['src']

        tables[title] = {
            'statistics': table_data,
            'image_url': image_url,
        }

    return tables


def extract_instructor_rating_value(tables, question_title):
    rating_table = tables.get('The Instructor . . .', [])
    
    for row in rating_table:
        if row['question'] == question_title:
            return float(row.get('Mean', 0))
    
    return None

def extract_image_url(driver):
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    
    question_title = "How many hours per week outside of attending required sessions did you spend on this course?"

    question_block = soup.find('h3', string=re.compile(re.escape(question_title), re.IGNORECASE))

    if not question_block:
        question_block = soup.find('span', string=re.compile(re.escape(question_title), re.IGNORECASE))
        if not question_block:
            return None

    image_chart_div = question_block.find_next('div', class_='FrequencyBlock_chart')
    if image_chart_div:
        img_tag = image_chart_div.find('img')
        if img_tag and 'src' in img_tag.attrs:
            return img_tag['src']
    return None

def extract_bio_image_url(driver):
    soup = BeautifulSoup(driver.page_source, 'html.parser')

    question_title = "How many hours per week outside of attending required sessions did you spend on this course?"

    question_block = soup.find('span', string=re.compile(re.escape(question_title), re.IGNORECASE))

    if not question_block:
        print(f"Question title '{question_title}' not found.")
        return None

    image_chart_div = question_block.find_next('div', class_='FrequencyBlock_chart')
    if image_chart_div:
        img_tag = image_chart_div.find('img')
        if img_tag and 'src' in img_tag.attrs:
            return img_tag['src']

    print(f"No image found for question title: '{question_title}'")
    return None


def insert_professors(professors, dept, conn):
    cursor = conn.cursor()
    professor_ids = []
    
    for professor in professors:
        name_parts = professor.split()
        
        if len(name_parts) == 0:
            print(f"No professor name found for department: {dept}. Skipping insertion.")
            continue

        if len(name_parts) > 2:
            first_name = name_parts[0]
            last_name = " ".join(name_parts[1:])
        elif len(name_parts) == 2:
            first_name, last_name = name_parts
        else:
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


def insert_course_professors(course_id, professor_ids, conn):
    cursor = conn.cursor()
    
    for professor_id in professor_ids:
        cursor.execute("""
            INSERT INTO courses_professors (course_id, professor_id) 
            VALUES (?, ?)
        """, (course_id, professor_id))


def insert_course_data(course_data, conn):
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO courses 
        (dept, quarter, course_id, challenge_intellect, purpose, standards, feedback, fairness, respect, excellence, organization, challenge, available, inclusive, significant, less_five, five_to_ten, ten_to_fifteen, fifteen_to_twenty, twenty_to_twenty_five, twenty_five_to_thirty, more_thirty, url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        course_data['dept'], course_data['quarter'], course_data['course_id'], 
        course_data['challenge_intellect'], course_data['purpose'], course_data['standards'], 
        course_data['feedback'], course_data['fairness'], course_data['respect'], 
        course_data['excellence'], course_data['organization'], course_data['challenge'], 
        course_data['available'], course_data['inclusive'], course_data['significant'], 
        course_data['less_five'], course_data['five_to_ten'], course_data['ten_to_fifteen'], 
        course_data['fifteen_to_twenty'], course_data['twenty_to_twenty_five'], 
        course_data['twenty_five_to_thirty'], course_data['more_thirty'], course_data['url']
    ))

    course_id = cursor.lastrowid
    return course_id

def extract_rating_value(tables, question_title):
    rating_table = tables.get('Please respond to the following:', [])
    
    for row in rating_table:
        if row['question'] == question_title:
            return float(row.get('Mean', 0))
    
    return None


def extract_bio_rating_value(rating_tables, target_titles):
    mean_values = []

    for title in target_titles:
        block_data = rating_tables.get(title, {})
        if not block_data:
            print(f"Warning: No data found for title: {title}")
            continue

        statistics = block_data.get('statistics', {})
        mean_str = statistics.get('Mean', None)
        if mean_str is not None:
            try:
                mean_values.append(float(mean_str))
            except ValueError:
                print(f"Error: Unable to convert 'Mean' to float for title: {title}")

    if not mean_values:
        print("No valid 'Mean' values found.")
        return None

    average_mean = sum(mean_values) / len(mean_values)
    return average_mean


def processLink(driver, link):
    driver.get(link)
    time.sleep(2)

    course_name, instructors, quarter = extract_header_info(driver)

    if is_covid_era(quarter):
        print(f"Skipping {course_name} for {quarter} (COVID-19 era)")
        return None

    dept = course_name.split()[0]

    rating_tables = extract_rating_tables(driver)

    image_url = extract_image_url(driver)
    if image_url:
        counts = process_image(image_url)
        total_responses = sum(counts.values())
        percentages = {key: round((value / total_responses) * 100, 2) for key, value in counts.items()}
    else:
        percentages = {}

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
        'more_thirty': percentages.get('>30 hours', None),
        'url': link
    }
    }

    return allData


def processBioLink(driver, link):
    try:
        driver.get(link)
        time.sleep(2)
        
        course_name, instructors, quarter = extract_header_info(driver)
        
        if is_covid_era(quarter):
            print(f"Skipping {course_name} for {quarter} (COVID-19 era)")
            return None
        
        dept = course_name.split()[0]
        
        rating_tables = extract_bio_rating_tables(driver)

        target_titles = [
            "The learning objectives of the course were clear and I understood how to  achieve them.",
            "The course helped me to make important progress toward the stated  objectives.",
            "The graded elements of the course were directed toward assessing my progress toward the stated course objectives.",
            "Overall, this was an excellent course."
        ]

        normalized_target_titles = [title + " " for title in target_titles]

        average_mean = (
            extract_bio_rating_value(rating_tables, target_titles)
            or extract_bio_rating_value(rating_tables, normalized_target_titles)
        )
        
        image_url = extract_bio_image_url(driver)
        if image_url:
            counts = process_image(image_url)
            total_responses = sum(counts.values())
            percentages = {key: round((value / total_responses) * 100, 2) for key, value in counts.items()}
        else:
            percentages = {}
        
        allData = {
            "instructors": instructors,
            "dept": dept,
            "quarter": quarter,
            "course_data": {
                'dept': dept,
                'quarter': quarter,
                'course_id': int(course_name.split()[1]),
                'challenge_intellect': average_mean,
                'purpose': average_mean,
                'standards': average_mean,
                'feedback': average_mean,
                'fairness': average_mean,
                'respect': average_mean,
                'excellence': average_mean,
                'organization': average_mean,
                'challenge': average_mean,
                'available': average_mean,
                'inclusive': average_mean,
                'significant': average_mean,
                'less_five': percentages.get('<5 hours', 0),
                'five_to_ten': percentages.get('5-10 hours', 0),
                'ten_to_fifteen': percentages.get('10-15 hours', 0),
                'fifteen_to_twenty': percentages.get('15-20 hours', 0),
                'twenty_to_twenty_five': percentages.get('20-25 hours', 0),
                'twenty_five_to_thirty': percentages.get('25-30 hours', 0),
                'more_thirty': percentages.get('>30 hours', None),
                
                'url': link
            }
        }
        
        return allData
    
    except Exception as e:
        print(f"Error processing BIO link {link}: {e}")
        return None


def save_to_database(allData):
    """Save course data to database with thread safety"""
    if allData is None:
        return
    
    with db_lock:
        conn = sqlite3.connect('../course_feedback.db', timeout=30)
        
        new_course_id = insert_course_data(allData.get("course_data"), conn)
        professor_ids = insert_professors(allData.get("instructors"), allData.get("dept"), conn)
        if professor_ids:
            insert_course_professors(new_course_id, professor_ids, conn)
        else:
            print(f"No professors found for course {allData['course_data']['course_id']}. Skipping course-professor mapping.")
        
        conn.commit()
        conn.close()


def worker(worker_id, driver, url_list):
    """Each driver processes its own list of URLs sequentially"""
    processed = 0
    for url_tuple in url_list:
        row_id, course_dept, course_id, url = url_tuple
        print(f"[Worker {worker_id}] Processing {course_dept} {course_id}: {url}")
        try:
            if course_dept == "BIOS":
                allData = processBioLink(driver, url)
            else:
                allData = processLink(driver, url)
            
            if allData:
                save_to_database(allData)
                processed += 1
        except Exception as e:
            print(f"[Worker {worker_id}] Error processing {url}: {e}")
    
    print(f"[Worker {worker_id}] Finished. Processed {processed} courses.")
    return processed


def main():
    # Create driver pool
    print(f"Creating {NUM_WORKERS} WebDriver instances...")
    drivers = []
    for i in range(NUM_WORKERS):
        print(f"Creating driver {i+1}/{NUM_WORKERS}...")
        drivers.append(create_driver())
        time.sleep(2)  # Small delay between driver creation
    print("All drivers created.")

    # Open database connection for fetching URLs
    connToLinks = sqlite3.connect('../getCourseLinks/course_urls.db')
    connToLinks.execute("ATTACH DATABASE '../course_feedback.db' AS feedback_db")

    cursorToLinks = connToLinks.cursor()

    # Select only URLs that don't already exist in course_feedback.db
    cursorToLinks.execute("""
        SELECT cu.id, cu.department, cu.course_id, cu.url 
        FROM course_urls cu
        LEFT JOIN feedback_db.courses c 
            ON cu.url = c.url
        WHERE c.id IS NULL
    """)
    urls = cursorToLinks.fetchall()
    connToLinks.close()
    
    print(f"Found {len(urls)} new courses to scrape")

    if len(urls) == 0:
        print("No new courses to scrape. Exiting.")
        for driver in drivers:
            driver.quit()
        return

    # Split URLs among workers
    url_chunks = [[] for _ in range(NUM_WORKERS)]
    for i, url_tuple in enumerate(urls):
        url_chunks[i % NUM_WORKERS].append(url_tuple)

    print(f"Split {len(urls)} URLs among {NUM_WORKERS} workers:")
    for i, chunk in enumerate(url_chunks):
        print(f"  Worker {i}: {len(chunk)} URLs")

    # Run workers in parallel
    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
        futures = []
        for i in range(NUM_WORKERS):
            futures.append(executor.submit(worker, i, drivers[i], url_chunks[i]))
        
        # Wait for all to complete and collect results
        total_processed = 0
        for future in as_completed(futures):
            try:
                processed = future.result()
                total_processed += processed
            except Exception as e:
                print(f"Worker error: {e}")

    print(f"\nTotal courses processed: {total_processed}")

    # Cleanup
    print("Closing WebDrivers...")
    for driver in drivers:
        driver.quit()

    print("Scraping complete!")


if __name__ == "__main__":
    main()