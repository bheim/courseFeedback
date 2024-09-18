from PIL import Image
import pytesseract

# Function to process the image and extract text
def process_image(image_path):
    """
    This function takes an image path, processes the image, and extracts text from it.
    
    Args:
        image_path (str): The path to the image file.
    
    Returns:
        str: The extracted text from the image.
    """
    try:
        # Open the image
        img = Image.open(image_path)
        
        # Use Tesseract to extract text
        extracted_text = pytesseract.image_to_string(img)
        
        return extracted_text.strip()  # Return the extracted text
    
    except Exception as e:
        print(f"Error processing image: {e}")
        return None
