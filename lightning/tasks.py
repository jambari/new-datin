from celery import shared_task
from django.conf import settings
from .models import Strike, DailyStrikeSummary
from django.utils import timezone as django_timezone
import os
import datetime
from datetime import timezone as dt_timezone
import re
import sqlite3
import traceback
import logging
from django.db import transaction
from django.db.models import Count, Q

# Gunakan logger Celery atau Django
logger = logging.getLogger(__name__)

@shared_task(name="lightning.tasks.process_yesterday_nexstorm_file")
def process_yesterday_nexstorm_file():
    """
    Celery task terjadwal untuk memproses file .db3 NexStorm dari HARI KEMARIN.
    Dijalankan setiap hari pukul 00:05.
    """
    
    # --- 1. Tentukan tanggal "Kemarin" dan nama file ---
    # Asumsikan server Celery berjalan di zona waktu lokal (misal WIT)
    try:
        # Dapatkan tanggal 'hari ini' di zona waktu server, lalu kurangi satu hari
        yesterday_local_date = datetime.date.today() - datetime.timedelta(days=1)
        yesterday_date_str_yyyymmdd = yesterday_local_date.strftime('%Y%m%d')
        yesterday_date_str_iso = yesterday_local_date.strftime('%Y-%m-%d') # Untuk log
        
        filename = f"NGXDS_{yesterday_date_str_yyyymmdd}.db3"
        summary_date_obj = yesterday_local_date # Tanggal untuk disimpan di DailyStrikeSummary
        
        logger.info(f"Task started: processing file for 'yesterday' ({yesterday_date_str_iso}) -> {filename}")
        
        db3_directory = os.path.join(settings.BASE_DIR, 'lightning', 'db3')
        file_path = os.path.join(db3_directory, filename)

        if not os.path.exists(file_path):
            logger.error(f'Error: File not found for yesterday: "{file_path}". Task stopping.')
            return f"File not found: {file_path}"
            
    except Exception as e:
        logger.error(f"Error determining yesterday's date or file path: {e}")
        return f"Error in date calculation: {e}"

    # --- 2. Tentukan Filter Koordinat (Sama seperti di management command) ---
    min_lat_filter = -3.014833
    max_lat_filter = -2.014833
    min_lon_filter = 140.204667
    max_lon_filter = 141.204667
    logger.info(f"Using summary coordinate filter: Lat ({min_lat_filter} to {max_lat_filter}), Lon ({min_lon_filter} to {max_lon_filter})")

    # --- 3. Logika Pemrosesan (dari management command) ---
    logger.info(f'Starting processing for: {file_path}')

    strikes_to_insert_buffer = []
    processed_count = 0
    skipped_count = 0
    BATCH_SIZE = 1000

    # Counter untuk agregasi (hanya yang di dalam koordinat)
    file_cg_plus_count_filtered = 0
    file_cg_minus_count_filtered = 0
    file_ic_count_filtered = 0
    file_other_count_filtered = 0
    file_total_count_filtered = 0

    try:
        # Gunakan atomic transaction
        with transaction.atomic():
            conn = sqlite3.connect(file_path, timeout=10.0)
            cursor = conn.cursor()

            # Query SELURUH file (karena file ini spesifik untuk hari itu)
            base_query = "SELECT epoch_ms, latitude, longitude, type FROM NGXLIGHTNING"
            logger.info(f"Executing SQLite query: {base_query}")
            cursor.execute(base_query) # Tidak perlu filter tanggal lagi

            rows_processed_from_db = 0
            while True:
                rows = cursor.fetchmany(BATCH_SIZE * 2)
                if not rows: break
                rows_processed_from_db += len(rows)

                current_read_batch_objects = []
                for row_data in rows:
                    epoch_ms, lat, lon, st_type = row_data
                    if epoch_ms is None or lat is None or lon is None: 
                        skipped_count += 1
                        continue
                        
                    try:
                        epoch_sec = float(epoch_ms) / 1000
                        dt_naive_utc = datetime.datetime.utcfromtimestamp(epoch_sec)
                        strike_dt_aware = dt_naive_utc.replace(tzinfo=dt_timezone.utc)
                        lat_float = float(lat); lon_float = float(lon); type_int = int(st_type) if st_type is not None else None

                        # Tambahkan ke buffer insert
                        current_read_batch_objects.append(Strike(epoch_ms=epoch_ms, timestamp=strike_dt_aware, latitude=lat_float, longitude=lon_float, strike_type=type_int))
                        processed_count += 1

                        # Cek koordinat untuk agregasi
                        is_within_bounds = (
                            min_lat_filter <= lat_float <= max_lat_filter and
                            min_lon_filter <= lon_float <= max_lon_filter
                        )

                        if is_within_bounds:
                            file_total_count_filtered += 1
                            if type_int == 0: file_cg_plus_count_filtered += 1
                            elif type_int == 1: file_cg_minus_count_filtered += 1
                            elif type_int == 2: file_ic_count_filtered += 1
                            else: file_other_count_filtered += 1

                    except (ValueError, TypeError, OverflowError) as e:
                        logger.warning(f"Skipping bad data row. Error: {e}. Data: {row_data}")
                        skipped_count += 1
                        continue

                # Bulk create batch
                if current_read_batch_objects:
                    Strike.objects.bulk_create(current_read_batch_objects, ignore_conflicts=False, batch_size=BATCH_SIZE)
                    strikes_to_insert_buffer = [] # Reset buffer (ini seharusnya di luar loop for row_data)

            # Sisa buffer (jika ada) - Sebenarnya logic buffer bisa disederhanakan
            # Logic di atas sudah memasukkan per `fetchmany` chunk, jadi tidak perlu buffer di luar loop
            
            conn.close()
            logger.info(f"Finished reading/inserting from DB file. Total rows read: {rows_processed_from_db}")

            # --- 4. Update Summary ---
            logger.info(f"Updating summary for local date: {summary_date_obj}...")
            
            summary, created = DailyStrikeSummary.objects.update_or_create(
                summary_date=summary_date_obj,
                defaults={
                    'cg_plus_count': file_cg_plus_count_filtered,
                    'cg_minus_count': file_cg_minus_count_filtered,
                    'ic_count': file_ic_count_filtered,
                    'other_count': file_other_count_filtered,
                    'total_count': file_total_count_filtered,
                }
            )
            action = "Created" if created else "Updated"
            logger.info(f"  {action} summary for {summary_date_obj}: "
                         f"CG+({summary.cg_plus_count}), CG-({summary.cg_minus_count}), "
                         f"IC({summary.ic_count}), Oth({summary.other_count}), Tot({summary.total_count})")
        
        # Selesai atomic transaction
        final_msg = f"Successfully processed {filename}. Rows inserted: {processed_count}, Rows skipped: {skipped_count}."
        logger.info(final_msg)
        return final_msg

    except sqlite3.Error as db_err:
        logger.error(f"Database error accessing {file_path}: {db_err}")
        raise # Re-raise agar Celery menandai task sebagai FAILED
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        traceback.print_exc()
        raise # Re-raise agar Celery menandai task sebagai FAILED