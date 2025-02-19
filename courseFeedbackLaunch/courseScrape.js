let debounceTimeout;

// Create a MutationObserver to watch for changes in the DOM
const observerCallback = (mutationsList, observer) => {
    clearTimeout(debounceTimeout);

    debounceTimeout = setTimeout(() => {
        //console.log("Debounced function execution");
        const scrapedCourses = scrapeCourseData();
        //console.log(scrapedCourses);

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
                //console.log("Response from backend:", data);
                addFeedbackWidgets(data, scrapedCourses);  // Call function to add the feedback widgets
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

// Add this helper function
function getExtensionUrl(path) {
    return chrome.runtime.getURL(path);
}

// Replace the createExternalLinkIcon function with this simpler version
function createExternalLinkIcon() {
    const img = document.createElement('img');
    img.src = getExtensionUrl('/external-link.svg');
    img.width = 12;
    img.height = 12;
    return img;
}

// Add this helper function at the top with other helpers
function isCoursesearchSite() {
    return window.location.hostname.includes('coursesearch92');
}

// Modify the addFeedbackWidgets function
function addFeedbackWidgets(feedbackData, courseData) {
    // Change selector based on site
    const rows = document.querySelectorAll('tbody.ps_grid-body tr.ps_grid-row');
    
    rows.forEach((row, index) => {
        // Determine where to insert the widget
        const container = !isCoursesearchSite() 
            ? row.querySelector('td.ps_grid-cell')  // ais92psprd site
            : row;  // coursesearch92 site

        if (!container || container.querySelector('.feedback-widget')) {
            return;
        }

        // Only style the cell for NOT coursesearch92 site
        if (!isCoursesearchSite()) {
            container.style.height = 'fit-content';
            container.style.display = 'flex';
            container.style.alignItems = 'center';
            container.style.justifyContent = 'space-between';
        }

        const feedback = feedbackData[index];
        const course = courseData[index];
       
        if (feedback) {
            const widget = document.createElement('div');
            widget.classList.add('feedback-widget');
            
            const instructor = course.instructor || 'X';
            const courseCode = course.courseId || 'Course';
    
            const professorRating = feedback.professor_rating !== null ? `${feedback.professor_rating.toFixed(2)}/5` : 'Not Found';
            const courseRating = feedback.course_rating !== null ? `${feedback.course_rating.toFixed(2)}/5` : 'Not Found';
            const professorCourseRating = feedback.professor_course_rating !== null ? `${feedback.professor_course_rating.toFixed(2)}/5` : 'Not Found';
            const courseHours = feedback.course_hours !== null ? feedback.course_hours.toFixed(2) : 'Not Found';
            const professorCourseHours = feedback.professor_course_hours !== null ? feedback.professor_course_hours.toFixed(2) : 'Not Found';
    
            widget.innerHTML = `
                <span class="feedback-widget-title">Feedback:</span>
                <div class="feedback-widget-content">
                    <strong>${courseCode}</strong><br>
                    Course Rating: <strong>${courseRating}</strong><br>
                    Avg Hours: <strong>${courseHours}</strong><br>
                    <hr class="feedback-widget-divider">
                    <strong>Prof. ${instructor}</strong><br>
                    Prof Rating: <strong>${professorRating}</strong><br>
                    Prof x Course Rating: <strong>${professorCourseRating}</strong><br>
                    Prof x Course Hours: <strong>${professorCourseHours}</strong>
                </div>
                ${(courseRating !== 'Not Found') ? `
                    <div class="feedback-widget-buttons">
                    <a class="feedback-widget-button feedback-widget-left" href=${feedback.feedback_urls} target="_blank">
                        <span>See Course Feedback</span>
                    </a>
                </div>`
                : ''}
                
            `;

            // Add icons to buttons after creating the HTML
            const buttons = widget.querySelectorAll('.feedback-widget-button');
            buttons.forEach(button => {
                button.appendChild(createExternalLinkIcon());
            });

            // Add this before cell.appendChild(widget)
            widget.addEventListener('click', (e) => e.stopPropagation());

            container.appendChild(widget);
        }
    });
}
