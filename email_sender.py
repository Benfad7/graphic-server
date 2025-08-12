import requests
import json
import os

# --- Configuration ---
# It's best practice to store credentials in environment variables
# for security, rather than hardcoding them.
# Replace with your actual values if not using environment variables.
CLIENT_ID = os.environ.get("CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
TENANT_ID = os.environ.get("TENANT_ID")
SENDER_EMAIL = "graphic@benline.co.il"


def get_access_token():
    """
    Authenticates with Microsoft Entra ID and retrieves an access token.
    """
    token_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    token_data = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default"
    }

    try:
        token_r = requests.post(token_url, data=token_data)
        token_r.raise_for_status()  # Raise an exception for bad status codes
        token_response = token_r.json()
        access_token = token_response.get("access_token")

        if not access_token:
            print("Error: Access token not found in the response.")
            return None

        print("Successfully retrieved access token.")
        return access_token

    except requests.exceptions.RequestException as e:
        print(f"Error during token retrieval: {e}")
        return None


def send_approval_email(access_token, order_id, recipient_email, review_link, customer_name="הלקוח"):
    """
    Sends a modern, styled email in Hebrew for graphic approval using the Microsoft Graph API.
    """
    send_mail_url = f"https://graph.microsoft.com/v1.0/users/{SENDER_EMAIL}/sendMail"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # Modern HTML email body with updated CSS
    html_body = f"""
    <!DOCTYPE html>
    <html lang="he" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{
                font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
                margin: 0;
                padding: 0;
                background-color: #f6f9fc;
                direction: rtl;
            }}
            .email-wrapper {{
                width: 100%;
                background-color: #f6f9fc;
                padding: 20px 0;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                background-color: #ffffff;
                border-radius: 8px;
                overflow: hidden;
                border: 1px solid #e0e0e0;
            }}
            .header {{
                background-color: #0d6efd;
                color: #ffffff;
                padding: 25px;
                text-align: center;
            }}
            .header h1 {{
                margin: 0;
                font-size: 28px;
                font-weight: 600;
            }}
            .content {{
                padding: 40px;
                color: #000000; /* Changed to black */
                line-height: 1.7;
                text-align: right;
            }}
            .content p {{
                margin: 0 0 15px 0;
                font-size: 16px;
            }}
            .button-container {{
                text-align: center;
                margin-top: 30px;
            }}
            .button {{
                display: inline-block;
                padding: 14px 28px;
                border-radius: 6px;
                text-decoration: none;
                font-weight: bold;
                font-size: 18px;
                background-color: #0d6efd;
                color: #ffffff !important; /* Ensured button text is white */
                border: none;
                white-space: nowrap;
            }}
            .footer {{
                padding: 20px 40px;
                font-size: 14px;
                color: #555555;
                background-color: #f8f9fa;
                text-align: right;
            }}
        </style>
    </head>
    <body>
        <div class="email-wrapper">
            <div class="container">
                <div class="header">
                    <h1>!הגרפיקה מוכנה ומחכה לאישור שלך</h1>
                </div>
                <div class="content">
                    <p>,שלום {customer_name}</p>
                    <p>.מבן ליין מוכנה לבדיקה <strong>{order_id}</strong> הגרפיקה עבור הזמנתך מספר</p>
                    <p>על מנת שנוכל להתקדם לשלב ההדפסה, אנא לחצ/י על הכפתור מטה כדי לצפות בגרפיקה, ולאחר מכן לאשר אותה או לבקש שינויים בעמוד שיפתח</p>
                    <div class="button-container">
                        <a href="{review_link}" class="button">לצפייה ואישור הגרפיקה</a>
                    </div>
                </div>
                <div class="footer">
                    <p>,תודה רבה<br>צוות בן ליין</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """

    email_body = {
        "message": {
            "subject": f"הגרפיקה שלך להזמנה {order_id} מבן ליין מוכנה לאישור",
            "body": {
                "contentType": "HTML",
                "content": html_body
            },
            "toRecipients": [
                {
                    "emailAddress": {
                        "address": recipient_email
                    }
                }
            ]
        },
        "saveToSentItems": "true"
    }

    try:
        send_r = requests.post(send_mail_url, headers=headers, data=json.dumps(email_body))
        send_r.raise_for_status()

        if send_r.status_code == 202:
            print(f"Email successfully sent to {recipient_email}!")
            return True
        else:
            print(f"Email could not be sent. Status code: {send_r.status_code}")
            print(f"Response: {send_r.text}")
            return False

    except requests.exceptions.RequestException as e:
        print(f"Error during email sending: {e}")
        return False
