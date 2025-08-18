import imaplib
import email
import os
from email.header import decode_header
from dotenv import load_dotenv
import base64
from bs4 import BeautifulSoup
import google.generativeai as genai
import logging
import smtplib, ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logging.basicConfig(level=logging.INFO)

load_dotenv()

GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
if not GOOGLE_API_KEY:
    logging.error("GOOGLE_API_KEY not found in environment variables. Gemini features will be disabled.")

# Gemini AI Setup
gemini_model = None
if GOOGLE_API_KEY:
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        # 'gemini-2.0-flash-lite' is the free model name for Gemini
        gemini_model = genai.GenerativeModel('gemini-2.0-flash-lite')
        logging.info("Gemini AI Model configured successfully with 'gemini-2.0-flash-lite'.")
    except Exception as e:
        logging.error(f"Error configuring Gemini AI: {e}. Gemini features will be disabled.")
        gemini_model = None
else:
    logging.warning("GOOGLE_API_KEY is missing. Gemini features are disabled.")

# Replace these with your Gmail address and the App Password you generated
GMAIL_USER = os.getenv('GMAIL_USER')
APP_PASSWORD = os.getenv('APP_PASSWORD')

def get_misfits_market_email_imap():
    try:
        # Connect to Gmail's IMAP server over SSL
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        mail.login(GMAIL_USER, APP_PASSWORD)
        
        # Select the mailbox (e.g., INBOX)
        mail.select('inbox')
        
        # Search for the Misfits Market email
        # The search criteria is case-sensitive and must be in all caps
        status, messages = mail.search(None, 'FROM "donotreply@misfitsmarket.com"', 'SUBJECT "We received your order"')
        
        if status != 'OK' or not messages[0]:
            print("No Misfits Market email found.")
            return None
        else:
            print(f"Found {len(messages[0].split())} emails in the inbox.")
            
        # Get the ID of the most recent email
        latest_email_id = messages[0].split()[-1]
        
        # Fetch the email by its ID
        status, msg_data = mail.fetch(latest_email_id, '(RFC822)')
        
        if status != 'OK':
            print("Error fetching email.")
            return None

        raw_email = msg_data[0][1]
        
        # Parse the raw email data
        msg = email.message_from_bytes(raw_email)
        
        html_body = None
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == 'text/html':
                    html_body = part.get_payload(decode=True).decode('utf-8')
                    break
        else:
            if msg.get_content_type() == 'text/html':
                html_body = msg.get_payload(decode=True).decode('utf-8')
        
        mail.close()
        mail.logout()
        
        return html_body
        
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

# ...existing code...
def parse_ingredients(html_content):
    """Parses the HTML content to find the list of ingredients."""
    if not html_content:
        return []

    soup = BeautifulSoup(html_content, 'html.parser')
    ingredients = []

    # Find the table that contains the order items
    order_tables = soup.find_all('table', attrs={'width': '500'})
    for table in order_tables:
        for row in table.find_all('tr'):
            tds = row.find_all('td')
            if len(tds) >= 3:
                name_td = tds[0]
                qty_td = tds[1]
                price_td = tds[2]
                # Check for the correct style and ignore header/subtotal rows
                style = name_td.get('style', '')
                if (
                    'font-size: 15px' in style
                    and 'font-weight: 400' in style
                    and '$' in price_td.get_text()
                ):
                    ingredient = name_td.get_text(strip=True)
                    # Exclude subtotal/discount/total rows
                    if not any(x in ingredient.lower() for x in ['subtotal', 'discount', 'shipping', 'tax', 'total', 'tip', 'credit']):
                        ingredients.append(ingredient)
    return ingredients

def prompt_gemini(ingredient_list):
    if not gemini_model:
        logging.warning("Gemini model is not available.")
        return
    
    prompt = f"""
    Given the following list of ingredients, please create a meal plan for 4-6 dinners 
    this week. The plan should be a mix of quick weeknight meals and more involved weekend 
    recipes. For each recipe, provide the title, ingredients, and instructions. Format the 
    entire response as a single, valid HTML string. Please use <h1> for the overall meal 
    plan title, <h2> for each recipe title, an unordered list (<ul>) with <li> tags for 
    ingredients, and an ordered list (<ol>) with <li> tags for instructions.
     
    Ingredients:  {', '.join(ingredient_list)}
    """

    try:
        response = gemini_model.generate_content(prompt)

        recipes = response.text.strip()
        return recipes


    except Exception as e:
        logging.error(f"Error generating recipes with Gemini: {e}")
        try:
            # Attempt to get feedback if the error occurred after the API call
             logging.error(f"Gemini prompt feedback: {response.prompt_feedback}")
        except Exception:
             pass # Ignore if feedback isn't available
        return "Error: Could not generate AI suggestion due to an internal error."
    
def send_email(to_email, subject, body_html):
    context = ssl.create_default_context()

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = GMAIL_USER
    message["To"] = to_email

    part1 = MIMEText(body_html, "html")
    message.attach(part1)
    
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(GMAIL_USER, APP_PASSWORD)
            server.sendmail(
                GMAIL_USER, to_email, message.as_string()
            )
            print("Email sent successfully!")
            
    except Exception as e:
        print(f"Error sending email: {e}")

def main():
    email_html = get_misfits_market_email_imap()
    if not email_html:
        print("Failed to retrieve email content.")
        return

    ingredient_list = parse_ingredients(email_html)
    if len(ingredient_list) == 0:
        print("No ingredients found.")
        return

    recipes = prompt_gemini(ingredient_list)
    if not recipes:
        print("Failed to generate recipes.")
        return

    send_email(GMAIL_USER, "Weekly Recipe Suggestions", recipes)


if __name__ == '__main__':
    main()