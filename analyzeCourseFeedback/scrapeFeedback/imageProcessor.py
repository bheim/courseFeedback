from PIL import Image
from io import BytesIO
import pytesseract
import requests

BASE_URL = 'https://uchicago.bluera.com'

# Process image using OCR and extract hours worked data
def process_image(image_url):
    response = requests.get(BASE_URL + image_url)
    if response.status_code == 200:
        img = Image.open(BytesIO(response.content))

        # Use Tesseract to extract text from the image
        extracted_text = pytesseract.image_to_string(img)

        results = {}

        # Extract total responses from the image
        total_responses = None
        lines = extracted_text.split("\n")
        for line in lines:
            if 'Total' in line:
                try:
                    total_responses = int(line.split('(')[1].split(')')[0])
                    break
                except (IndexError, ValueError):
                    print("Error extracting total responses.")
                    continue
        
        # Ensure we have the total responses before proceeding
        if not total_responses:
            print("Error: Could not extract total number of responses.")
            return {}

        # Groups we want to extract data for
        groups = ['<5 hours', '5-10 hours', '10-15 hours', '15-20 hours', '20-25 hours', '25-30 hours', '>30 hours']

        # Extract data for each group
        for line in lines:
            line = line.strip()
            for group in groups:
                if group in line:
                    try:
                        count = int(line.split('(')[1].split(')')[0])  # Extract the count
                        percentage = (count / total_responses) * 100
                        results[group] = percentage  # Store as float (no '%' symbol)
                    except (IndexError, ValueError):
                        print(f"Error processing line: {line}")
                        continue

        return results
    else:
        print(f"Failed to retrieve image from {image_url}")
        return {}
