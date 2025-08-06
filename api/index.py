import json
from flask import Flask, jsonify, request
from main import get_order_details, update_order_status, update_order_status_and_add_attachment
from flask_cors import CORS
import logging
import os
import time
from email_sender import get_access_token, send_approval_email

app = Flask(__name__)

# --- Logging Configuration ---
# Configure logging to be able to see debu   g messages in Vercel logs
logging.basicConfig(level=logging.INFO)

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
        app.logger.info("Access token is expired or not available. Fetching a new one.")
        new_token = get_access_token()
        if new_token:
            access_token = new_token
            token_creation_time = current_time
            return access_token
        else:
            app.logger.error("Failed to retrieve a new access token.")
            return None

    app.logger.info("Reusing existing access token.")
    return access_token


@app.route('/get-data')
def get_data():
    """
    Reads data from data.json.
    This pathing is made robust for Vercel's environment.
    """
    file_path = '' # Initialize to be accessible in except block
    try:
        # In the Vercel environment, the current working directory is the project's root.
        # This is a more reliable way to locate files than using __file__.
        project_root = os.getcwd()
        file_path = os.path.join(project_root, 'data.json')
        app.logger.info(f"Attempting to read data.json from: {file_path}")

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify(data)
    except FileNotFoundError:
        app.logger.error(f"File not found at the specified path: {file_path}")
        return jsonify({"status": "error", "message": f"data.json not found. Tried path: {file_path}"}), 404
    except Exception as e:
        app.logger.error(f"An error occurred while reading data.json: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/run-python')
def run_python_script():
    try:
        app.logger.info("Running Python script to get order details.")
        data = get_order_details()
        if data:
            return jsonify(data)
        else:
            app.logger.error("Failed to fetch order details from main.py.")
            return jsonify({"status": "error", "message": "Failed to fetch order details."}), 500
    except Exception as e:
        app.logger.error(f"An exception occurred in /run-python: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/update-status', methods=['POST'])
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
                # Still return success to the client, but log the email failure.
                app.logger.error("Order status updated but failed to send email due to invalid token.")
                return jsonify({"status": "success",
                                "message": "Order status updated but failed to send email due to invalid token."}), 200

            email_sent = send_approval_email(token, order_name, recipient_email, review_link,
                                             customer_name=customer_name)
            if not email_sent:
                # Retry once with a new token
                app.logger.info("Initial email send failed. Retrying with a new token.")
                global access_token
                access_token = None # Force a refresh
                token = get_valid_token()
                if token:
                    send_approval_email(token, order_name, recipient_email, review_link, customer_name=customer_name)
                else:
                    app.logger.error("Failed to send email on retry, no valid token.")

        return jsonify({"status": "success", "message": "Order status updated successfully."}), 200
    else:
        return jsonify({"status": "error", "message": "Failed to update order status."}), 500


@app.route('/update-status-and-attach', methods=['POST'])
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

# This is for local development testing
if __name__ == '__main__':
    app.run(debug=True)
