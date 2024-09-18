from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import pickle
import time
from bs4 import BeautifulSoup

# Load cookies from file and add to Selenium browser session
def load_cookies(driver, cookies_file):
    with open(cookies_file, 'rb') as file:
        cookies = pickle.load(file)
    
    for cookie in cookies:
        if 'expiry' in cookie:
            cookie['expiry'] = int(cookie['expiry'])
        driver.add_cookie(cookie)

# Extract rating tables with questions and ratings
def extract_rating_tables(driver):
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    tables = {}
    
    # Loop through all report blocks
    for block in soup.find_all('div', class_='report-block'):
        # Extract title from h3 or h4 elements
        title = block.find(['h3', 'h4'], class_='ReportBlockTitle')
        if title:
            table_title = title.text.strip()
            table_data = []
            
            # Find the table within the block
            table = block.find('table', class_='CondensedTabular')
            if table:
                # Extract headers, skipping the first header
                headers = [th.text.strip() for th in table.find_all('th')[1:]]
                
                # Loop through the rows of the table, skipping the first header row
                for row in table.find_all('tr')[1:]:
                    cells = row.find_all(['th', 'td'])
                    if cells:
                        # Collect the question and its corresponding ratings
                        row_data = {
                            'question': cells[0].text.strip(),  # First column is the question
                            **{headers[i]: cells[i+1].text.strip() for i in range(len(headers)) if i+1 < len(cells)}
                        }
                        table_data.append(row_data)
            
            # Add the data for this table to the results
            tables[table_title] = table_data
    
    # Collect relevant data
    rating_table = tables.get('Please respond to the following:', [])
    question_means = {}
    valid_question_indices = [1, 2, 3, 5, 6, 7, 8]

    for index, row in enumerate(rating_table, start=1):
        if index in valid_question_indices:
            question = row['question']
            mean_value = row.get('Mean', None)
            if mean_value:
                question_means[question] = mean_value

    print(question_means)

    rating_table = tables.get('The Instructor . . .', [])
    specific_instructor_question_means = {}
    specific_questions = [
        'Organized the course clearly.',
        'Challenged you to learn.',
        'Helped you gain significant learning from the course content.',
        'Motivated you to think independently.',
        'Worked to create an inclusive and welcoming learning environment.'
    ]

    for row in rating_table:
        question = row['question']
        if question in specific_questions:
            mean_value = row.get('Mean')
            if mean_value is not None:
                specific_instructor_question_means[question] = mean_value

    print(specific_instructor_question_means)

    return tables

# Extract class, instructors, and quarter information from header
def extract_header_info(driver):
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    
    # Find the header block
    header = soup.find('div', class_='header')
    
    if header:
        # Extract course and instructors
        course_info = header.find('h2').text if header.find('h2') else ""
        class_code = course_info.split(' ')[0] if course_info else ""  # Extract "CMSC 14100"
        instructors_info = course_info.split('Instructor(s): ')[-1] if 'Instructor(s): ' in course_info else ""
        instructors = [instructor.strip() for instructor in instructors_info.split(',')] if instructors_info else []
        
        # Find the project title element and extract its text
        project_title_element = header.find('dd')
        project_title = project_title_element.text.strip() if project_title_element else ""
        
        # Define possible quarter names
        quarters = ["Autumn", "Winter", "Spring", "Summer"]
        
        # Search for the quarter and year within the project title text
        quarter_info = next((q for q in quarters if q in project_title), "")
        
        # Append the year following the quarter if the quarter is found
        if quarter_info:
            year = project_title.split(quarter_info)[-1].strip()  # Extract the year
            quarter_info = f"{quarter_info} {year}"

        # Return extracted information as a dictionary
        return {
            'class_code': class_code,
            'instructors': instructors,
            'quarter': quarter_info
        }

    return {}


# Main function to control Selenium
def main():
    # Set up Chrome WebDriver
    chrome_options = Options()
    driver_service = Service("/opt/homebrew/bin/chromedriver")  # Use the specified path for ChromeDriver
    driver = webdriver.Chrome(service=driver_service, options=chrome_options)

    try:
        # Open the initial page to set domain for the cookies
        driver.get('https://uchicago.bluera.com/uchicago/')  # Open the base URL first

        # Load the cookies to bypass login
        cookies_file = 'cookies.pkl'  # Path to your cookies.pkl
        load_cookies(driver, cookies_file)

        # Refresh the page after adding cookies to ensure they are applied
        driver.refresh()

        # Feedback URL
        feedback_url = 'https://uchicago.bluera.com/uchicago/rpvf-eng.aspx?lang=eng&redi=1&SelectedIDforPrint=36bbc414a9f8093e8449347498c17bf192f23487b2a70e7f9034ec973d66b5f8a2ddb38d6a5194397ce937729a24f994&ReportType=2&regl=en-US'

        # Navigate to the feedback page
        driver.get(feedback_url)
        time.sleep(1)  # Ensure the page loads completely

        # Step 1: Extract the header information (class, instructors, quarter)
        header_info = extract_header_info(driver)
        print(f"Class Info: {header_info}")

        # Step 2: Extract the rating tables
        rating_tables = extract_rating_tables(driver)

    finally:
        # Close the browser
        driver.quit()

if __name__ == "__main__":
    main()
