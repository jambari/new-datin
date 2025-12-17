# lightning/management/commands/process_nexstormdb.py
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from lightning.models import Strike, DailyStrikeSummary
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

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = ('Processes a NexStorm .db3 file, saves strikes, and updates the daily '
            'summary (filtered by default coordinates) using the date derived from the filename.')

    def add_arguments(self, parser):
        parser.add_argument(
            'filename', type=str,
            help='Filename of the .db3 file (e.g., NGXDS_20251001.db3) in lightning/db3/.'
        )
        # Optional date filters remain, they filter which strikes are READ from the file
        parser.add_argument(
            '--start-date', type=str,
            help='Optional start date (YYYY-MM-DD, local time) for filtering strikes *within* the file.'
        )
        parser.add_argument(
            '--end-date', type=str,
            help='Optional end date (YYYY-MM-DD, local time) for filtering strikes *within* the file.'
        )

    def handle(self, *args, **options):
        filename = options['filename']
        start_date_arg = options['start_date']
        end_date_arg = options['end_date']

        db3_directory = os.path.join(settings.BASE_DIR, 'lightning', 'db3')
        file_path = os.path.join(db3_directory, filename)

        if not os.path.exists(file_path):
            raise CommandError(f'Error: File not found at "{file_path}"')

        # --- Define Default Coordinate Boundaries ---
        # (Using the values previously discussed)
        min_lat_filter = -3.014833
        max_lat_filter = -2.014833
        min_lon_filter = 140.204667
        max_lon_filter = 141.204667
        self.stdout.write(f"Using coordinate filter: Lat ({min_lat_filter} to {max_lat_filter}), Lon ({min_lon_filter} to {max_lon_filter}) for summary aggregation.")
        # --- End Coordinate Boundaries ---


        # --- Derive the primary summary date from filename ---
        summary_date_obj = None
        match = re.search(r'NGXDS_(\d{8})\.db3', filename)
        if match:
            date_part_yyyymmdd = match.group(1)
            try:
                summary_date_obj = datetime.datetime.strptime(date_part_yyyymmdd, '%Y%m%d').date()
                self.stdout.write(f'Using summary date {summary_date_obj.strftime("%Y-%m-%d")} derived from filename.')
            except ValueError:
                raise CommandError(f'Error: Could not parse date from filename "{filename}".')
        else:
             raise CommandError(f'Filename "{filename}" does not match pattern NGXDS_YYYYMMDD.db3.')
        # --- End date derivation ---

        # --- Date Validation & Range Calculation for *filtering within file* ---
        start_epoch_ms_filter = None
        end_epoch_ms_filter = None
        wit_offset = datetime.timedelta(hours=9)
        try:
            # Validate optional user-provided filter dates
            if start_date_arg: datetime.datetime.strptime(start_date_arg, '%Y-%m-%d')
            if end_date_arg: datetime.datetime.strptime(end_date_arg, '%Y-%m-%d')
            if start_date_arg and end_date_arg and start_date_arg > end_date_arg:
                 raise CommandError('Error: --start-date cannot be after --end-date.')
            # Calculate epoch filters ONLY if user provided --start-date or --end-date
            if start_date_arg:
                start_date_local = datetime.datetime.strptime(start_date_arg, '%Y-%m-%d').date()
                start_dt_local_naive = datetime.datetime.combine(start_date_local, datetime.time.min)
                start_dt_utc_naive = start_dt_local_naive - wit_offset
                start_epoch_ms_filter = int(start_dt_utc_naive.timestamp() * 1000)
            if end_date_arg:
                end_date_local = datetime.datetime.strptime(end_date_arg, '%Y-%m-%d').date()
                end_dt_exclusive_local_naive = datetime.datetime.combine(end_date_local + datetime.timedelta(days=1), datetime.time.min)
                end_dt_exclusive_utc_naive = end_dt_exclusive_local_naive - wit_offset
                end_epoch_ms_filter = int(end_dt_exclusive_utc_naive.timestamp() * 1000)
        except ValueError:
             raise CommandError('Error: Invalid date format provided via arguments. Please use YYYY-MM-DD.')
        except Exception as e:
            raise CommandError(f'Error calculating date range filters: {e}')
        # --- End Date Calculation ---

        # --- Direct Processing Logic ---
        self.stdout.write(f'Starting DIRECT processing for: {file_path}')
        if start_epoch_ms_filter or end_epoch_ms_filter:
            self.stdout.write(f'Filtering strikes within file between {start_date_arg or "beginning"} and {end_date_arg or "end"} (Local Time).')
        else:
            self.stdout.write('Processing all strikes within the file.')

        strikes_to_insert_buffer = [] # Buffer for bulk insert
        processed_count = 0
        skipped_count = 0
        BATCH_SIZE = 1000

        # --- Counters for aggregation *within coordinates* ---
        file_cg_plus_count_filtered = 0
        file_cg_minus_count_filtered = 0
        file_ic_count_filtered = 0
        file_other_count_filtered = 0
        file_total_count_filtered = 0
        # --- END Counters ---

        try:
            with transaction.atomic():
                conn = sqlite3.connect(file_path, timeout=10.0)
                cursor = conn.cursor()

                # Build SQLite Query with optional epoch filters
                base_query = "SELECT epoch_ms, latitude, longitude, type FROM NGXLIGHTNING"
                filters = []; params = []
                if start_epoch_ms_filter is not None: filters.append("epoch_ms >= ?"); params.append(start_epoch_ms_filter)
                if end_epoch_ms_filter is not None: filters.append("epoch_ms < ?"); params.append(end_epoch_ms_filter)
                query = f"{base_query} WHERE {' AND '.join(filters)} ORDER BY epoch_ms ASC" if filters else f"{base_query} ORDER BY epoch_ms ASC"

                self.stdout.write(f"Executing SQLite query...")
                cursor.execute(query, params)

                rows_processed_from_db = 0
                while True:
                    rows = cursor.fetchmany(BATCH_SIZE * 2)
                    if not rows: break
                    rows_processed_from_db += len(rows)

                    current_read_batch_objects = []
                    for row_data in rows:
                        epoch_ms, lat, lon, st_type = row_data
                        # Basic validation (skip row if essential data missing)
                        if epoch_ms is None or lat is None or lon is None:
                             skipped_count += 1
                             continue

                        try:
                            epoch_sec = float(epoch_ms) / 1000
                            dt_naive_utc = datetime.datetime.utcfromtimestamp(epoch_sec)
                            strike_dt_aware = dt_naive_utc.replace(tzinfo=dt_timezone.utc)
                            lat_float = float(lat); lon_float = float(lon); type_int = int(st_type) if st_type is not None else None

                            # Create Strike object regardless of coordinates for insertion
                            current_read_batch_objects.append(Strike(epoch_ms=epoch_ms, timestamp=strike_dt_aware, latitude=lat_float, longitude=lon_float, strike_type=type_int))
                            processed_count += 1 # Counts successfully processed rows for insertion

                            # --- NEW: Check Coordinates before Aggregating ---
                            is_within_bounds = (
                                min_lat_filter <= lat_float <= max_lat_filter and
                                min_lon_filter <= lon_float <= max_lon_filter
                            )

                            if is_within_bounds:
                                file_total_count_filtered += 1 # Increment total if within bounds
                                if type_int == 0:
                                    file_cg_plus_count_filtered += 1
                                elif type_int == 1:
                                    file_cg_minus_count_filtered += 1
                                elif type_int == 2:
                                    file_ic_count_filtered += 1
                                else: # Includes None and other integers
                                    file_other_count_filtered += 1
                            # --- END Coordinate Check ---

                        except (ValueError, TypeError, OverflowError) as e:
                            logger.warning(f"Skipping bad data. Error: {e}. Data: {row_data}")
                            skipped_count += 1; continue

                    # Bulk create the batch read from DB
                    if current_read_batch_objects:
                        created_objects = Strike.objects.bulk_create(current_read_batch_objects, ignore_conflicts=False, batch_size=BATCH_SIZE)

                conn.close()
                self.stdout.write(f"Finished reading/inserting from DB file. Total rows read matching filter: {rows_processed_from_db}")

                # --- Update Summary using FILTERED counts ---
                self.stdout.write(f"Updating summary for local date: {summary_date_obj} using filtered counts...")

                summary, created = DailyStrikeSummary.objects.update_or_create(
                    summary_date=summary_date_obj,
                    defaults={
                        'cg_plus_count': file_cg_plus_count_filtered,
                        'cg_minus_count': file_cg_minus_count_filtered,
                        'ic_count': file_ic_count_filtered,
                        'other_count': file_other_count_filtered,
                        'total_count': file_total_count_filtered, # Use the filtered total
                    }
                )
                action = "Created" if created else "Updated"
                self.stdout.write(f"  {action} summary for {summary_date_obj}: "
                                 f"CG+({summary.cg_plus_count}), CG-({summary.cg_minus_count}), "
                                 f"IC({summary.ic_count}), Oth({summary.other_count}), Tot({summary.total_count})")
            # End of atomic transaction

            final_msg = f"Successfully processed {filename}. Rows inserted: {processed_count}, Rows skipped: {skipped_count}."
            self.stdout.write(self.style.SUCCESS(final_msg))

        except sqlite3.Error as db_err:
            raise CommandError(f"Database error accessing {file_path}: {db_err}")
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"An unexpected error occurred: {e}"))
            traceback.print_exc(); raise CommandError(f"Stopping due to unexpected error: {e}")
        # --- End Direct Processing ---