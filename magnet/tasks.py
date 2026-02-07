# magnet/tasks.py
from celery import shared_task
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time
import os


@shared_task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 10})
def fill_external_form(self, selenium_data):
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")

    service = Service(ChromeDriverManager().install())

    driver = webdriver.Chrome(
        service=service,
        options=chrome_options
    )

    driver.set_page_load_timeout(30)

    # pastikan folder screenshot ada
    os.makedirs("app", exist_ok=True)

    try:
        print(f"AUTOMATION DATA RECEIVED: {selenium_data}")

        url = "http://202.90.198.224:8181/absolute/DATA_INPUT.php"
        driver.get(url)

        wait = WebDriverWait(driver, 20)

        # ======================
        # DATA PENGAMAT
        # ======================
        wait.until(EC.presence_of_element_located((By.NAME, "kode_sts"))).send_keys("JYP")
        driver.find_element(By.ID, "pengamat").send_keys(selenium_data["pengamat"])
        driver.find_element(By.ID, "datepicker").send_keys(selenium_data["datepicker"])

        # ======================
        # AZIMUTH TT
        # ======================
        azimuth = selenium_data["azimuth_tt"]
        driver.find_element(By.ID, "ATT_D").send_keys(azimuth["deg"])
        driver.find_element(By.ID, "ATT_M").send_keys(azimuth["min"])
        driver.find_element(By.ID, "ATT_S").send_keys(azimuth["sec"])

        # ======================
        # BACAAAN TITIK TETAP
        # ======================
        for key in ["CR1", "CL1", "CR2", "CL2"]:
            data = selenium_data[key]
            driver.find_element(By.ID, f"{key}_D").send_keys(data["deg"])
            driver.find_element(By.ID, f"{key}_M").send_keys(data["min"])
            driver.find_element(By.ID, f"{key}_S").send_keys(data["sec"])

        # ======================
        # DEKLINASI
        # ======================
        dek_times = selenium_data["deklinasi_times"]
        dek_dms = selenium_data["deklinasi_dms"]

        for reading in ["WU", "ED", "WD", "EU"]:
            driver.find_element(By.ID, f"{reading}_T").send_keys(dek_times[reading])
            driver.find_element(By.ID, f"{reading}_D").send_keys(dek_dms[reading]["deg"])
            driver.find_element(By.ID, f"{reading}_M").send_keys(dek_dms[reading]["min"])
            driver.find_element(By.ID, f"{reading}_S").send_keys(dek_dms[reading]["sec"])

        # ======================
        # INKLINASI
        # ======================
        ink_times = selenium_data["inklinasi_times"]
        ink_dms = selenium_data["inklinasi_dms"]

        for reading in ["NU", "SD", "ND", "SU"]:
            driver.find_element(By.ID, f"{reading}_T").send_keys(ink_times[reading])
            driver.find_element(By.ID, f"{reading}_D").send_keys(ink_dms[reading]["deg"])
            driver.find_element(By.ID, f"{reading}_M").send_keys(ink_dms[reading]["min"])
            driver.find_element(By.ID, f"{reading}_S").send_keys(ink_dms[reading]["sec"])

        # ======================
        # PROTON / FTOTAL
        # ======================
        ftotals = selenium_data["inklinasi_ftotals"]
        driver.find_element(By.ID, "PPM_1").send_keys(ftotals["NU"])
        driver.find_element(By.ID, "PPM_2").send_keys(ftotals["SD"])
        driver.find_element(By.ID, "PPM_3").send_keys(ftotals["ND"])
        driver.find_element(By.ID, "PPM_4").send_keys(ftotals["SU"])

        # ======================
        # SUBMIT
        # ======================
        driver.save_screenshot("app/before_submit.png")

        submit_btn = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))
        )

        try:
            submit_btn.click()
        except Exception:
            driver.execute_script("arguments[0].click();", submit_btn)

        time.sleep(3)

        driver.save_screenshot("app/after_submit.png")

        return "Successfully filled and submitted the form."

    except Exception as e:
        driver.save_screenshot("app/error.png")
        raise e

    finally:
        driver.quit()
