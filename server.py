import json
import base64
from flask import Flask, jsonify, request
from main import get_order_details, update_order_status, update_order_status_and_add_attachment
from flask_cors import CORS
from flask import make_response
import logging
import os
import time
from email_sender import get_access_token, send_approval_email
import requests
from urllib.parse import urlparse, quote, unquote
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
INFORU_TOKEN = os.environ.get("INFORU_TOKEN")
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




def compose_public_url_for_key(object_key: str) -> str:
    base = R2_PUBLIC_BASE_URL.rstrip("/")
    # URL-encode each path segment to avoid invalid URLs (spaces, unicode, etc.)
    encoded_key = "/".join(quote(seg, safe="-_.~") for seg in object_key.split("/"))
    if R2_BUCKET_NAME and f"/{R2_BUCKET_NAME}" not in base:
        return f"{base}/{R2_BUCKET_NAME}/{encoded_key}"
    return f"{base}/{encoded_key}"



def upload_json_to_r2(data: dict) -> bool:
    if not _s3_client:
        print("R2 S3 client not configured. Skipping upload.")
        return False


@app.route('/r2/presign-upload', methods=['POST'])
def presign_upload():
    if not _s3_client:
        return jsonify({"status": "error", "message": "R2 client not configured"}), 500
    try:
        body = request.get_json(force=True)
        filename = body.get('filename') or 'file'
        content_type = body.get('contentType') or 'application/octet-stream'
        order_id = body.get('orderId') or 'misc'
        folder = body.get('folder') or 'orders'
        # Generate an object key: e.g., orders/<orderId>/<ts>_<filename>
        ts = str(int(time.time() * 1000))
        safe_name = filename.replace('\\', '/').split('/')[-1]
        object_key = f"{folder}/{order_id}/{ts}_{safe_name}"

        params = {
            'Bucket': R2_BUCKET_NAME,
            'Key': object_key,
            'ContentType': content_type,
        }
        url = _s3_client.generate_presigned_url(
            ClientMethod='put_object',
            Params=params,
            ExpiresIn=3600,
        )
        public_url = compose_public_url_for_key(object_key)
        return jsonify({
            'uploadUrl': url,
            'key': object_key,
            'publicUrl': public_url,
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/r2/delete', methods=['POST'])
def delete_object():
    if not _s3_client:
        return jsonify({"status": "error", "message": "R2 client not configured"}), 500
    try:
        body = request.get_json(force=True)
        key = body.get('key')
        if not key:
            # Try derive key from publicUrl
            public_url = body.get('publicUrl')
            if public_url:
                # Expect key after bucket in URL path
                path = urlparse(public_url).path
                # Remove leading '/bucket/' and decode percent-encoding
                if path.startswith(f"/{R2_BUCKET_NAME}/"):
                    key_enc = path[len(R2_BUCKET_NAME) + 2:]
                    key = unquote(key_enc)
        if not key:
            return jsonify({"status": "error", "message": "Missing key"}), 400
        _s3_client.delete_object(Bucket=R2_BUCKET_NAME, Key=key)
        return jsonify({"status": "success"})
    except (BotoCoreError, ClientError) as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/r2/get', methods=['GET'])
def get_object_proxy():
    if not _s3_client:
        return jsonify({"status": "error", "message": "R2 client not configured"}), 500
    key = request.args.get('key')
    if key:
        key = unquote(key)
    url_param = request.args.get('url')
    if not key and url_param:
        # derive key from url
        path = urlparse(url_param).path
        if path.startswith(f"/{R2_BUCKET_NAME}/"):
            key = unquote(path[len(R2_BUCKET_NAME) + 2:])
    if not key:
        return jsonify({"status": "error", "message": "Missing key"}), 400
    disposition = request.args.get('disposition', 'inline')
    try:
        obj = _s3_client.get_object(Bucket=R2_BUCKET_NAME, Key=key)
        body = obj['Body'].read()
        content_type = obj.get('ContentType', 'application/octet-stream')
        resp = make_response(body)
        resp.headers['Content-Type'] = content_type
        resp.headers['Access-Control-Allow-Origin'] = '*'
        if disposition in ('inline', 'attachment'):
            # Let browser decide filename if not provided
            resp.headers['Content-Disposition'] = f"{disposition}"
        return resp
    except (BotoCoreError, ClientError) as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/r2/upload', methods=['POST'])
def upload_via_server():
    if not _s3_client:
        return jsonify({"status": "error", "message": "R2 client not configured"}), 500
    try:
        body = request.get_json(force=True)
        data_url = body.get('dataUrl')
        filename = body.get('filename') or 'file'
        content_type = body.get('contentType') or 'application/octet-stream'
        order_id = body.get('orderId') or 'misc'
        folder = body.get('folder') or 'uploads'
        if not data_url or 'base64,' not in data_url:
            return jsonify({"status": "error", "message": "Invalid dataUrl"}), 400
        ts = str(int(time.time() * 1000))
        safe_name = filename.replace('\\', '/').split('/')[-1]
        object_key = f"{folder}/{order_id}/{ts}_{safe_name}"

        base64_part = data_url.split('base64,', 1)[1]
        data_bytes = base64.b64decode(base64_part)

        _s3_client.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=object_key,
            Body=data_bytes,
            ContentType=content_type,
        )
        return jsonify({
            'key': object_key,
            'publicUrl': compose_public_url_for_key(object_key)
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
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



@app.route('/run-python')
def run_python_script():
    try:
        print("Running Python script")
        data = get_order_details()
        if data:
            # Return the data without saving it server-side
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
            recipient_phone_number = data.get('phoneNumber')
            customer_name = data.get('name')
            review_link = data.get('reviewLink')

            if send_email_flag:
                if not all([recipient_email, review_link, recipient_phone_number]):
                    return jsonify({"status": "error", "message": "Missing email or reviewLink for sending email"}), 400
                #send messages to inforu
                #/
                """
                url = 'https://cloud.inforu.co.il/api/Automation/Trigger'
                payload = {
                    "User": {
                        "Username": "benline",  
                        "Token": INFORU_TOKEN
                    },
                    "Data": {
                        "ApiEventName": "graphics",
                        "Contacts": [
                            {
                                "link": str(review_link),
                                "name": str(customer_name),
                                "order": str(order_name),
                                "PhoneNumber": recipient_phone_number,
                            }
                        ]
                    }
                }
                payload_json_str = json.dumps(payload, ensure_ascii=False)
                print(payload_json_str)
                try:
                    headers = {'Content-Type': 'application/json; charset=utf-8'}
                    response = requests.post(url, data=payload_json_str.encode('utf-8'), headers=headers, timeout=50)
                    if response.status_code == 200:
                        print("messages sent successfully")
                    else:
                        print(f"Error! Status code: {response.status_code}")
                        print("Response text:")
                        print(response.text)
                except requests.exceptions.RequestException as e:
                    print(f"An error occurred: {e}")
                """
                #send an email to the customer
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
