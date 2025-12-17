# magnet/tasks.py
from celery import shared_task
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

# magnet/tasks.py
@shared_task
def fill_external_form(selenium_data):
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    driver = webdriver.Remote(
        command_executor='http://localhost:4444/wd/hub',
        options=chrome_options
    )

    # Set a generous page load timeout
    driver.set_page_load_timeout(30)
    
    try:
        print(f"AUTOMATION DATA RECEIVED: {selenium_data}")
        url = "http://202.90.198.224:8181/absolute/DATA_INPUT.php"
        driver.get(url)
        
        # Fill "Data Pengamat"
        driver.find_element(By.NAME, 'kode_sts').send_keys('JYP')
        driver.find_element(By.ID, 'pengamat').send_keys(selenium_data['pengamat'])
        driver.find_element(By.ID, 'datepicker').send_keys(selenium_data['datepicker'])

        # Fill "Azimuth TT"
        azimuth = selenium_data['azimuth_tt']
        driver.find_element(By.ID, 'ATT_D').send_keys(azimuth['deg'])
        driver.find_element(By.ID, 'ATT_M').send_keys(azimuth['min'])
        driver.find_element(By.ID, 'ATT_S').send_keys(azimuth['sec'])

        # Fill all "Bacaan titik tetap" fields
        cr1 = selenium_data['CR1']
        driver.find_element(By.ID, 'CR1_D').send_keys(cr1['deg'])
        driver.find_element(By.ID, 'CR1_M').send_keys(cr1['min'])
        driver.find_element(By.ID, 'CR1_S').send_keys(cr1['sec'])

        cl1 = selenium_data['CL1']
        driver.find_element(By.ID, 'CL1_D').send_keys(cl1['deg'])
        driver.find_element(By.ID, 'CL1_M').send_keys(cl1['min'])
        driver.find_element(By.ID, 'CL1_S').send_keys(cl1['sec'])

        cr2 = selenium_data['CR2']
        driver.find_element(By.ID, 'CR2_D').send_keys(cr2['deg'])
        driver.find_element(By.ID, 'CR2_M').send_keys(cr2['min'])
        driver.find_element(By.ID, 'CR2_S').send_keys(cr2['sec'])

        cl2 = selenium_data['CL2']
        driver.find_element(By.ID, 'CL2_D').send_keys(cl2['deg'])
        driver.find_element(By.ID, 'CL2_M').send_keys(cl2['min'])
        driver.find_element(By.ID, 'CL2_S').send_keys(cl2['sec'])

        # Fill "Bacaan Deklinasi"
        dek_times = selenium_data['deklinasi_times']
        dek_dms = selenium_data['deklinasi_dms']
        for reading in ['WU', 'ED', 'WD', 'EU']:
            driver.find_element(By.ID, f'{reading}_T').send_keys(dek_times[reading])
            driver.find_element(By.ID, f'{reading}_D').send_keys(dek_dms[reading]['deg'])
            driver.find_element(By.ID, f'{reading}_M').send_keys(dek_dms[reading]['min'])
            driver.find_element(By.ID, f'{reading}_S').send_keys(dek_dms[reading]['sec'])

        # --- ADD THIS SECTION FOR INKLINASI ---
        ink_times = selenium_data['inklinasi_times']
        ink_dms = selenium_data['inklinasi_dms']
        for reading in ['NU', 'SD', 'ND', 'SU']:
            driver.find_element(By.ID, f'{reading}_T').send_keys(ink_times[reading])
            driver.find_element(By.ID, f'{reading}_D').send_keys(ink_dms[reading]['deg'])
            driver.find_element(By.ID, f'{reading}_M').send_keys(ink_dms[reading]['min'])
            driver.find_element(By.ID, f'{reading}_S').send_keys(ink_dms[reading]['sec'])
            
        # --- ADD THIS SECTION FOR PROTON/FTOTAL ---
        # We map the four F-Total readings to the four PPM fields
        ftotals = selenium_data['inklinasi_ftotals']
        driver.find_element(By.ID, 'PPM_1').send_keys(ftotals['NU'])
        driver.find_element(By.ID, 'PPM_2').send_keys(ftotals['SD'])
        driver.find_element(By.ID, 'PPM_3').send_keys(ftotals['ND'])
        driver.find_element(By.ID, 'PPM_4').send_keys(ftotals['SU'])

        # --- NEW ROBUST SUBMIT LOGIC ---
        # Define the submit button selector
        submit_button_selector = (By.CSS_SELECTOR, "button[type='submit']")

        # Take a screenshot to see if the form is filled correctly
        driver.save_screenshot('app/before_submit.png')
        print("Screenshot 'before_submit.png' saved.")

        # Wait up to 10 seconds for the button to be clickable
        wait = WebDriverWait(driver, 10)
        submit_button = wait.until(EC.element_to_be_clickable(submit_button_selector))
        
        # Try a standard click first
        try:
            submit_button.click()
            print("Standard click successful.")
        except Exception as e:
            print(f"Standard click failed: {e}. Trying JavaScript click.")
            # If standard click fails, use a more forceful JavaScript click
            driver.execute_script("arguments[0].click();", submit_button)
            print("JavaScript click successful.")

        time.sleep(3) # Wait for the page to process the submission
        
        # Take a screenshot after submitting to see the result page
        driver.save_screenshot('app/after_submit.png')
        print("Screenshot 'after_submit.png' saved.")
        
        return "Successfully filled and submitted the form."
        
    except Exception as e:
        print(f"SELENIUM ERROR: {e}")
        # Save a screenshot on error
        driver.save_screenshot('app/error.png')
        return f"An error occurred: {e}"
    finally:
        driver.quit()