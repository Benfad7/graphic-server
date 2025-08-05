import os

import requests
import json

PRIORITY_API_BASE_URL = "https://benline.wee.co.il/"
API_USERNAME = "API"
API_PASSWORD = os.environ.get("API_PASSWORD")
COMPANY_NAME = "beline"
HEADERS = {
    'X-App-Id': 'APP008P',
    'X-App-Key': '1F42D7474ECF4FA6A0CB328819C71911'
}


def check_api_connection():
    """
    Checks the connection to the Priority API by fetching the metadata.
    This helps verify the base URL, credentials, and general API availability.
    """
    # The metadata endpoint is a good way to test the connection.
    # Note: The company/database name here is 'demo', which is often a default for metadata.
    metadata_endpoint = f"/odata/Priority/tabula.ini/demo/$metadata"
    url = f"{PRIORITY_API_BASE_URL.rstrip('/')}{metadata_endpoint}"

    print("\n--- 1. Checking API Connection ---")
    print(f"Attempting to connect to: {url}")
    print(f"Using username: {API_USERNAME} for authentication.")

    try:
        # Use a timeout to prevent the request from hanging indefinitely.
        response = requests.get(url, auth=(API_USERNAME, API_PASSWORD), timeout=30)
        # Raise an exception for HTTP errors (e.g., 401 Unauthorized, 404 Not Found, 500 Server Error)
        response.raise_for_status()
        print(f"✅ Successfully connected to the API! Status Code: {response.status_code}")
        # with open('meta_data.json', 'w', encoding='utf-8') as f:
        # json.dump(response.text, f, ensure_ascii=False, indent=4)
        # print(json.dumps(response.text, indent=4, ensure_ascii=False))

        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ API Connection Failed: {e}")
        # If the server provided an error message in the response, print it.
        if e.response is not None:
            print(f"Error Response Body: {e.response.text}")
        return False


def get_order_details():
    """
    Fetches order details from the Priority API and saves them to a JSON file.
    """
    endpoint = f"/odata/Priority/tabula.ini/{COMPANY_NAME}/ORDERS"
    url = f"{PRIORITY_API_BASE_URL.rstrip('/')}{endpoint}"
    statuses_to_fetch = ["3אצל הגרפיקא"]
    filter_query = " or ".join([f"ORDSTATUSDES eq '{s}'" for s in statuses_to_fetch])
    params = {
        '$filter': filter_query,
        '$expand': 'EXTFILES_SUBFORM,ORDERSTEXT_SUBFORM,ORDERSDOCS_SUBFORM,ORDERITEMS_SUBFORM, ORDERSCONT_SUBFORM'
    }
    print(f"Connecting to: {url}")
    try:
        response = requests.get(
            url,
            auth=(API_USERNAME, API_PASSWORD),
            params=params,
            headers=HEADERS,
            timeout=30
        )
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        order_data = response.json()
        with open('data.json', 'w', encoding='utf-8') as f:
            json.dump(order_data, f, ensure_ascii=False, indent=4)
        print(f"✅ Successfully fetched data and saved to '{'data.json'}'")
        return order_data

    except requests.exceptions.RequestException as e:
        print(f"❌ API Request Failed: {e}")
        if e.response is not None:
            print(f"Error Response Body: {e.response.text}")
        return None


def update_order_status(order_name, status):
    print(f"Order: {order_name}, New Status: {status}")
    endpoint = f"/odata/Priority/tabula.ini/{COMPANY_NAME}/ORDERS('{order_name}')"
    url = f"{PRIORITY_API_BASE_URL.rstrip('/')}{endpoint}"
    payload = {
        "ORDSTATUSDES": status
    }
    print(f"Sending PATCH request to: {url}")
    try:
        response = requests.patch(
            url,
            auth=(API_USERNAME, API_PASSWORD),
            headers=HEADERS,
            json=payload,
            timeout=30
        )

        response.raise_for_status()

        print(f"✅ Successfully updated status for '{order_name}' in Priority. Status Code: {response.status_code}")
        return True

    except requests.exceptions.RequestException as e:
        print(f"❌ API Request Failed: {e}")
        if e.response is not None:
            print(f"Error Response Status: {e.response.status_code}")
            print(f"Error Response Body: {e.response.text}")
        return False
    except Exception as e:
        print(f"❌ An unexpected error occurred during API update: {e}")
        return False


def update_order_status_and_add_attachment(order_name, status, file_base64):
    if not file_base64:
        print("No file to attach.")
        return True

    endpoint = f"/odata/Priority/tabula.ini/{COMPANY_NAME}/ORDERS('{order_name}')/EXTFILES_SUBFORM"
    url = f"{PRIORITY_API_BASE_URL.rstrip('/')}{endpoint}"

    payload = {
        "EXTFILEDES": f"{order_name} confirmed",
        "EXTFILENAME": file_base64,
    }

    print(f"Sending POST request to add attachment: {url}")
    try:
        response = requests.post(
            url,
            auth=(API_USERNAME, API_PASSWORD),
            headers=HEADERS,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        print(f"✅ Successfully added attachment for '{order_name}'. Status Code: {response.status_code}")
        update_order_status(order_name, status)
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to add attachment: {e}")
        if e.response is not None:
            print(f"Error Response Status: {e.response.status_code}")
            print(f"Error Response Body: {e.response.text}")
        return False
    except Exception as e:
        print(f"❌ An unexpected error occurred during attachment upload: {e}")
        return False


if __name__ == "__main__":
    # check_api_connection()
    get_order_details()
