import os
import requests
import json
from datetime import datetime, timedelta
import obspy

# --- Configuration ---
# Your API endpoint URL
API_URL = "http://36.91.166.189/api/availability/report/"

# Base directory of your SeisComP archive
ARCHIVE_BASE_DIR = "/home/sysop/seiscomp/var/lib/archive"

# List of stations and channels to process
STATIONS_AND_CHANNELS = {
    "AMPM": ["SHE.D", "SHN.D", "SHZ.D"],
    "ANAPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "ARKPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "ARMPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "ARPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "BAKPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "BATPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "BTSPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "DYPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "EDMPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "ELMPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "FAKI": ["SHE.D", "SHN.D", "SHZ.D"],
    "FKMPM": ["SHE.D", "SHN.D", "SHZ.D"],
    "FKSPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "GENI": ["SHE.D", "SHN.D", "SHZ.D"],
    "IWPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "JAY": ["SHE.D", "SHN.D", "SHZ.D"],
    "KIMPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "LJIPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "MBPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "MIBPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "MMPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "MTJPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "MTMPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "NBPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "OBMPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "RKPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "SATPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "SJPM": ["SHE.D", "SHN.D", "SHZ.D"],
    "SKPM": ["SHE.D", "SHN.D", "SHZ.D"],
    "SMPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "SOMPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "SRPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "SUSPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "SWI": ["SHE.D", "SHN.D", "SHZ.D"],
    "SWPM": ["SHE.D", "SHN.D", "SHZ.D"],
    "TRPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "TSPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "UWINPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "WAMPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "WANPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "WWPI": ["SHE.D", "SHN.D", "SHZ.D"],
    "YBYPI": ["SHE.D", "SHN.D", "SHZ.D"],
}

# --- Helper Functions ---
def get_archive_files(station, date):
    """
    Constructs the full path to the waveform files for a given station and date.
    Args:
        station (str): The station code (e.g., "BATPI").
        date (datetime): The date for which to get files.
    Returns:
        list: A list of full paths to the waveform files.
    """
    julian_day = date.timetuple().tm_yday
    year = date.year
    
    files = []
    
    # Path to the station's archive directory
    day_dir_base = os.path.join(ARCHIVE_BASE_DIR, str(year), "IA", station)

    for channel_id in STATIONS_AND_CHANNELS.get(station, []):
        file_name = f"IA.{station}.{channel_id}.{year}.{julian_day:03d}"
        file_path = os.path.join(day_dir_base, channel_id, file_name)
        if os.path.exists(file_path):
            files.append(file_path)
    
    return files

def calculate_availability_from_files(files):
    """
    Calculates the percentage availability from a list of mseed files.
    Args:
        files (list): A list of full paths to mseed files.
    Returns:
        dict: A dictionary of channels and their availability percentage.
    """
    if not files:
        print("No files found to process.")
        return {}
    
    channel_availability = {}
    
    for file_path in files:
        try:
            # Read the waveform file with obspy
            st = obspy.read(file_path, format="mseed")
            
            # Use obspy's built-in functionality to check for gaps
            st.merge(fill_value='--')
            
            # Calculate total trace duration in seconds
            total_duration_in_seconds = 0
            if len(st) > 0:
                for trace in st:
                    total_duration_in_seconds += trace.stats.npts / trace.stats.sampling_rate

            # Get the total expected duration for a full day
            total_expected_duration = 86400  # 24 hours * 60 minutes * 60 seconds
            
            # Calculate availability percentage
            availability_percentage = (total_duration_in_seconds / total_expected_duration) * 100
            
            # Get the channel code (e.g., SHE.D) from the file name
            channel_id = os.path.basename(os.path.dirname(file_path))
            channel_availability[channel_id] = round(availability_percentage, 2)
            
        except Exception as e:
            print(f"Error processing file {file_path}: {e}")
            continue
            
    return channel_availability

def send_data_to_api(payload):
    """
    Sends the calculated data as a JSON payload to the API.
    """
    headers = {'Content-Type': 'application/json'}

    try:
        response = requests.post(API_URL, data=json.dumps(payload), headers=headers)
        response.raise_for_status()
        print("Data sent successfully!")
        print(f"Server response: {response.status_code}")
        print(response.json())
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Failed to send data to API: {e}")
        return None

# --- Main Execution ---
if __name__ == "__main__":
    # Get yesterday's date to ensure data is complete
    yesterday = datetime.now().date() - timedelta(days=1)
    
    # Create a single list to hold all entries from all stations and channels
    all_data_to_send = []
    
    for station in STATIONS_AND_CHANNELS.keys():
        print(f"Processing station: {station}")
        
        # Get the list of files to process for yesterday
        files_to_process = get_archive_files(station, yesterday)
        
        if files_to_process:
            # Calculate availability from the files
            availability_data = calculate_availability_from_files(files_to_process)
            
            if availability_data:
                # Add each channel's data to the main list
                for channel, percentage in availability_data.items():
                    all_data_to_send.append({
                        "station": station,
                        "channel": channel,
                        "date": yesterday.isoformat(),
                        "percentage": percentage
                    })
        else:
            print(f"No files found for {station} on {yesterday.isoformat()}.")
            
    # Send the combined list of data entries to the API in a single request
    if all_data_to_send:
        send_data_to_api(all_data_to_send)
    else:
        print("No data calculated. Nothing to send.")