from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import cProfile
import pstats
from io import StringIO

app = Flask(__name__)
CORS(app)

# Path to your course_feedback database
DB_PATH = '/home/benheim/courseFeedback/courseFeedBackExtensionProduction/course_feedback.db'

# Helper function to split course name into dept and course_id
def split_course_name(course_name):
    try:
        dept, course_id = course_name.strip().split()
        return dept.strip(), course_id.strip()
    except ValueError:
        # Return None if the format is unexpected
        return None, None

# Function to find the professor's ID based on their last name and department

def find_professor_ids(cursor, professors):
    # professors -> [(last_name, [ordered_departments])]

    professor_ids = {}
    parameters = []
    conditions = []
    department_order = {}  # To keep track of departments for each professor

    for last_name, departments in professors:
        if last_name in department_order:
            continue
        department_order[last_name] = departments
        placeholders = ','.join(['?'] * len(departments))
        conditions.append(f"(last_name = ? AND dept IN ({placeholders}))")
        parameters.extend([last_name] + departments)

    if not conditions:
        return professor_ids

    where_clause = " OR ".join(conditions)

    query = f"""
        SELECT id, last_name, dept
        FROM professors
        WHERE {where_clause}
    """

    cursor.execute(query, parameters)
    results = cursor.fetchall()

    # For each professor, find the first department match according to their department order
    for last_name, departments in department_order.items():
        for dept in departments:
            # Check if the professor exists in this department
            for row in results:
                prof_id, db_last_name, db_dept = row
                if db_last_name == last_name and db_dept == dept:
                    professor_ids[(last_name, dept)] = prof_id
                    break
            if (last_name, dept) in professor_ids:
                # Found the professor in this department, move to next professor
                break

    return professor_ids

# Function to calculate course rating based on course_id and dept
def calculate_course_rating(cursor, dept, course_id):
    # Columns for course rating
    # Query to get all the course feedback for the given course
    query = f"SELECT avg_course_rating FROM courses WHERE dept = ? AND course_id = ?"
    cursor.execute(query, (dept, course_id))
    results = cursor.fetchone()
    # If no results, return None
    if not results:
        return None
    return results[0]

def calculate_course_ratings(cursor, courses):
    conditions = []
    parameters = []
    for dept, course_id in courses:
        conditions.append("(dept = ? AND course_id = ?)")
        parameters.extend([dept, course_id])
    where_clause = " OR ".join(conditions)
    
    # Query to fetch all rows for the given courses
    query = f"""
        SELECT dept, course_id, avg_course_rating
        FROM courses
        WHERE {where_clause}
    """
    
    # Execute the query
    cursor.execute(query, parameters)
    results = cursor.fetchall()
    
    course_ratings = {}
    for row in results:
        dept = row[0]
        course_id = row[1]
        rating = row[2]
        
        # Create a key for the course
        course_key = (dept, course_id)
        course_ratings[course_key] = rating
    return course_ratings

# Function to calculate course hours based on time ranges
def calculate_course_hours(cursor, dept, course_id):
    # Columns for time spent
    hour_columns = [
        "less_five", "five_to_ten", "ten_to_fifteen", "fifteen_to_twenty",
        "twenty_to_twenty_five", "twenty_five_to_thirty", "more_thirty"
    ]
    # Weight multipliers for each time range
    hour_weights = [2.5, 7.5, 12.5, 17.5, 22.5, 27.5, 32.5]
    # Query to get the time distribution for the course
    query = f"SELECT {', '.join(hour_columns)} FROM courses WHERE dept = ? AND course_id = ?"
    cursor.execute(query, (dept, course_id))
    results = cursor.fetchall()
    if not results:
        return None
    total_hours = 0
    total_responses = 0
    for result in results:
        hours_sum = 0
        responses_sum = 0
        for i, count in enumerate(result):
            if count is not None:
                hours_sum += count * hour_weights[i]
                responses_sum += count
        total_hours += hours_sum
        total_responses += responses_sum
    if total_responses == 0:
        return None
    average_hours = total_hours / total_responses
    return average_hours

def calculate_courses_hours(cursor, courses):
    conditions = []
    parameters = []
    for dept, course_id in courses:
        conditions.append("(dept = ? AND course_id = ?)")
        parameters.extend([dept, course_id])
    where_clause = " OR ".join(conditions)
    
    # Query to fetch all rows for the given courses
    query = f"""
        SELECT dept, course_id, avg_course_hours
        FROM courses
        WHERE {where_clause}
    """
    
    # Execute the query
    cursor.execute(query, parameters)
    results = cursor.fetchall()
    
    course_hours = {}
    for row in results:
        dept = row[0]
        course_id = row[1]
        rating = row[2]
        
        # Create a key for the course
        course_key = (dept, course_id)
        course_hours[course_key] = rating
    return course_hours

