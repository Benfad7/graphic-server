import json
from flask import Flask, jsonify, request
from main import get_order_details, update_order_status, update_order_status_and_add_attachment
from flask_cors import CORS
import logging
import os
import time
from email_sender import get_access_token, send_approval_email
import requests
from typing import Optional

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
except Exception:
    boto3 = None
    BotoCoreError = ClientError = Exception

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


###############################
# Cloudflare R2 configuration #
###############################

R2_ACCOUNT_ID = "944539d199bcd56d08fd20e2920753c9"
R2_ACCESS_KEY_ID = "869cd104efd961706ce96b5d051388b3"
R2_SECRET_ACCESS_KEY = "5ff7e1df459b90aba30e39fd91e04a01b0573014dd224e79036f197fbdf21fcd"
R2_BUCKET_NAME = "graphic"
R2_OBJECT_KEY = os.environ.get("R2_OBJECT_KEY", "data.json")
# Public base URL to read from. Fallback to the value provided by the user
R2_PUBLIC_BASE_URL = os.environ.get(
    "R2_PUBLIC_BASE_URL",
    "https://944539d199bcd56d08fd20e2920753c9.r2.cloudflarestorage.com",
)

_s3_client = None
if boto3 and R2_ACCOUNT_ID and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY and R2_BUCKET_NAME:
    try:
        _s3_client = boto3.client(
            "s3",
            endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            region_name="auto",
        )
    except Exception as e:
        print(f"Failed to initialize R2 S3 client: {e}")


def _compose_public_object_url() -> str:
    base = R2_PUBLIC_BASE_URL.rstrip("/")
    if R2_BUCKET_NAME and f"/{R2_BUCKET_NAME}" not in base:
        return f"{base}/{R2_BUCKET_NAME}/{R2_OBJECT_KEY}"
    return f"{base}/{R2_OBJECT_KEY}"


def download_json_from_r2() -> Optional[dict]:
    """Try downloading via S3 API if configured; otherwise use public HTTP URL."""
    # Prefer authenticated S3 API (does not require public object)
    if _s3_client:
        try:
            obj = _s3_client.get_object(Bucket=R2_BUCKET_NAME, Key=R2_OBJECT_KEY)
            body_bytes = obj["Body"].read()
            return json.loads(body_bytes.decode("utf-8"))
        except (BotoCoreError, ClientError, Exception) as e:
            print(f"Failed to download JSON from R2 via S3 API: {e}")
            # fall through to public HTTP

    # Fallback to public HTTP if available
    try:
        url = _compose_public_object_url()
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Failed to download JSON from R2 public URL: {e}")
        return None


def upload_json_to_r2(data: dict) -> bool:
    if not _s3_client:
        print("R2 S3 client not configured. Skipping upload.")
        return False
    try:
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        _s3_client.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=R2_OBJECT_KEY,
            Body=body,
            ContentType="application/json; charset=utf-8",
            CacheControl="no-cache",
        )
        print(f"✅ Uploaded JSON to R2 bucket='{R2_BUCKET_NAME}' key='{R2_OBJECT_KEY}'")
        return True
    except (BotoCoreError, ClientError) as e:
        print(f"❌ Failed to upload JSON to R2: {e}")
        return False


@app.route('/get-data')
def get_data():
    try:
        data = download_json_from_r2()
        if data is not None:
            return jsonify(data)

        with open('data.json', 'r', encoding='utf-8') as f:
            local_data = json.load(f)
        return jsonify(local_data)
    except FileNotFoundError:
        return jsonify({"status": "error", "message": "data.json not found and R2 unavailable"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/run-python')
def run_python_script():
    try:
        print("Running Python script")
        data = get_order_details()
        if data:
            upload_json_to_r2(data)
            return jsonify(data)
        else:
            return jsonify({"status": "error", "message": "Failed to fetch order details."}), 500
    except Exception as e:
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
            send_email_flag = data.get('sendEmail', True)
            if not isinstance(send_email_flag, bool):
                # Be defensive; treat truthy/falsy
                send_email_flag = bool(send_email_flag)

            recipient_email = data.get('email')
            customer_name = data.get('name')
            review_link = data.get('reviewLink')

            if send_email_flag:
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
                        send_approval_email(token, order_name, recipient_email, review_link,
                                            customer_name=customer_name)

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
        return jsonify({"status": "error", "message": "Failed to update order status or add attachment. "}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5001, ssl_context='adhoc')
