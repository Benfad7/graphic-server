import requests
import json

# --- Your Credentials ---
# Replace with your actual temporary or permanent access token
TOKEN = "EAARJR5ZBEEJkBPHdTf3vBV9cAaJ1JNFBQDfE5jsi9g41RTmrMO3D8zsXnhSGN0X1QnhYE2q1APGK2AmomP2ZAQJST5bqDBaOelZCgWeJwvGJRTlJRMWgdgoweXT1LQsDH8GyZBRdC2ehj8UUTCwzbuFQWlE5EJetMcgkDFOguIwSTLMkIYTvyZCS3mtVFTmucVBKG4VNNn7XCy0xmuHlOXa7HEBdeo49KC3Ds5T7D1QsaukVGqEcjys5IOgZDZD"
# Replace with your phone number ID
PHONE_NUMBER_ID = "YOUR_PHONE_NUMBER_ID"
# Replace with the recipient's phone number (include country code, no '+')
RECIPIENT_WAID = "15551234567"

# --- API Details ---
API_VERSION = "v20.0"
URL = f"https://graph.facebook.com/{API_VERSION}/{PHONE_NUMBER_ID}/messages"

# --- Message Payload ---
headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

data = {
    "messaging_product": "whatsapp",
    "to": RECIPIENT_WAID,
    "type": "text",
    "text": {
        "preview_url": False,
        "body": "Hello! This is an official message sent from the WhatsApp Cloud API."
    }
}

# --- Send the Message ---
try:
    response = requests.post(URL, headers=headers, data=json.dumps(data))
    response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)

    print("Message sent successfully!")
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")

except requests.exceptions.HTTPError as err:
    print(f"HTTP Error occurred: {err}")
    print(f"Response content: {err.response.content.decode()}")
except Exception as err:
    print(f"An error occurred: {err}")