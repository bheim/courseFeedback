// Function to extract course data from the provided HTML structure
function scrapeCourseData() {
    const courses = [];
    
    // Select all course rows
    const courseRows = document.querySelectorAll('tbody.ps_grid-body tr.ps_grid-row');

    courseRows.forEach((row, index) => {
        // Dynamic selector for course title
        let courseTitleSelector = `#win0divUC_CLSRCH_WRK_UC_CLASS_TITLE\\$${index} .ps_box-value`;
        let courseTitleElement = row.querySelector(courseTitleSelector);
        let courseTitle = courseTitleElement?.textContent.trim() || '';

        // Dynamic selector for course ID (This part is from the HTMLArea where the ID is embedded)
        let courseIdSelector = `#win0divUC_RSLT_NAV_WRK_HTMLAREA\\$${index}`;
        let courseIdElement = row.querySelector(courseIdSelector);
        let courseIdText = courseIdElement?.textContent.trim() || '';
        let courseId = courseIdText.split('/')[0];  // Extract course ID from the text

        // Dynamic selector for instructor name
        let instructorSelector = `#win0divUC_CLSRCH_WRK_SSR_INSTR_LONG\\$${index} .ps_box-value`;
        let instructorElement = row.querySelector(instructorSelector);
        let instructor = instructorElement?.textContent.trim() || '';

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

// Function to send the scraped data to the Flask backend
function sendDataToBackend(courses) {
    fetch('http://localhost:5000/get-course-feedback', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(courses),  // Send the scraped courses data
    })
    .then(response => response.json())
    .then(data => {
        console.log('Response from backend:', data);
        // This is where you would handle the response, if necessary
    })
    .catch(error => console.error('Error:', error));
}

// Execute the scraper and send the data when the page loads
document.addEventListener('DOMContentLoaded', () => {
    const scrapedCourses = scrapeCourseData();  // Step 1: Scrape the course data
    sendDataToBackend(scrapedCourses);  // Step 2: Send the data to the backend
});