def calculate_professors_ratings(cursor, professor_ids):
    conditions = []
    parameters = []
    for id in professor_ids.values():
        conditions.append("(id = ?)")
        parameters.extend([id])
    where_clause = " OR ".join(conditions)
    
    # Query to fetch all rows for the given courses
    query = f"""
        SELECT id, avg_professor_rating
        FROM professors
        WHERE {where_clause}
    """
    # Execute the query
    cursor.execute(query, parameters)
    results = cursor.fetchall()
    
    professor_ratings = {}
    for row in results:
        id = row[0]
        rating = row[1]

        # Create a key for the course
        professor_key = (id)
        professor_ratings[professor_key] = rating
    return professor_ratings


def calculate_professor_course_ratings(cursor, professor_course_ids):
    """
    Calculate professor-course ratings using a singular query.

    Args:
        cursor (sqlite3.Cursor): The database cursor.
        professor_course_ids (list): List of tuples, where each tuple contains (professor_id, dept, course_id).

    Returns:
        dict: A dictionary with keys as (professor_id, dept, course_id) and values as avg_prof_course_rating.
    """
    conditions = []
    parameters = []
    
    # Build WHERE clause for the query
    for professor_id, dept, course_id in professor_course_ids:
        conditions.append("(cp.professor_id = ? AND c.dept = ? AND c.course_id = ?)")
        parameters.extend([professor_id, dept, course_id])
    
    if not conditions:
        return {}
    
    where_clause = " OR ".join(conditions)
    
    # Query to fetch all avg_prof_course_rating for the given professor-course combinations
    query = f"""
        SELECT cp.professor_id, c.dept, c.course_id, cp.avg_prof_course_rating
        FROM courses_professors cp
        JOIN courses c ON cp.course_id = c.id
        WHERE {where_clause}
    """
    
    # Execute the query
    cursor.execute(query, parameters)
    results = cursor.fetchall()
    
    # Build the result dictionary
    professor_course_ratings = {}
    for row in results:
        professor_id = row[0]
        dept = row[1]
        course_id = row[2]
        avg_rating = row[3]
        
        professor_course_ratings[(professor_id, dept, course_id)] = avg_rating
    
    return professor_course_ratings

# Function to calculate professor course hours for a specific professor teaching a specific course
def calculate_professor_courses_hours(cursor, professor_course_ids):
    """
    Calculate professor-course hours using a singular query.

    Args:
        cursor (sqlite3.Cursor): The database cursor.
        professor_course_ids (list): List of tuples, where each tuple contains (professor_id, dept, course_id).

    Returns:
        dict: A dictionary with keys as (professor_id, dept, course_id) and values as avg_prof_course_hours.
    """
    conditions = []
    parameters = []
    
    # Build WHERE clause for the query
    for professor_id, dept, course_id in professor_course_ids:
        conditions.append("(cp.professor_id = ? AND c.dept = ? AND c.course_id = ?)")
        parameters.extend([professor_id, dept, course_id])
    
    if not conditions:
        return {}
    
    where_clause = " OR ".join(conditions)
    
    # Query to fetch all avg_prof_course_hours for the given professor-course combinations
    query = f"""
        SELECT cp.professor_id, c.dept, c.course_id, cp.avg_prof_course_hours
        FROM courses_professors cp
        JOIN courses c ON cp.course_id = c.id
        WHERE {where_clause}
    """
    
    # Execute the query
    cursor.execute(query, parameters)
    results = cursor.fetchall()
    
    # Build the result dictionary
    professor_course_hours = {}
    for row in results:
        professor_id = row[0]
        dept = row[1]
        course_id = row[2]
        avg_hours = row[3]
        
        professor_course_hours[(professor_id, dept, course_id)] = avg_hours
    
    return professor_course_hours

def fetch_course_urls(cursor, courses):
    conditions = []
    parameters = []
    for dept, course_id in courses:
        conditions.append("(dept = ? AND course_id = ?)")
        parameters.extend([dept, course_id])
    where_clause = " OR ".join(conditions)
    query = f"""
        SELECT dept, course_id, url
        FROM courses
        WHERE {where_clause}
    """
    cursor.execute(query, parameters)
    results = cursor.fetchall()
    course_urls = {}
    for row in results:
        dept, course_id, url = row
        key = (dept, course_id)
        if key in course_urls:
            course_urls[key].append(url)
        else:
            course_urls[key] = [url]
    return course_urls

