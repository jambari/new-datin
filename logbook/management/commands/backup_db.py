import os
import datetime
import subprocess
import glob
from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.mail import EmailMessage

class Command(BaseCommand):
    help = 'Backup DB: Split large files for Telegram, Send Email, & SCP'

    def handle(self, *args, **kwargs):
        # 1. SETUP
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        base_filename = f"backup_datin_{timestamp}"
        sql_filename = f"{base_filename}.sql"
        zip_filename = f"{sql_filename}.gz"
        
        # DB Credentials
        db_conf = settings.DATABASES['default']
        os.environ['PGPASSWORD'] = db_conf['PASSWORD']
        
        self.stdout.write(f"Starting backup for {db_conf['NAME']}...")

        try:
            # 2. DUMP & COMPRESS
            # Dump
            dump_cmd = f"pg_dump -h {db_conf['HOST']} -p {db_conf['PORT']} -U {db_conf['USER']} {db_conf['NAME']} > {sql_filename}"
            subprocess.run(dump_cmd, shell=True, check=True)
            
            # Compress (Gzip level 9 for max compression)
            subprocess.run(f"gzip -9 {sql_filename}", shell=True, check=True)
            
            file_size_mb = os.path.getsize(zip_filename) / (1024 * 1024)
            self.stdout.write(self.style.SUCCESS(f"Backup created: {zip_filename} ({file_size_mb:.2f} MB)"))

            # ---------------------------------------------------------
            # 3. TELEGRAM (AUTO-SPLIT LOGIC)
            # ---------------------------------------------------------
            if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID:
                self.stdout.write("Processing for Telegram...")
                
                # Telegram limit is 50MB. We split if > 45MB just to be safe.
                telegram_files = []
                
                if file_size_mb > 45:
                    self.stdout.write("File > 45MB. Splitting for Telegram...")
                    # Split into 45MB chunks named: backup_xxx.sql.gz.part_aa, ab, etc.
                    split_prefix = f"{zip_filename}.part_"
                    subprocess.run(f"split -b 45M {zip_filename} {split_prefix}", shell=True, check=True)
                    telegram_files = sorted(glob.glob(f"{split_prefix}*"))
                else:
                    telegram_files = [zip_filename]

                # Send each file loop
                for f_path in telegram_files:
                    f_name = os.path.basename(f_path)
                    caption = f"🗄️ Backup Part: {f_name}" if len(telegram_files) > 1 else f"🗄️ Backup Full: {timestamp}"
                    
                    self.stdout.write(f"Sending {f_name}...")
                    
                    curl_cmd = (
                        f'curl -s -F chat_id="{settings.TELEGRAM_CHAT_ID}" '
                        f'-F caption="{caption}" '
                        f'-F document=@"{f_path}" '
                        f'https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendDocument'
                    )
                    subprocess.run(curl_cmd, shell=True)

                # Cleanup split parts
                if len(telegram_files) > 1:
                    for f in telegram_files:
                        os.remove(f)

            # ---------------------------------------------------------
            # 5. SCP (Kirim file UTUH, bukan pecahan)
            # ---------------------------------------------------------
            if hasattr(settings, 'BACKUP_REMOTE_HOST'):
                self.stdout.write("Sending via SCP...")
                # Pastikan folder tujuan sudah ada!
                remote = f"{settings.BACKUP_REMOTE_USER}@{settings.BACKUP_REMOTE_HOST}:{settings.BACKUP_REMOTE_PATH}"
                
                # Tambahkan -o ConnectTimeout=10 agar tidak hang jika server mati
                scp_cmd = f"scp -o ConnectTimeout=10 {zip_filename} {remote}"
                
                ret = subprocess.run(scp_cmd, shell=True)
                if ret.returncode != 0:
                     self.stdout.write(self.style.ERROR("SCP Failed. Check remote folder exists."))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {str(e)}"))
        
        finally:
            # 6. CLEANUP
            if os.path.exists(zip_filename):
                os.remove(zip_filename)
            if os.path.exists(sql_filename):
                os.remove(sql_filename)
            self.stdout.write(self.style.SUCCESS("Process Finished."))