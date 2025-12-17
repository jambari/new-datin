import subprocess
import json
import requests
from datetime import datetime, date, timedelta, timezone

# --- KONFIGURASI ---
STATION_CODE = "DETAILJYP"
API_ENDPOINT = "http://36.91.166.189/api/gempa/create/"
# Ganti dengan path ke perintah yang menghasilkan DataGempa.txt
SEISCOMP_CMD_PATH = "/home/sysop/bin/datagempa" 
# Ganti nama file sementara agar cocok
TMP_FILE_PATH = "/home/sysop/Documents/DataGempa.txt" 

def run_seiscomp_command():
    """Menjalankan perintah SeisComP untuk menghasilkan file data gempa."""
    today = date.today()
    yesterday = today - timedelta(days=1)
    
    start_date = yesterday.strftime("%Y/%m/%d")
    end_date = today.strftime("%Y/%m/%d")
    
    command = [SEISCOMP_CMD_PATH, start_date, end_date]
    
    print(f"Running command: {' '.join(command)}")
    try:
        with open(TMP_FILE_PATH, "w") as f:
            subprocess.run(command, check=True, text=True, stdout=f)
        print(f"Successfully generated data file at {TMP_FILE_PATH}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Error running custom script: {e}")
        return False

def parse_event_file():
    """Membaca file data mentah dan mengubahnya menjadi format JSON yang bersih."""
    events = []
    
    print(f"Reading data from {TMP_FILE_PATH}...")
    try:
        with open(TMP_FILE_PATH, 'r') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: Input file '{TMP_FILE_PATH}' not found.")
        return []

    # Lewati baris header pertama
    for line in lines[1:]:
        try:
            columns = line.split()
            if len(columns) < 11:
                continue

            # Ekstrak data menggunakan indeks yang benar
            origin_date = columns[1]
            origin_time = columns[2]
            magnitudo = float(columns[5])
            latitude = float(columns[6])
            longitude = float(columns[8])
            depth = int(float(columns[10]))
            
            # Gabungkan tanggal dan waktu, buat menjadi timezone-aware (UTC)
            dt_object = datetime.strptime(f"{origin_date} {origin_time}", '%Y-%m-%d %H:%M:%S.%f').replace(tzinfo=timezone.utc)
            
            # Buat source_id unik
            source_id = f"{dt_object.strftime('%Y%m%d%H%M%S')}-{STATION_CODE}"

            event_data = {
                "source_id": source_id,
                "station_code": STATION_CODE,
                "origin_datetime": dt_object.isoformat(),
                "latitude": latitude,
                "longitude": longitude,
                "magnitudo": magnitudo,
                "depth": depth,
                "remark": f"Event from {STATION_CODE} at {origin_date}", # Membuat 'remark' placeholder
                "felt": False,
                "impact": None,
            }
            events.append(event_data)
        except (ValueError, IndexError) as e:
            print(f"Skipping malformed row: {line.strip()} | Error: {e}")

    print(f"Successfully parsed {len(events)} events.")
    return events

def send_to_api(events_data):
    """Mengirimkan data yang sudah diproses ke API Django."""
    if not events_data:
        print("No new events to send.")
        return

    print(f"Sending {len(events_data)} events to API at {API_ENDPOINT}")
    try:
        response = requests.post(API_ENDPOINT, json=events_data, timeout=60)
        response.raise_for_status()
        print("API Response:", response.json())
    except requests.exceptions.RequestException as e:
        print(f"Error sending data to API: {e}")

# Jalankan alur kerja utama
if __name__ == "__main__":
    if run_seiscomp_command():
        parsed_events = parse_event_file()
        send_to_api(parsed_events)