@app.route('/')
def home():
    # Simple home route to check if the app is running
    return "The Flask app is working!"

# Route to handle course data and return the course rating, professor rating, course hours, and professor course hours
@app.route('/get-course-feedback', methods=['POST'])
def get_course_feedback():
    profiler = cProfile.Profile()
    profiler.enable()
    data = request.json
    feedback_data = []

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        course_keys = set()
        professor_keys = []
        professor_course_ids = set()  # Stores professor-course mappings

        # Process each course to collect course_keys and professor_keys
        for course in data:
            course_name = course['courseId']
            other_listings = course['otherListings']
            dept, course_id = split_course_name(course_name)
            course_keys.add((dept, course_id))

            # Collect alternative listings
            for listing in other_listings:
                alt_dept, alt_course_id = split_course_name(listing)
                if alt_dept and alt_course_id:
                    course_keys.add((alt_dept, alt_course_id))

            professor_last_name = course['instructor']
            professor_names = [name.strip() for name in professor_last_name.split(',')] if ',' in professor_last_name else [professor_last_name.strip()]

            # Collect professor_keys with department order
            departments_order = [dept] + [split_course_name(listing)[0] for listing in other_listings if split_course_name(listing)[0]]
            for name in professor_names:
                professor_keys.append((name, departments_order))

        # Perform bulk queries for courses and professors
        course_ratings = calculate_course_ratings(cursor, list(course_keys))
        courses_hours = calculate_courses_hours(cursor, list(course_keys))
        course_urls = fetch_course_urls(cursor, list(course_keys))
        print(f"here are course urls: {course_urls}")
        professor_ids = find_professor_ids(cursor, professor_keys)
        professor_ratings = calculate_professors_ratings(cursor, professor_ids)

        # Now process each course individually to collect professor_course_ids and prepare data
        for course in data:
            course_name = course['courseId']
            other_listings = course['otherListings']
            professor_last_name = course['instructor']

            dept, course_id = split_course_name(course_name)
            if course_id:
                course_id = int(course_id)
            if not dept or not course_id:
                continue

            # Initialize actual_dept and actual_course_id
            actual_dept, actual_course_id = dept, course_id

            # Fetch course rating and hours
            course_rating = course_ratings.get((dept, course_id))
            course_hours = courses_hours.get((dept, course_id))
            # Handle alternative listings if no rating found
            if course_rating is None:
                for listing in other_listings:
                    alt_dept, alt_course_id = split_course_name(listing)
                    if alt_course_id:
                        alt_course_id = int(alt_course_id)
                    if alt_dept and alt_course_id:
                        course_rating = course_ratings.get((alt_dept, alt_course_id))
                        course_hours = courses_hours.get((alt_dept, alt_course_id))
                        if course_rating is not None:
                            course_name = listing
                            actual_dept, actual_course_id = alt_dept, alt_course_id
                            break

            # Collect departments in order
            departments = [dept] + [split_course_name(listing)[0] for listing in other_listings if split_course_name(listing)[0]]

            # Process professors for this course and all its listings
            professor_names = [name.strip() for name in professor_last_name.split(',')] if ',' in professor_last_name else [professor_last_name.strip()]

            for name in professor_names:
                # Find the professor ID based on department order
                professor_id = None
                for dept_option in departments:
                    professor_id = professor_ids.get((name, dept_option))
                    if professor_id:
                        break

                if professor_id:
                    # Collect professor_course_id for the main course
                    professor_course_ids.add((professor_id, actual_dept, actual_course_id))

                    # Collect professor_course_id for each alternative listing
                    for listing in other_listings:
                        alt_dept, alt_course_id = split_course_name(listing)
                        if alt_dept and alt_course_id:
                            professor_course_ids.add((professor_id, alt_dept, int(alt_course_id)))

        # Now perform bulk queries for professor-course data
        professor_course_ids_list = list(professor_course_ids)
        professor_course_hours = calculate_professor_courses_hours(cursor, professor_course_ids_list)
        professor_course_ratings = calculate_professor_course_ratings(cursor, professor_course_ids_list)

        # Now process each course again to compile feedback_data
        for course in data:
            course_name = course['courseId']
            other_listings = course['otherListings']
            professor_last_name = course['instructor']

            dept, course_id = split_course_name(course_name)
            if course_id:
                course_id = int(course_id)
            if not dept or not course_id:
                continue

            # Initialize actual_dept and actual_course_id
            actual_dept, actual_course_id = dept, course_id

            # Fetch course rating and hours
            course_rating = course_ratings.get((dept, course_id))
            course_hours = courses_hours.get((dept, course_id))

            # Handle alternative listings if no rating found
            if course_rating is None:
                for listing in other_listings:
                    alt_dept, alt_course_id = split_course_name(listing)
                    if alt_course_id:
                        alt_course_id = int(alt_course_id)
                    if alt_dept and alt_course_id:
                        course_rating = course_ratings.get((alt_dept, alt_course_id))
                        course_hours = courses_hours.get((alt_dept, alt_course_id))
                        if course_rating is not None:
                            course_name = listing
                            actual_dept, actual_course_id = alt_dept, alt_course_id
                            break

            # Collect departments in order
            departments = [dept]
            for listing in other_listings:
                alt_dept, _ = split_course_name(listing)
                if alt_dept:
                    departments.append(alt_dept)

            # Process professors for this course
            professor_names = [name.strip() for name in professor_last_name.split(',')] if ',' in professor_last_name else [professor_last_name.strip()]

            single_course_professor_ratings = []
            single_course_professor_course_ratings = []
            single_course_professor_course_hours = []

            for name in professor_names:
                # Find the professor ID based on department order
                professor_id = None
                for dept_option in departments:
                    professor_id = professor_ids.get((name, dept_option))
                    if professor_id:
                        break
                """
                if professor_id:
                    # Use actual_dept and actual_course_id to look up professor-course data
                    prof_course_key = (professor_id, actual_dept, actual_course_id)
                    single_course_professor_course_ratings.append(
                        professor_course_ratings.get(prof_course_key)
                    )
                    single_course_professor_course_hours.append(
                        professor_course_hours.get(prof_course_key)
                    )
                    single_course_professor_ratings.append(professor_ratings.get(professor_id))
                """


                if professor_id:

                    single_course_professor_ratings.append(professor_ratings.get(professor_id))
                    
                    # First attempt: Use actual_dept and actual_course_id
                    prof_course_key = (professor_id, actual_dept, actual_course_id)
                    prof_course_rating = professor_course_ratings.get(prof_course_key)
                    prof_course_hours = professor_course_hours.get(prof_course_key)

                    # If no rating found, try alternative department-course combinations
                    if prof_course_rating is None or prof_course_hours is None:

                        for listing in other_listings:
                            alt_dept, alt_course_id = split_course_name(listing)
                            if alt_dept and alt_course_id:
                                alt_course_id = int(alt_course_id)
                                alt_prof_course_key = (professor_id, alt_dept, alt_course_id)
        
                                alt_prof_course_rating = professor_course_ratings.get(alt_prof_course_key)
                                alt_prof_course_hours = professor_course_hours.get(alt_prof_course_key)

                                # Use the first valid rating we find
                                if prof_course_rating is None and alt_prof_course_rating is not None:
                                    prof_course_rating = alt_prof_course_rating

                                if prof_course_hours is None and alt_prof_course_hours is not None:
                                    prof_course_hours = alt_prof_course_hours

                                # Stop searching if both values are found
                                if prof_course_rating is not None and prof_course_hours is not None:
                                    break

                    # Append final values
                    single_course_professor_course_ratings.append(prof_course_rating)
                    single_course_professor_course_hours.append(prof_course_hours)

            # Calculate averages
            valid_professor_ratings = list(filter(None, single_course_professor_ratings))
            avg_professor_rating = (
                sum(valid_professor_ratings) / len(valid_professor_ratings)
                if valid_professor_ratings else None
            )
            valid_professor_course_ratings = list(filter(None, single_course_professor_course_ratings))
            avg_professor_course_rating = (
                sum(valid_professor_course_ratings) / len(valid_professor_course_ratings)
                if valid_professor_course_ratings else None
            )
            valid_professor_course_hours = list(filter(None, single_course_professor_course_hours))
            avg_professor_course_hours = (
                sum(valid_professor_course_hours) / len(valid_professor_course_hours)
                if valid_professor_course_hours else None
            )
            urls = course_urls.get((actual_dept, actual_course_id), [])

            # Append the results to the feedback_data list
            feedback_data.append({
                'courseId': course_name,
                'course_rating': course_rating,
                'professor_rating': avg_professor_rating,
                'professor_course_rating': avg_professor_course_rating,
                'course_hours': course_hours,
                'professor_course_hours': avg_professor_course_hours,
                'course_urls': urls
            })
        print(feedback_data)
        # Return the feedback data as JSON
        return jsonify(feedback_data), 200

    finally:
        # Close the database connection after all processing is complete
        conn.close()
        profiler.disable()
        s = StringIO()
        ps = pstats.Stats(profiler, stream=s).sort_stats('cumtime')
        ps.print_stats()

if __name__ == '__main__':
    app.run(debug=True)