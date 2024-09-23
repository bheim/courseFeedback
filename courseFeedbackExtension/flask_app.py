from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3

app = Flask(__name__)
CORS(app)



# Path to your course_feedback database
DB_PATH = 'course_feedback.db'

PYTHONUNBUFFERED=0

# Helper function to split course name into dept and course_id
def split_course_name(course_name):
    try:
        dept, course_id = course_name.split()
        return dept, course_id
    except ValueError:
        return None, None  # In case the format is unexpected

# Function to query the professor's ID based on their name and department
def find_professor_id(last_name, possible_depts):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Try to find the professor using their last name and department
    for dept in possible_depts:
        cursor.execute("SELECT id FROM professors WHERE last_name=? AND dept=?", (last_name, dept))
        result = cursor.fetchone()
        if result:
            conn.close()
            return result[0]  # Return professor ID if found

    conn.close()
    return None  # Return None if no professor was found

# Function to calculate course rating based on course_id and dept
def calculate_course_rating(dept, course_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Columns for course rating
    course_rating_columns = [
        "challenge_intellect", "purpose", "standards", "feedback", "fairness",
        "respect", "excellence"
    ]

    # Query to get all the course feedback for the given course
    query = f"SELECT {', '.join(course_rating_columns)} FROM courses WHERE dept=? AND course_id=?"
    cursor.execute(query, (dept, course_id))
    results = cursor.fetchall()

    # Calculate the average of the columns
    total_ratings = {col: 0 for col in course_rating_columns}
    valid_result_count = 0

    for result in results:
        valid_course = False
        for i, rating in enumerate(result):
            if rating is not None:
                total_ratings[course_rating_columns[i]] += rating
                valid_course = True
        if valid_course:
            valid_result_count += 1

    course_rating = None
    if valid_result_count > 0:
        course_rating = sum(total_ratings[col] for col in course_rating_columns) / (valid_result_count * len(course_rating_columns))

    conn.close()
    return course_rating

# Function to calculate professor_rating based on all the courses they taught
def calculate_professor_rating(professor_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Columns for professor rating
    rating_columns = [
        "organization", "challenge", "available", "inclusive", "significant"
    ]

    # Get all course IDs taught by the professor
    cursor.execute("SELECT course_id FROM courses_professors WHERE professor_id=?", (professor_id,))
    course_ids = cursor.fetchall()

    total_ratings = {column: 0 for column in rating_columns}
    valid_course_count = 0

    # Fetch the rating values for each course and calculate the sum
    for course_id in course_ids:
        course_id = course_id[0]  # Extract course_id from the tuple
        cursor.execute(f"SELECT {', '.join(rating_columns)} FROM courses WHERE id=?", (course_id,))
        ratings = cursor.fetchone()

        if ratings:
            valid_course = False
            for i, rating in enumerate(ratings):
                if rating is not None:
                    total_ratings[rating_columns[i]] += rating
                    valid_course = True

            if valid_course:
                valid_course_count += 1

    professor_rating = None
    if valid_course_count > 0:
        professor_rating = sum(total_ratings[column] for column in rating_columns) / (valid_course_count * len(rating_columns))

    conn.close()
    return professor_rating

# Function to calculate professor_course_rating for a specific professor teaching a specific course
def calculate_professor_course_rating(professor_id, dept, course_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Columns for professor_course_rating
    prof_course_rating_columns = [
        "challenge_intellect", "purpose", "standards", "feedback", "fairness",
        "respect", "excellence", "organization", "challenge", "available",
        "inclusive", "significant"
    ]

    # Query to find all courses this professor taught with the given course_id
    cursor.execute("""
        SELECT {columns}
        FROM courses c
        JOIN courses_professors cp ON c.id = cp.course_id
        WHERE cp.professor_id = ? AND c.dept = ? AND c.course_id = ?
    """.format(columns=', '.join(prof_course_rating_columns)), (professor_id, dept, course_id))
    results = cursor.fetchall()

    # Calculate the average of the columns
    total_ratings = {col: 0 for col in prof_course_rating_columns}
    valid_result_count = 0

    for result in results:
        valid_course = False
        for i, rating in enumerate(result):
            if rating is not None:
                total_ratings[prof_course_rating_columns[i]] += rating
                valid_course = True
        if valid_course:
            valid_result_count += 1

    professor_course_rating = None
    if valid_result_count > 0:
        professor_course_rating = sum(total_ratings[col] for col in prof_course_rating_columns) / (valid_result_count * len(prof_course_rating_columns))

    conn.close()
    return professor_course_rating

# Function to calculate course hours based on time ranges
def calculate_course_hours(dept, course_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Columns for time spent
    hour_columns = [
        "less_five", "five_to_ten", "ten_to_fifteen", "fifteen_to_twenty",
        "twenty_to_twenty_five", "twenty_five_to_thirty", "more_thirty"
    ]

    # Weight multipliers for each time range
    hour_weights = [2.5, 7.5, 12.5, 17.5, 22.5, 27.5, 32.5]

    # Query to get the time distribution for the course
    query = f"SELECT {', '.join(hour_columns)} FROM courses WHERE dept=? AND course_id=?"
    cursor.execute(query, (dept, course_id))
    results = cursor.fetchall()

    total_hours = 0
    total_responses = 0

    # Calculate the weighted hours for each response
    for result in results:
        hours_sum = 0
        responses_sum = 0
        for i, count in enumerate(result):
            if count is not None:
                hours_sum += count * hour_weights[i]
                responses_sum += count

        total_hours += hours_sum
        total_responses += responses_sum

    course_hours = None
    if total_responses > 0:
        course_hours = total_hours / total_responses

    conn.close()
    return course_hours

# Function to calculate professor course hours for a specific professor teaching a specific course
def calculate_professor_course_hours(professor_id, dept, course_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Columns for time spent
    hour_columns = [
        "less_five", "five_to_ten", "ten_to_fifteen", "fifteen_to_twenty",
        "twenty_to_twenty_five", "twenty_five_to_thirty", "more_thirty"
    ]

    # Weight multipliers for each time range
    hour_weights = [2.5, 7.5, 12.5, 17.5, 22.5, 27.5, 32.5]

    # Query to get the time distribution for the course taught by the professor
    cursor.execute("""
        SELECT {columns}
        FROM courses c
        JOIN courses_professors cp ON c.id = cp.course_id
        WHERE cp.professor_id = ? AND c.dept = ? AND c.course_id = ?
    """.format(columns=', '.join(hour_columns)), (professor_id, dept, course_id))
    results = cursor.fetchall()

    total_hours = 0
    total_responses = 0

    # Calculate the weighted hours for each response
    for result in results:
        hours_sum = 0
        responses_sum = 0
        for i, count in enumerate(result):
            if count is not None:
                hours_sum += count * hour_weights[i]
                responses_sum += count

        total_hours += hours_sum
        total_responses += responses_sum

    professor_course_hours = None
    if total_responses > 0:
        professor_course_hours = total_hours / total_responses

    conn.close()
    return professor_course_hours


# Route to handle course data and return the course rating, professor rating, course hours, and professor course hours
@app.route('/get-course-feedback', methods=['POST'])
def get_course_feedback():
    data = request.json
    feedback_data = []

    # Loop through the courses sent from the frontend
    for course in data:
        course_name = course['courseId']  # e.g., "CMSC 14100"
        other_listings = course['otherListings']  # List of alternative course names
        professor_last_name = course['instructor']  # Instructor's last name

        # Split the main course name into dept and course_id
        

        dept, course_id = split_course_name(course_name)

        old_dept = None
        if dept and course_id:
            # Calculate course_rating
            course_rating = calculate_course_rating(dept, course_id)

            if not course_rating:
                for course_info in other_listings:
                    current_dept, current_id = split_course_name(course_info)
                    course_rating = calculate_course_rating(current_dept, current_id)
                    if(course_rating):
                        course_name = course_info
                        old_dept = dept
                        dept = current_dept
                        course_id = current_id
                        break

            # Calculate course_hours
            course_hours = calculate_course_hours(dept, course_id)

            # Find the list of possible departments (from main and alternative courses)
            possible_depts = [old_dept if old_dept is not None else dept] + [split_course_name(alt_course)[0] for alt_course in other_listings]

            # Find professor ID based on last name and departments
            professor_id = find_professor_id(professor_last_name, possible_depts)

            if professor_id:
                # Calculate professor_rating, professor_course_rating, and professor_course_hours
                professor_rating = calculate_professor_rating(professor_id)
                professor_course_rating = calculate_professor_course_rating(professor_id, dept, course_id)
                professor_course_hours = calculate_professor_course_hours(professor_id, dept, course_id)
            else:
                professor_rating = None
                professor_course_rating = None
                professor_course_hours = None

            # Append the results to the feedback_data list
            feedback_data.append({
                'courseId': course_name,
                'course_rating': course_rating,
                'professor_rating': professor_rating,
                'professor_course_rating': professor_course_rating,
                'course_hours': course_hours,
                'professor_course_hours': professor_course_hours
            })

    # Return the feedback data as JSON
    return jsonify(feedback_data), 200

if __name__ == '__main__':
    app.run(debug=True)
