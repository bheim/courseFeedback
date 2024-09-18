import pickle
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
import time

# Path to your ChromeDriver
chrome_driver_path = "/opt/homebrew/bin/chromedriver"  # Replace with your actual path


# Create a Service object
service = Service(chrome_driver_path)

# Initialize the WebDriver with the Service object
driver = webdriver.Chrome(service=service)

# Navigate to the Okta login page (this is the login page you want to capture cookies from)
login_url = "https://uchicago.okta.com/"
driver.get(login_url)

# Wait for the user to log in manually
print("Please log in manually...")
time.sleep(60)  # Adjust the time if you need more time to log in

# Once logged in, capture cookies for the login domain (uchicago.okta.com)
cookies_login = driver.get_cookies()

# Save only the login cookies to a pickle file
with open('cookies.pkl', 'wb') as f:
    pickle.dump(cookies_login, f)

print("Login cookies saved to login_cookies.pkl")

# Close the browser
driver.quit()