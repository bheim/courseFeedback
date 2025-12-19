First and foremost, activate the virtual environment and install the requirements.

A tour of the folders:
BACKEND
analyzeCourseFeedback
- this contains the quarterly update python files that you will run every time feedback drops.
getCourseIDs
- run scrape_courses.py this once a quarter. It goes to the department sites and scrapes the list of courses that they offer. This will be used later for conducting feedback searches for these courses.
- this script only takes a couple of minutes to run and will keep you updated on which department it's currently looking at.
- the department and course_id combinations will be added to all_course_ids.db if they do not already exist there.
getCourseLinks
- you need cookies loaded to run scrape_course_links.py; the only time to run this script is if you want to scrape all feedback ever created (bar covid years, which are weird)
- it's much better to run the single_quarter.py script. In this, you indicate the quarter you want to scrape and this adds only those links to the database.
- single quarter script takes ~10 minutes. The other script takes hours!

cookies
- two files here that are essential. The first is getCookies.py which is the script to get cookies and the second is cookies.pkl which stores the cookies.
- To allow the scripts to act like a UChicago student and see the course feedback links and PDFs, you have to do getCookies.py and then login normally. After a minute, it will collect the cookies.
- This minute timer is used to give you time to complete logging in. You have to be logged in to get the right cookies. Do not do anything in that browser after logging in.
- Cookies will last for a few hours and then you'll have to run getCookies again once you see that you're getting network errors when trying to make searches that only UChicago students can access.

scrapeFeedback
- you need cookies
- ignore imageProcessor.py; it's necessary for analyzing images in course feedback but is never something you'd need to touch unless the images change
- scrapeFeedback.py looks at all the links in the course_urls.db and compares the combinations of department, course id, and url to those in the feedback database
if that combination isn't in the database, it will scrape the feedback and add the data to teh course_feedback.db
- you can set the number of workers in this file. I suggest a high number to make it go quickly. E.g., 10 workers would take a 10 hour task and make it only take 1 hour without taking up too much compute.

calculate_averages.py
- this will calculate average scores for professors and courses. Doing this on the backend is fast and prevents it from needing to happen every time a user needs the data

FRONTEND
I never touch the frontend. I built a basic version and someone made it prettier, and I just leave it that way. All you need to know is that there's a
"mutation observer" to detect when a user changes the course feedback screen, it will scrape off the data it needs to query the backend, it queries the backend,
and then it sends data back to the frontend.

One thing to flag is that there's frontend logic to handle alternative course listings. If that ever becomes a problem, you'd find it there.

You can load in the extension into chrome to test the extension. the courseFeedbackExtension folder is for testing the extension locally. Just make sure to start the flask
backend locally.

The courseFeeedBackExtensionProduction is for what you can use to test the pythonanywhere backend and is also what must be submitted to google so that the extension works for everyone.



To update the course feedback after the release of new feedback, follow these steps:
1. Run scrape_courses.py in getCourseIDs folder
This will get all the course ids. It's essential to run because there may be new courses. It's also not very difficult to run - it should only take a few minutes.

2. Run scrape_course_links.py
NOTE: Before you do this, you have to run getCookies which will require you to log into UChicago OKTA. This will provide the cookies to the webdriver to get the links.
You will have to do this multiple time throughout the process. That's why we process 25 courses at a time so if it gets interrupted, you don't lose your progress and you can change the SELECT statement in the code.

3. Run scrapeFeedback.py

4. Run calculate_averages.py

5. Push to the repo (the only thing that matter is the updated databases)

6. On pythonanywhere, pull from the repo

This will get the links to the feedback for all the courseIDs we just scraped. We will then scrape this.

