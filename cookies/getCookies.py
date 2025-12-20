import pickle
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time

# Path to your ChromeDriver
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))

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

print("Login cookies saved to cookies.pkl")

# Close the browser
driver.quit()