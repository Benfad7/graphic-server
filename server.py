import json
from flask import Flask, jsonify, request
from main import get_order_details, update_order_status, update_order_status_and_add_attachment
from flask_cors import CORS
import logging
import os
import time
from email_sender import get_access_token, send_approval_email

app = Flask(__name__)

CORS(app, origins="*")

# --- Token Management ---
access_token = None
token_creation_time = 0


def get_valid_token():
    """
    Returns a valid access token, refreshing it if it's expired or doesn't exist.
    Tokens from Microsoft Graph are typically valid for 1 hour (3600 seconds).
    We'll refresh it after 50 minutes (3000 seconds) to be safe.
    """
    global access_token, token_creation_time
    current_time = time.time()

    if not access_token or (current_time - token_creation_time) > 3000:
        print("Access token is expired or not available. Fetching a new one.")
        new_token = get_access_token()
        if new_token:
            access_token = new_token
            token_creation_time = current_time
            return access_token
        else:
            print("Failed to retrieve a new access token.")
            return None

    print("Reusing existing access token.")
    return access_token


# Set up logging
log_file = 'call_count.log'
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
handler = logging.FileHandler(log_file)
logger.addHandler(handler)

# Initialize call count
if os.path.exists(log_file):
    with open(log_file, 'r') as f:
        try:
            call_count = int(f.read().strip())
        except ValueError:
            call_count = 0
else:
    call_count = 0


def log_call(func):
    def wrapper(*args, **kwargs):
        global call_count
        call_count += 1
        logger.info(f'The server has been called {call_count} times.')
        return func(*args, **kwargs)

    wrapper.__name__ = func.__name__
    return wrapper


@app.route('/get-data')
@log_call
def get_data():
    try:
        with open('data.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify(data)
    except FileNotFoundError:
        return jsonify({"status": "error", "message": "data.json not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/run-python')
@log_call
def run_python_script():
    try:
        print("Running Python script")
        data = get_order_details()
        if data:
            return jsonify(data)
        else:
            return jsonify({"status": "error", "message": "Failed to fetch order details."}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/update-status', methods=['POST'])
@log_call
def update_status():
    data = request.get_json()
    order_name = data.get('orderName')
    status = data.get('status')

    if not order_name or not status:
        return jsonify({"status": "error", "message": "Missing orderName or status"}), 400

    if update_order_status(order_name, status):
        # If the status is for graphic approval, send an email
        if status == '4לאשור גרפיק':
            recipient_email = data.get('email')
            customer_name = data.get('name')
            review_link = data.get('reviewLink')

            if not all([recipient_email, review_link]):
                return jsonify({"status": "error", "message": "Missing email or reviewLink for sending email"}), 400

            token = get_valid_token()
            if not token:
                return jsonify({"status": "success",
                                "message": "Order status updated but failed to send email due to invalid token."}), 200

            email_sent = send_approval_email(token, order_name, recipient_email, review_link,
                                             customer_name=customer_name)
            if not email_sent:
                # Retry once with a new token
                global access_token
                access_token = None
                token = get_valid_token()
                if token:
                    send_approval_email(token, order_name, recipient_email, review_link, customer_name=customer_name)

        return jsonify({"status": "success", "message": "Order status updated successfully."}), 200
    else:
        return jsonify({"status": "error", "message": "Failed to update order status."}), 500


@app.route('/update-status-and-attach', methods=['POST'])
@log_call
def update_status_and_attach():
    data = request.get_json()
    order_name = data.get('orderName')
    status = data.get('status')
    file_base64 = data.get('fileBase64')

    if not order_name or not status:
        return jsonify({"status": "error", "message": "Missing orderName or status"}), 400

    if update_order_status_and_add_attachment(order_name, status, file_base64):
        return jsonify({"status": "success", "message": "Order status updated and attachment added successfully."}), 200
    else:
        return jsonify({"status": "error", "message": "Failed to update order status or add attachment."}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5001, ssl_context='adhoc')
