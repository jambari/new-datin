# monitor/tasks.py
import os
import paramiko
from django.utils import timezone  # Use this instead of datetime.datetime
from datetime import timedelta
from django.conf import settings
from celery import shared_task
from .models import EarthquakeEvent

@shared_task
def export_and_sync_gmt_history():
    # 1. Get data from the last 30 days
    thirty_days_ago = timezone.now() - timedelta(days=30)
    events = EarthquakeEvent.objects.filter(origin_time__gte=thirty_days_ago)

    # 2. Format data for GMT (Lon, Lat, Depth, Mag, etc.)
    # Adjust the string format based on your specific GMT requirements
    lines = []
    for event in events:
        line = f"{event.longitude} {event.latitude} {event.depth} {event.magnitude} {event.event_id}"
        lines.append(line)

    # 3. Save to local temporary file
    local_path = os.path.join(settings.BASE_DIR, 'history_events.gmt')
    with open(local_path, 'w') as f:
        f.write("\n".join(lines))

    # 4. Transfer to remote server via SCP
    remote_host = "36.91.166.188"
    remote_user = "jamz"
    remote_path = "/home/jamz/history_events.gmt"

    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # Note: Using Key-based auth is recommended. 
        # If using password, add password='your_password' to connect()
        ssh.connect(remote_host, username=remote_user)
        
        sftp = ssh.open_sftp()
        sftp.put(local_path, remote_path)
        sftp.close()
        ssh.close()
        
        # Clean up local file after transfer
        os.remove(local_path)
        return f"Successfully synced {len(lines)} events to {remote_host}"
    
    except Exception as e:
        return f"Failed to sync: {str(e)}"