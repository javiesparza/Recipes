import imaplib
import email
import os
from email.header import decode_header
from dotenv import load_dotenv
import base64
from bs4 import BeautifulSoup
import anthropic
import logging
import smtplib, ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logging.basicConfig(level=logging.INFO)

load_dotenv()

ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
if not ANTHROPIC_API_KEY:
    logging.error("ANTHROPIC_API_KEY not found in environment variables.")

# Claude AI Setup
claude_client = None
if ANTHROPIC_API_KEY:
    try:
        claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        logging.info("Claude AI client configured successfully.")
    except Exception as e:
        logging.error(f"Error configuring Claude AI: {e}.")
else:
    logging.warning("ANTHROPIC_API_KEY is missing. AI features are disabled.")

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
    if not claude_client:
        logging.warning("Claude client is not available.")
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
        response = claude_client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        return text.strip()
    except Exception as e:
        logging.error(f"Error generating recipes with Claude: {e}")
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