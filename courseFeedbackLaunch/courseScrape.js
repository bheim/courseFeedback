let debounceTimeout;

// Create a MutationObserver to watch for changes in the DOM
const observerCallback = (mutationsList, observer) => {
    clearTimeout(debounceTimeout);

    debounceTimeout = setTimeout(() => {
        console.log("Debounced function execution");
        const scrapedCourses = scrapeCourseData();
        console.log(scrapedCourses);

        // Send course information to the backend only if valid data exists
        if (scrapedCourses.length > 0) {
            fetch('https://benheim.pythonanywhere.com/get-course-feedback', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(scrapedCourses),  // Send the scraped courses data
            })
            .then(response => response.json())
            .then(data => {
                console.log("Response from backend:", data);
                addFeedbackWidgets(data);  // Call function to add the feedback widgets
            })
            .catch(error => console.error('Error:', error));
        }
    }, 1000); // Adjust the delay (in milliseconds) to avoid frequent re-runs
};

const observer = new MutationObserver(observerCallback);
observer.observe(document.body, { childList: true, subtree: true });

// Scrape course data function
function scrapeCourseData() {
    const courses = [];
    
    // Select all course rows
    const courseRows = document.querySelectorAll('tbody.ps_grid-body tr.ps_grid-row');

    courseRows.forEach((row, index) => {
        // Dynamic selector for course title
        let courseTitleSelector = `#win0divUC_CLSRCH_WRK_UC_CLASS_TITLE\\$${index} .ps_box-value`;
        let courseTitleElement = row.querySelector(courseTitleSelector);
        let courseTitle = courseTitleElement?.textContent.trim() || '';

        // Skip this row if no course title is found (filters out non-course rows)
        if (!courseTitle) {
            return;
        }

        // Dynamic selector for course ID
        let courseIdSelector = `#win0divUC_RSLT_NAV_WRK_HTMLAREA\\$${index}`;
        let courseIdElement = row.querySelector(courseIdSelector);
        let courseIdText = courseIdElement?.textContent.trim() || '';
        let courseId = courseIdText.split('/')[0];  // Extract course ID from the text

        // Dynamic selector for instructor name
        let instructorSelector = `#win0divUC_CLSRCH_WRK_SSR_INSTR_LONG\\$${index} .ps_box-value`;
        let instructorElement = row.querySelector(instructorSelector);
        let instructor = instructorElement?.textContent.trim() || '';
        //instructor = instructor.split(',')[0].trim();

        // Dynamic selector for other course listings
        let otherListingsSelector = `#win0divUC_CLSRCH_WRK2_DESCRLONG_NOTES\\$${index} .ps_box-value`;
        let otherListingsElement = row.querySelector(otherListingsSelector);
        let otherListings = otherListingsElement?.textContent.trim() || '';

        // Add the extracted data to the courses array
        courses.push({
            courseTitle,
            courseId,
            instructor,
            otherListings: otherListings.split(',')
        });
    });

    return courses;
}

// Function to add feedback widgets with real data from the backend
function addFeedbackWidgets(feedbackData) {
    const courseRows = document.querySelectorAll('tbody.ps_grid-body tr.ps_grid-row');

    // Loop through each course row and add the feedback widget
    courseRows.forEach((row, index) => {
        // Check if a feedback widget has already been added to avoid duplication
        if (row.querySelector('.feedback-widget')) {
            return;  // Skip if widget already exists
        }
    
        const feedback = feedbackData[index];  // Get the feedback for this course
        const widget = document.createElement('div');
        widget.classList.add('feedback-widget');
    
        // Set the inner HTML for the widget based on the feedback data
        if (feedback) {
            const professorRating = feedback.professor_rating !== null ? feedback.professor_rating.toFixed(2) : 'No data since 2021';
            const courseRating = feedback.course_rating !== null ? feedback.course_rating.toFixed(2) : 'No data since 2021';
            const professorCourseRating = feedback.professor_course_rating !== null ? feedback.professor_course_rating.toFixed(2) : 'No data since 2021';
            const courseHours = feedback.course_hours !== null ? feedback.course_hours.toFixed(2) : 'No data since 2021';
            const professorCourseHours = feedback.professor_course_hours !== null ? feedback.professor_course_hours.toFixed(2) : 'No data since 2021';
    
            widget.innerHTML = `
                <strong>Professor Rating:</strong> ${professorRating}<br>
                <strong>Course Rating:</strong> ${courseRating}<br>
                <strong>Prof. X Course Rating:</strong> ${professorCourseRating}<br>
                <strong>Avg Hours:</strong> ${courseHours}<br>
                <strong>Prof. X Course Hours:</strong> ${professorCourseHours}
            `;
             // Style the widge
            widget.style.border = '1px solid #ccc';
            widget.style.padding = '10px';
            widget.style.marginLeft = '10px';
            widget.style.backgroundColor = '#f9f9f9';
            widget.style.fontSize = '12px';
            widget.style.width = '200px';
            widget.style.textAlign = 'left';

            // Append the widget to the course row
            row.appendChild(widget);
        }
       
    });
}
