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
def find_professor_id(cursor, last_name, dept):
    # Try to find the professor in the given department
    cursor.execute("SELECT id FROM professors WHERE last_name = ? AND dept = ?", (last_name, dept))
    result = cursor.fetchone()
    if result:
        return result[0]  # Return the professor's ID
    else:
        # If not found, try to find the professor in any department
        cursor.execute("SELECT id FROM professors WHERE last_name = ?", (last_name,))
        result = cursor.fetchone()
        if result:
            return result[0]
    return None

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

# Function to calculate professor_rating based on all the courses they taught
def calculate_professor_rating(cursor, professor_id):
    # Columns for professor rating
    rating_columns = [
        "organization", "challenge", "available", "inclusive", "significant"
    ]
    # Get all course IDs taught by the professor
    cursor.execute("SELECT course_id FROM courses_professors WHERE professor_id = ?", (professor_id,))
    course_ids = cursor.fetchall()
    if not course_ids:
        return None
    # Fetch the rating values for each course and calculate the sum
    total_ratings = {col: 0 for col in rating_columns}
    valid_course_count = 0
    for (course_id,) in course_ids:
        cursor.execute(f"SELECT {', '.join(rating_columns)} FROM courses WHERE id = ?", (course_id,))
        ratings = cursor.fetchone()
        if ratings:
            valid_ratings = [rating for rating in ratings if rating is not None]
            if valid_ratings:
                for i, rating in enumerate(ratings):
                    if rating is not None:
                        total_ratings[rating_columns[i]] += rating
                valid_course_count += 1
    if valid_course_count == 0:
        return None
    average_rating = sum(total_ratings[col] for col in rating_columns) / (valid_course_count * len(rating_columns))
    return average_rating



# Function to calculate professor_course_rating for a specific professor teaching a specific course
def calculate_professor_course_rating(cursor, professor_id, dept, course_id):
    # Columns for professor_course_rating
    prof_course_rating_columns = [
        "challenge_intellect", "purpose", "standards", "feedback", "fairness",
        "respect", "excellence", "organization", "challenge", "available",
        "inclusive", "significant"
    ]
    # Query to find courses this professor taught with the given dept and course_id
    query = f"""
        SELECT {', '.join(prof_course_rating_columns)}
        FROM courses c
        JOIN courses_professors cp ON c.id = cp.course_id
        WHERE cp.professor_id = ? AND c.dept = ? AND c.course_id = ?
    """
    cursor.execute(query, (professor_id, dept, course_id))
    results = cursor.fetchall()
    if not results:
        return None
    total_ratings = {col: 0 for col in prof_course_rating_columns}
    valid_result_count = 0
    for result in results:
        valid_ratings = [rating for rating in result if rating is not None]
        if valid_ratings:
            for i, rating in enumerate(result):
                if rating is not None:
                    total_ratings[prof_course_rating_columns[i]] += rating
            valid_result_count += 1
    if valid_result_count == 0:
        return None
    average_rating = sum(total_ratings[col] for col in prof_course_rating_columns) / (valid_result_count * len(prof_course_rating_columns))
    return average_rating

# Function to calculate professor course hours for a specific professor teaching a specific course
def calculate_professor_course_hours(cursor, professor_id, dept, course_id):
    # Columns for time spent
    hour_columns = [
        "less_five", "five_to_ten", "ten_to_fifteen", "fifteen_to_twenty",
        "twenty_to_twenty_five", "twenty_five_to_thirty", "more_thirty"
    ]
    # Weight multipliers for each time range
    hour_weights = [2.5, 7.5, 12.5, 17.5, 22.5, 27.5, 32.5]
    # Query to get the time distribution for the course taught by the professor
    query = f"""
        SELECT {', '.join(hour_columns)}
        FROM courses c
        JOIN courses_professors cp ON c.id = cp.course_id
        WHERE cp.professor_id = ? AND c.dept = ? AND c.course_id = ?
    """
    cursor.execute(query, (professor_id, dept, course_id))
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
        course_keys = []
        for course in data:
            course_name = course['courseId']
            dept, course_id = split_course_name(course_name)
            course_keys.append((dept, course_id))

        course_ratings = calculate_course_ratings(cursor, course_keys)
        courses_hours = calculate_courses_hours(cursor, course_keys)

        # Process each course individually
        for course in data:
            course_name = course['courseId']
            other_listings = course['otherListings']
            professor_last_name = course['instructor']

            # Try to split the main course name
            dept, course_id = split_course_name(course_name)
            if not dept or not course_id:
                # If unable to split, skip this course
                continue

            # First, try to calculate course_rating with the main course name
            course_rating = course_ratings.get((dept, int(course_id)), None)
            course_hours = courses_hours.get((dept, int(course_id)), None)

            # If course_rating is None, try with alternative listings (we assume course_hours would also be None and address that as well)
            if course_rating is None:
                found = False
                for listing in other_listings:
                    alt_dept, alt_course_id = split_course_name(listing)
                    if alt_dept and alt_course_id:
                        course_rating = calculate_course_rating(cursor, alt_dept, alt_course_id)
                        course_hours = calculate_course_hours(cursor, alt_dept, alt_course_id)
                        if course_rating is not None:
                            # Use this listing instead
                            course_name = listing
                            dept, course_id = alt_dept, alt_course_id
                            found = True
                            break
                if not found:
                    # If no rating found, set to None
                    course_rating = None
                    course_hours = None


            # Now, find professor IDs
            professor_ids = []
            if ',' in professor_last_name:
                # Multiple professors
                professor_names = [name.strip() for name in professor_last_name.split(',')]
            else:
                professor_names = [professor_last_name.strip()]

            for name in professor_names:
                professor_id = find_professor_id(cursor, name, dept)
                if professor_id:
                    professor_ids.append(professor_id)

            # Calculate professor ratings
            professor_ratings = []
            professor_course_ratings = []
            professor_course_hours_list = []

            for professor_id in professor_ids:
                professor_rating = calculate_professor_rating(cursor, professor_id)
                if professor_rating is not None:
                    professor_ratings.append(professor_rating)

                professor_course_rating = calculate_professor_course_rating(cursor, professor_id, dept, course_id)
                if professor_course_rating is not None:
                    professor_course_ratings.append(professor_course_rating)

                professor_course_hours = calculate_professor_course_hours(cursor, professor_id, dept, course_id)
                if professor_course_hours is not None:
                    professor_course_hours_list.append(professor_course_hours)

            # Calculate averages
            if professor_ratings:
                avg_professor_rating = sum(professor_ratings) / len(professor_ratings)
            else:
                avg_professor_rating = None

            if professor_course_ratings:
                avg_professor_course_rating = sum(professor_course_ratings) / len(professor_course_ratings)
            else:
                avg_professor_course_rating = None

            if professor_course_hours_list:
                avg_professor_course_hours = sum(professor_course_hours_list) / len(professor_course_hours_list)
            else:
                avg_professor_course_hours = None

            # Append the results to the feedback_data list
            feedback_data.append({
                'courseId': course_name,
                'course_rating': course_rating,
                'professor_rating': avg_professor_rating,
                'professor_course_rating': avg_professor_course_rating,
                'course_hours': course_hours,
                'professor_course_hours': avg_professor_course_hours
            })

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