import imaplib
import email
import os
from email.header import decode_header
from dotenv import load_dotenv
import base64
from bs4 import BeautifulSoup


load_dotenv()

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


def main():
    email_html = get_misfits_market_email_imap()
    if not email_html:
        print("Failed to retrieve email content.")
        return

    ingredient_list = parse_ingredients(email_html)
    if ingredient_list.empty:
        print("No ingredients found.")
        return
    



# --- Main Script Execution ---
if __name__ == '__main__':
    main()