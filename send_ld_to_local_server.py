import os
import json
import requests
import time

# --- Configuration ---
# Set the path to your ngxarchive.json file on the NexStorm PC
JSON_FILE_PATH = r"C:\xampp\htdocs\Jayapura\data\ngxarchive.json" 

# Set the path where you want to store the last sent timestamp
LAST_TIMESTAMP_FILE = r"C:\nexstorm_data\last_timestamp.txt"

# Set the URL for your Django API endpoint
API_URL = "http://36.91.166.189/api/nexstorm-data/"

def send_data_to_api(data):
    """Sends the JSON payload to the Django API."""
    try:
        response = requests.post(API_URL, json=data, timeout=10)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        print(f"Data successfully sent. Status: {response.status_code}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"Failed to send data to API: {e}")
        return False

def get_last_timestamp():
    """Reads the last known timestamp from a local file."""
    if os.path.exists(LAST_TIMESTAMP_FILE):
        with open(LAST_TIMESTAMP_FILE, 'r') as f:
            try:
                return f.read().strip()
            except (IOError, ValueError):
                return None
    return None

def save_last_timestamp(timestamp):
    """Saves the latest timestamp to a local file."""
    try:
        with open(LAST_TIMESTAMP_FILE, 'w') as f:
            f.write(str(timestamp))
    except IOError as e:
        print(f"Failed to save timestamp to file: {e}")

def main():
    """Main logic to check for updates and send data."""
    try:
        # Check if the JSON file exists
        if not os.path.exists(JSON_FILE_PATH):
            print(f"JSON file not found at {JSON_FILE_PATH}")
            return
            
        # Read the JSON data
        with open(JSON_FILE_PATH, 'r') as f:
            current_data = json.load(f)

        current_timestamp = current_data.get("TimestampEpoch")
        last_timestamp = get_last_timestamp()

        # Check for changes in the TimestampEpoch
        if current_timestamp and str(current_timestamp) != last_timestamp:
            print(f"New data detected. Timestamp: {current_timestamp}")
            if send_data_to_api(current_data):
                save_last_timestamp(current_timestamp)
        else:
            print("No new data to send.")
            
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error processing JSON file: {e}")

if __name__ == "__main__":
    # Ensure the directory for the timestamp file exists
    os.makedirs(os.path.dirname(LAST_TIMESTAMP_FILE), exist_ok=True)
    main()
