import time
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager
import logging
import os
import csv

# --- Logger Setup ---
log_formatter_file = logging.Formatter('%(asctime)s - %(levelname)s - %(module)s - %(funcName)s - %(lineno)d - %(message)s')
log_formatter_console = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

for handler in logger.handlers[:]:
    logger.removeHandler(handler)

log_file_path = 'bsp_scraping_detailed.log'
if os.path.exists(log_file_path):
    try:
        os.remove(log_file_path)
        print(f"Removed old log file: {log_file_path}")
    except OSError as e:
        print(f"Error removing old log file '{log_file_path}': {e}")

file_handler = logging.FileHandler(log_file_path)
file_handler.setFormatter(log_formatter_file)
file_handler.setLevel(logging.DEBUG)
logger.addHandler(file_handler)

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(log_formatter_console)
stream_handler.setLevel(logging.INFO)
logger.addHandler(stream_handler)

# --- Global Configuration ---
CODE_TO_ID_MAP = {
    "harness": "harness", "greyhounds": "greyhound", "thoroughbred": "thoroughbred",
    "r": "thoroughbred", "g": "greyhound", "h": "harness"
}
MAX_VENUE_FAILURES_PER_DATE = 2 

def setup_driver():
    logger.info("Initializing Chrome WebDriver setup...")
    options = webdriver.ChromeOptions()
    options.add_argument('--start-maximized'); options.add_argument('--log-level=3')
    # options.add_argument('--headless')
    options.add_argument('--disable-gpu'); options.add_argument('--no-sandbox'); options.add_argument('--disable-dev-shm-usage')
    try:
        logger.debug("WebDriverManager: Installing/Locating ChromeDriver...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        logger.info("WebDriver setup successful.")
        return driver
    except Exception as e:
        logger.critical(f"Fatal error during WebDriver setup: {e}", exc_info=True); raise

def select_date_on_calendar(driver, date_wait, target_date_str):
    logger.info(f"Calendar: Selecting date: '{target_date_str}'.")
    try:
        target_date_obj = datetime.strptime(target_date_str.split(' ')[0], "%d/%m/%Y")
        target_day, target_month_name, target_year = str(target_date_obj.day), target_date_obj.strftime("%B"), str(target_date_obj.year)

        logger.debug("Calendar: Clicking icon."); calendar_icon = date_wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "calendar-image"))); calendar_icon.click()
        calendar_widget = date_wait.until(EC.visibility_of_element_located((By.CLASS_NAME, "flatpickr-calendar"))); logger.debug("Calendar: Widget visible.")

        for _ in range(36): 
            cur_month = calendar_widget.find_element(By.CLASS_NAME, "cur-month").text.strip()
            cur_year = calendar_widget.find_element(By.CSS_SELECTOR, ".numInput.cur-year").get_attribute("value")
            logger.debug(f"Calendar: Display: {cur_month} {cur_year}. Target: {target_month_name} {target_year}.")
            if cur_month == target_month_name and cur_year == target_year: logger.debug("Calendar: Correct month/year."); break
            
            nav_button_class = "flatpickr-prev-month" if target_date_obj < datetime.strptime(f"1 {cur_month} {cur_year}", "%d %B %Y") else "flatpickr-next-month"
            logger.debug(f"Calendar: Clicking '{nav_button_class}'."); calendar_widget.find_element(By.CLASS_NAME, nav_button_class).click()
            time.sleep(0.4); calendar_widget = date_wait.until(EC.visibility_of_element_located((By.CLASS_NAME, "flatpickr-calendar")))
        else: logger.error(f"Calendar: Failed to navigate to {target_month_name} {target_year}."); return False

        day_xpath = f"//span[contains(@class, 'flatpickr-day') and not(contains(@class, 'prevMonthDay')) and not(contains(@class, 'nextMonthDay')) and normalize-space()='{target_day}']"
        logger.debug(f"Calendar: Clicking day XPath: {day_xpath}"); date_wait.until(EC.element_to_be_clickable((By.XPATH, day_xpath))).click()
        logger.info(f"Calendar: Day '{target_day}' selected.")
        
        logger.debug("Calendar: Waiting for spinner post-date selection (up to 60s)...")
        try:
            date_wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "img.loading"))); logger.debug("Calendar: Spinner detected. Waiting for invisibility.")
            date_wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, "img.loading"))); logger.info("Calendar: Date selection complete, spinner gone.")
        except TimeoutException: logger.warning("Calendar: Spinner NOT detected or timed out (60s). Proceeding.")
        return True
    except Exception as e: logger.error(f"Calendar: Error selecting date '{target_date_str}': {e}", exc_info=True); return False

def get_input_csv():
    filename = "bet sample.csv"; logger.info(f"CSV: Reading input: '{filename}'")
    if not os.path.exists(filename): logger.critical(f"CSV: File '{filename}' not found."); return None
    data = []
    try:
        with open(filename, mode='r', encoding='utf-8-sig') as infile:
            reader = csv.reader(infile); header = next(reader); logger.debug(f"CSV: Header: {header}")
            try: odds_index = [h.strip().lower() for h in header].index('odds')
            except ValueError: logger.critical("CSV: 'Odds' header not found."); return None
            logger.debug(f"CSV: 'Odds' column at index {odds_index}.")
            for i, row in enumerate(reader):
                if not any(field.strip() for field in row): logger.debug(f"CSV: Skipping blank row #{i+2}."); continue
                if len(row) > len(header):
                    logger.warning(f"CSV: Row #{i+2} has {len(row)} fields (expected {len(header)}). Consolidating 'Odds': {row}")
                    std_fields = row[:odds_index]; combined_odds = ''.join(row[odds_index:])
                    proc_row = std_fields + [combined_odds] + row[odds_index + (len(row)-len(header)+1):]
                    if len(proc_row)!=len(header): logger.error(f"CSV: Bad row #{i+2} after 'Odds' combine. Skipping."); continue
                    data.append(proc_row)
                elif len(row) == len(header): data.append(row)
                else: logger.warning(f"CSV: Malformed row #{i+2} ({len(row)} fields). Skipping: {row}")
        df = pd.DataFrame(data, columns=[h.strip() for h in header]); df.columns = [c.strip().lower() for c in df.columns]
        if 'time' not in df.columns and 'date' in df.columns: logger.debug("CSV: Renaming 'date' to 'time'."); df.rename(columns={'date': 'time'}, inplace=True)
        req_cols = ['time', 'venue', 'code', 'raceno', 'runnerno', 'runnername']
        if any(c not in df.columns for c in req_cols): logger.critical(f"CSV: Missing required columns. Need: {req_cols}"); return None
        logger.info(f"CSV: Loaded {len(df)} tasks from '{filename}'.")
        if df.empty: logger.warning("CSV: Parsed file is empty.")
        return df
    except Exception as e: logger.critical(f"CSV: Error reading/processing '{filename}': {e}", exc_info=True); return None

def _fetch_bsp_for_race_runners(driver, wait, active_meeting_element, raceno_to_find, tasks_for_this_race, venue_name_for_logging):
    processed_tasks = []
    str_raceno = str(raceno_to_find)
    # Console INFO log for each race start
    logger.info(f"Race R{str_raceno} ({venue_name_for_logging}): Processing {len(tasks_for_this_race)} task(s).")
    try:
        tab_xpath = f".//div[contains(@class, 'race-tab') and div[@class='race-number' and normalize-space(text())='{str_raceno}']]"
        logger.debug(f"Race R{str_raceno}: Locating Tab XPath: {tab_xpath}")
        tab = wait.until(EC.element_to_be_clickable(active_meeting_element.find_element(By.XPATH, tab_xpath)))
        if "active-grad" not in tab.get_attribute("class"):
            logger.debug(f"Race R{str_raceno}: Tab not active. Clicking."); driver.execute_script("arguments[0].scrollIntoView({block:'center'});", tab); time.sleep(0.3)
            driver.execute_script("arguments[0].click();", tab); time.sleep(2.0) # Wait for runners
        else: logger.debug(f"Race R{str_raceno}: Tab already active."); time.sleep(0.5)

        runners_xpath = f".//div[@class='races']/div[contains(@class, 'betfair-url') and not(contains(@style,'display: none'))]//div[@class='runners']"
        logger.debug(f"Race R{str_raceno}: Locating runners XPath: {runners_xpath}")
        runners_container = wait.until(EC.visibility_of(active_meeting_element.find_element(By.XPATH, runners_xpath)))

        for _, task in tasks_for_this_race.iterrows():
            task_copy = task.copy(); runner_no, runner_name = str(task['runnerno']), task['runnername']
            log_prefix = f"  Runner {runner_no} ('{runner_name}') in R{str_raceno}:" # Keep this for detailed file log
            logger.debug(f"{log_prefix} Scraping BSP.") # Detailed log
            try:
                runner_row_xpath = f".//div[@class='runner-info' and .//div[@class='number' and normalize-space(text())='{runner_no}']]/ancestor::div[@class='runner']"
                runner_row = runners_container.find_element(By.XPATH, runner_row_xpath)
                win_p = runner_row.find_element(By.CSS_SELECTOR, "div.price.win").text.strip()
                place_p = runner_row.find_element(By.CSS_SELECTOR, "div.price.place").text.strip()
                logger.debug(f"{log_prefix} SUCCESS. BSP Win: '{win_p}', Place: '{place_p}'.")
                task_copy['BSP Price Win'], task_copy['BSP Price Place'] = win_p or "N/A", place_p or "N/A"
            except NoSuchElementException: logger.warning(f"{log_prefix} FAILED. Not found on page."); task_copy['BSP Price Win'], task_copy['BSP Price Place'] = 'Runner Not Found on Page', 'Runner Not Found on Page'
            except StaleElementReferenceException: logger.warning(f"{log_prefix} FAILED. Stale element."); task_copy['BSP Price Win'], task_copy['BSP Price Place'] = 'Stale Element', 'Stale Element'
            except Exception as e: logger.warning(f"{log_prefix} FAILED. Scrape error: {e}", exc_info=False); task_copy['BSP Price Win'], task_copy['BSP Price Place'] = 'Scrape Error', 'Scrape Error'
            finally: processed_tasks.append(task_copy)
        
        # Summary log for the race
        success_count = sum(1 for t in processed_tasks if t.get('BSP Price Win') not in ['Runner Not Found on Page', 'Stale Element', 'Scrape Error', 'Race Timeout', 'Race Element Missing', 'Race Error'])
        if len(tasks_for_this_race) > 0 : # Avoid division by zero if tasks_for_this_race is empty (should not happen with groupby)
            logger.info(f"Race R{str_raceno} ({venue_name_for_logging}): Processed {success_count}/{len(tasks_for_this_race)} tasks successfully.")
        else:
            logger.info(f"Race R{str_raceno} ({venue_name_for_logging}): No tasks to process for this race number in CSV.")


    except Exception as e_race:
        error_type = 'Race Timeout' if isinstance(e_race, TimeoutException) else 'Race Element Missing' if isinstance(e_race, NoSuchElementException) else 'Race Error'
        logger.error(f"Race R{str_raceno} ({venue_name_for_logging}): {error_type.upper()} - {e_race}", exc_info=isinstance(e_race, (TimeoutException, NoSuchElementException)))
        for _, task in tasks_for_this_race.iterrows(): # Mark all tasks for this race with the race-level error
            task_copy = task.copy(); task_copy['BSP Price Win'], task_copy['BSP Price Place'] = error_type, error_type; processed_tasks.append(task_copy)
    
    logger.debug(f"Race R{str_raceno}: Finished. Returning {len(processed_tasks)} tasks.")
    return processed_tasks

def scrape_and_enrich_csv(tasks_df_original): # Renamed to avoid confusion with internal tasks_df
    logger.info("Starting main scraping and enrichment process...")
    driver = setup_driver()
    if not driver: return pd.DataFrame()

    wait = WebDriverWait(driver, 20); date_load_wait = WebDriverWait(driver, 60); wait_short = WebDriverWait(driver, 5)
    base_url = "https://www.betfair.com.au/hub/racing/horse-racing/racing-results/"
    enriched_rows, bad_dates_set = [], set()
    
    # Work on a copy for date processing
    tasks_df = tasks_df_original.copy()

    try: 
        logger.debug("Preprocessing 'time' column for 'date_only'.")
        tasks_df['date_only'] = pd.to_datetime(tasks_df['time'], errors='coerce').dt.strftime('%d/%m/%Y')
        mask_nat = tasks_df['date_only'].isna()
        if mask_nat.any():
            logger.debug(f"{mask_nat.sum()} NaT dates found. Trying alt format '%m/%d/%Y %H:%M'.")
            tasks_df.loc[mask_nat, 'date_only'] = pd.to_datetime(tasks_df.loc[mask_nat, 'time'], format='%m/%d/%Y %H:%M', errors='coerce').dt.strftime('%d/%m/%Y')
        orig_len = len(tasks_df); tasks_df.dropna(subset=['date_only'], inplace=True)
        dropped_by_date_parse = orig_len - len(tasks_df)
        if dropped_by_date_parse > 0: logger.warning(f"Dropped {dropped_by_date_parse} tasks due to unparseable dates.")
        if tasks_df.empty: logger.warning("No tasks left after date parsing."); return pd.DataFrame()
    except Exception as e: logger.critical(f"Date parsing error: {e}. Aborting.", exc_info=True); return pd.DataFrame()
         
    grouped_tasks = tasks_df.groupby(['date_only', 'code', 'venue'], sort=False)
    logger.info(f"Input tasks (after date parse) grouped into {len(grouped_tasks)} [Date, Code, Venue] groups.")
    
    try: 
        logger.info(f"Navigating to base URL: {base_url}"); driver.get(base_url)
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "pb-6"))); logger.info("Page loaded.")
        
        cur_date, cur_code, cur_venue, active_meeting_el = None, None, None, None
        venue_failures_for_current_date = 0 

        for (date_str, csv_code, csv_venue), venue_group_tasks in grouped_tasks:
            logger.info(f"Processing Group: Date='{date_str}', Code='{csv_code.upper()}', Venue='{csv_venue}' ({len(venue_group_tasks)} tasks)")
            
            if date_str in bad_dates_set:
                logger.warning(f"Date {date_str} in bad_dates_set. Skipping {len(venue_group_tasks)} tasks for this group.")
                for _, task_r in venue_group_tasks.iterrows(): task_c = task_r.copy(); task_c['BSP Price Win'],task_c['BSP Price Place'] = 'Date Previously Failed', 'Date Previously Failed'; enriched_rows.append(task_c)
                continue

            if cur_date != date_str:
                logger.info(f"DATE CHANGE: Current='{cur_date or 'None'}', Target='{date_str}'.")
                venue_failures_for_current_date = 0 
                if not select_date_on_calendar(driver, date_load_wait, date_str):
                    logger.error(f"DATE FAILURE: Calendar selection failed for '{date_str}'. Skipping date.")
                    bad_dates_set.add(date_str)
                    for _, task_r in venue_group_tasks.iterrows(): task_c=task_r.copy(); task_c['BSP Price Win'],task_c['BSP Price Place'] = 'Date Selection Error','Date Selection Error'; enriched_rows.append(task_c)
                    cur_date = "Error"; continue
                
                logger.info(f"DATE '{date_str}' selected. Verifying data panel (up to 2 mins)...")
                try:
                    wait.until(EC.presence_of_element_located((By.CLASS_NAME, "filter-panel"))); logger.debug(f"Filter panel present for {date_str}.")
                    date_load_wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.filters-list div.filter:not([style*='display: none'])")))
                    logger.info(f"FILTER LIST POPULATED for {date_str}. Date load OK.")
                    cur_date, cur_code, cur_venue, active_meeting_el = date_str, None, None, None
                except TimeoutException as e_data_load:
                    logger.error(f"DATE DATA LOAD FAILURE for '{date_str}': {e_data_load.msg}. Skipping date.")
                    bad_dates_set.add(date_str)
                    for _, task_r in venue_group_tasks.iterrows(): task_c=task_r.copy(); task_c['BSP Price Win'],task_c['BSP Price Place']='Date Data Not Loaded','Date Data Not Loaded'; enriched_rows.append(task_c)
                    continue
            
            target_web_code_id = CODE_TO_ID_MAP.get(csv_code.lower())
            if not target_web_code_id:
                logger.error(f"CODE UNKNOWN: '{csv_code}' from CSV. Skipping group.");
                for _, task_r in venue_group_tasks.iterrows(): task_c=task_r.copy();task_c['BSP Price Win'],task_c['BSP Price Place']='Unknown Race Code','Unknown Race Code';enriched_rows.append(task_c)
                continue

            if cur_code != target_web_code_id:
                logger.info(f"CODE CHANGE: Current='{cur_code or 'None'}', Target='{target_web_code_id}'.")
                try:
                    code_btn = wait.until(EC.element_to_be_clickable((By.ID, target_web_code_id)))
                    driver.execute_script("arguments[0].scrollIntoView(true);", code_btn); time.sleep(0.5); code_btn.click()
                    wait.until(EC.presence_of_element_located((By.CLASS_NAME, "filter-panel"))); time.sleep(2.0)
                    logger.info(f"CODE SWITCHED to '{target_web_code_id}'.")
                    cur_code, cur_venue, active_meeting_el = target_web_code_id, None, None
                except Exception as e_code: 
                    logger.error(f"CODE CHANGE ERROR for '{target_web_code_id}': {e_code}. Skipping group.");
                    for _, task_r in venue_group_tasks.iterrows(): task_c=task_r.copy();task_c['BSP Price Win'],task_c['BSP Price Place']='Code Selection Error','Code Selection Error';enriched_rows.append(task_c)
                    continue 

            if cur_venue != csv_venue:
                logger.info(f"VENUE CHANGE: Current='{cur_venue or 'None'}', Target='{csv_venue}'.")
                try:
                    css_filters = "div.filters-list div.filter:not([style*='display: none'])"
                    logger.debug(f"VENUE: Locating filters with CSS: {css_filters}")
                    wait.until(EC.visibility_of_any_elements_located((By.CSS_SELECTOR, css_filters)))
                    vis_filters = driver.find_elements(By.CSS_SELECTOR, css_filters)
                    logger.debug(f"VENUE: Found {len(vis_filters)} filters for code '{cur_code}'. Searching for '{csv_venue}'.")
                    
                    venue_clicked = False
                    for filt_el in vis_filters:
                        try: el_text = filt_el.text.strip()
                        except StaleElementReferenceException: logger.debug("VENUE: Filter stale. Skipping."); continue
                        if el_text.lower() == csv_venue.lower():
                            logger.debug(f"VENUE: Found '{el_text}'. Clicking."); driver.execute_script("arguments[0].scrollIntoView({block:'center'});", filt_el); time.sleep(0.5)
                            filt_el.click(); venue_clicked = True; break
                    if not venue_clicked: raise TimeoutException(f"Venue '{csv_venue}' not found in list.")

                    cur_venue, active_meeting_el = csv_venue, None
                    logger.debug(f"VENUE: Waiting for spinner post-click '{csv_venue}'.")
                    try: wait_short.until(EC.visibility_of_element_located((By.CSS_SELECTOR,"img.loading"))); wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR,"img.loading")))
                    except TimeoutException: logger.debug(f"VENUE: Spinner not detected/timed out for '{csv_venue}'.")
                    
                    active_meeting_xpath = "//div[@class='meetings-list']/div[@class='meeting' and not(contains(@style, 'display: none'))]"
                    active_meeting_el = wait.until(EC.visibility_of_element_located((By.XPATH, active_meeting_xpath)))
                    logger.info(f"VENUE SELECTED: '{csv_venue}'.")
                    venue_failures_for_current_date = 0 
                except Exception as e_venue: 
                    logger.error(f"VENUE LOAD/SELECT ERROR for '{csv_venue}' on date '{date_str}': {e_venue}. Marking venue tasks as error.")
                    venue_failures_for_current_date += 1
                    for _, task_r in venue_group_tasks.iterrows(): task_c=task_r.copy();task_c['BSP Price Win'],task_c['BSP Price Place']='Venue Load Error','Venue Load Error';enriched_rows.append(task_c)
                    
                    if venue_failures_for_current_date >= MAX_VENUE_FAILURES_PER_DATE:
                        logger.warning(f"MAX VENUE FAILURES ({venue_failures_for_current_date}) reached for date '{date_str}'. Marking date as bad and skipping future groups for this date.")
                        bad_dates_set.add(date_str)
                    cur_venue, active_meeting_el = "Error", None 
                    continue 

            if not active_meeting_el and cur_venue == csv_venue and cur_venue != "Error":
                logger.debug(f"VENUE: Re-validating for '{csv_venue}'.")
                try: active_meeting_el = wait.until(EC.visibility_of_element_located((By.XPATH, "//div[@class='meetings-list']/div[@class='meeting' and not(contains(@style, 'display: none'))]")))
                except TimeoutException: logger.error(f"VENUE: Failed re-validation for '{csv_venue}'.");
                for _, task_r in venue_group_tasks.iterrows(): task_c=task_r.copy();task_c['BSP Price Win'],task_c['BSP Price Place']='Venue Element Error','Venue Element Error';enriched_rows.append(task_c)
                continue

            if not active_meeting_el:
                logger.error(f"RACE PROCESSING SKIPPED for '{csv_venue}': Active meeting element not available.");
                for _, task_r in venue_group_tasks.iterrows(): 
                    if 'BSP Price Win' not in task_r or pd.isna(task_r['BSP Price Win']): task_c=task_r.copy();task_c['BSP Price Win'],task_c['BSP Price Place']='Venue Data Unavailable','Venue Data Unavailable';enriched_rows.append(task_c)
                    else: enriched_rows.append(task_r.copy()) 
                continue

            races_in_venue = venue_group_tasks.groupby('raceno', sort=False)
            logger.debug(f"Venue '{csv_venue}': Processing {len(races_in_venue)} race number(s).")
            for raceno, race_tasks in races_in_venue:
                processed_race_tasks = _fetch_bsp_for_race_runners(driver, wait, active_meeting_el, raceno, race_tasks, csv_venue)
                enriched_rows.extend(processed_race_tasks)
        
    except Exception as e_main_loop: logger.critical(f"CRITICAL MAIN LOOP ERROR: {e_main_loop}", exc_info=True)
    finally:
        if 'driver' in locals() and driver: logger.info("Closing WebDriver."); driver.quit()
        logger.info("WebDriver closed.")
    
    if not enriched_rows:
        logger.warning("No data was enriched. Returning empty DataFrame.")
        # tasks_df here refers to the one after date parsing, not tasks_df_original
        final_cols = tasks_df.columns.tolist() if tasks_df is not None and not tasks_df.empty else []
        if 'BSP Price Win' not in final_cols: final_cols.append('BSP Price Win')
        if 'BSP Price Place' not in final_cols: final_cols.append('BSP Price Place')
        return pd.DataFrame(columns=final_cols)

    enriched_df = pd.DataFrame(enriched_rows)
    
    # --- SCRAPING SUMMARY ---
    total_input_tasks_processed = len(tasks_df) # Number of tasks after initial date parsing failures
    
    if not enriched_df.empty:
        script_error_values = [
            'Date Selection Error', 'Date Data Not Loaded', 'Unknown Race Code',
            'Code Selection Error', 'Venue Selection Timeout/Error', 'Venue Load Error',
            'Venue Element Error', 'Venue Data Unavailable', 'Group Processing Error',
            'Race Timeout', 'Race Element Missing', 'Race Error',
            'Runner Not Found on Page', 'Stale Element', 'Scrape Error', 
            'Date Previously Failed'
        ]
        failed_scrapes_count = enriched_df['BSP Price Win'].isin(script_error_values).sum()
        successful_scrapes_count = len(enriched_df) - failed_scrapes_count
        
        logger.info("--- SCRAPING SUMMARY ---")
        logger.info(f"Total Input Tasks (after initial date parsing): {total_input_tasks_processed}")
        logger.info(f"  Tasks Processed for BSP: {len(enriched_df)}") 
        logger.info(f"  Successfully Scraped (BSP found or N/A): {successful_scrapes_count}")
        logger.info(f"  Failed to Scrape (Error or Not Found): {failed_scrapes_count}")
        logger.info("-------------------------")
    else: # enriched_df is empty
        logger.info("--- SCRAPING SUMMARY ---")
        logger.info(f"Total Input Tasks (after initial date parsing): {total_input_tasks_processed}")
        logger.info("No data rows were enriched after processing.")
        logger.info("-------------------------")

    logger.info(f"Collected {len(enriched_df)} total rows before final duplicate removal.")
    if not enriched_df.empty:
        initial_row_count = len(enriched_df)
        enriched_df.drop_duplicates(inplace=True) # Keep all original columns for uniqueness check
        rows_dropped = initial_row_count - len(enriched_df)
        if rows_dropped > 0:
            logger.info(f"Removed {rows_dropped} exact duplicate rows from the processed data.")
    
    logger.info(f"Scraping process finished. Returning {len(enriched_df)} unique rows for final formatting.")
    return enriched_df


def format_and_save_data(final_df, original_input_df):
    output_filename = "final_results.csv"
    
    logger.debug(f"Preparing to save data to '{output_filename}'. Ensuring clean save.")
    if os.path.exists(output_filename):
        try:
            os.remove(output_filename)
            logger.info(f"Removed existing output file: '{output_filename}' for fresh save.")
        except OSError as e:
            logger.error(f"Could not remove existing '{output_filename}': {e}. Data might append or save may fail.")

    if final_df.empty:
        logger.warning(f"No data to save. '{output_filename}' will be empty or created with headers only.")
        if original_input_df is not None and not original_input_df.empty:
            empty_cols = []
            col_map = {'time': ('Time', ''), 'venue': ('Venue', ''), 'code': ('Code', ''), 'raceno': ('RaceNo', ''), 'runnerno': ('RunnerNo', ''), 'runnername': ('RunnerName', ''), 'type': ('Type', ''), 'market': ('Market', ''), 'bookie': ('Bookie', ''), 'odds': ('Odds', '')}
            for col_in in original_input_df.columns: # Use original_input_df to get original casing and order
                 orig_case = col_in
                 if col_in.lower() in col_map: mapped_tup = col_map[col_in.lower()]; empty_cols.append((orig_case, mapped_tup[1]))
                 else: empty_cols.append((orig_case, '')) # For any other original columns
            empty_cols.extend([('BSP', 'Price Win'), ('BSP', 'Price Place')])
            try: pd.DataFrame(columns=pd.MultiIndex.from_tuples(empty_cols)).to_csv(output_filename, index=False, encoding='utf-8-sig'); logger.info(f"Saved an empty '{output_filename}' with expected headers.")
            except Exception as e: logger.error(f"Failed to save empty '{output_filename}': {e}", exc_info=True)
        return

    logger.info(f"Formatting {len(final_df)} rows for '{output_filename}'...")
    orig_col_casings = {c.lower(): c for c in original_input_df.columns} # Map lowercase to original case
    
    # Define the mapping for output columns and their MultiIndex structure
    # Keys are lowercase versions of columns expected in final_df OR original_input_df
    col_map_multi = {'time': ('Time', ''), 'venue': ('Venue', ''), 'code': ('Code', ''), 
                     'raceno': ('RaceNo', ''), 'runnerno': ('RunnerNo', ''), 'runnername': ('RunnerName', ''), 
                     'type': ('Type', ''), 'market': ('Market', ''), 'bookie': ('Bookie', ''), 
                     'odds': ('Odds', ''), 'bsp price win': ('BSP', 'Price Win'), 
                     'bsp price place': ('BSP', 'Price Place')}
    
    out_df = pd.DataFrame()
    final_mi_tuples_for_df = [] # Store tuples as they are added to preserve order for MultiIndex

    # Remove internal 'date_only' column if it accidentally propagated
    if 'date_only' in final_df.columns:
        final_df = final_df.drop(columns=['date_only'], errors='ignore')
        logger.debug("Removed internal 'date_only' column before final formatting, if present.")

    # Iterate through original_input_df columns to preserve their order and casing for the output
    for original_col_name in original_input_df.columns:
        original_col_lower = original_col_name.lower()
        if original_col_lower in col_map_multi:
            target_mi_tuple_template = col_map_multi[original_col_lower]
            # For original columns, the first level of MultiIndex should be their original name
            actual_mi_tuple = (original_col_name, target_mi_tuple_template[1]) 
            
            if original_col_name in final_df.columns: # Prefer direct match on original casing
                 out_df[actual_mi_tuple] = final_df[original_col_name]
                 final_mi_tuples_for_df.append(actual_mi_tuple)
            elif original_col_lower in final_df.columns: # Fallback to lowercase if needed
                 out_df[actual_mi_tuple] = final_df[original_col_lower]
                 final_mi_tuples_for_df.append(actual_mi_tuple)
            else:
                 logger.debug(f"Original column '{original_col_name}' not found in processed data. Will be missing or empty.")
                 # Optionally create an empty column to maintain structure:
                 # out_df[actual_mi_tuple] = pd.Series([None] * len(final_df)) 
                 # final_mi_tuples_for_df.append(actual_mi_tuple)
        else: # Column from original_input_df not in our primary map (e.g. extra user columns)
            actual_mi_tuple = (original_col_name, '')
            if original_col_name in final_df.columns:
                out_df[actual_mi_tuple] = final_df[original_col_name]
                final_mi_tuples_for_df.append(actual_mi_tuple)
            else: # Fallback for lowercase for these extra columns too
                if original_col_lower in final_df.columns:
                    out_df[actual_mi_tuple] = final_df[original_col_lower]
                    final_mi_tuples_for_df.append(actual_mi_tuple)
                else:
                    logger.debug(f"Extra original column '{original_col_name}' not found in processed data.")


    # Add BSP columns specifically
    bsp_win_key_lower = 'bsp price win'
    bsp_place_key_lower = 'bsp price place'
    
    if bsp_win_key_lower in final_df.columns:
        bsp_win_tuple = col_map_multi[bsp_win_key_lower]
        out_df[bsp_win_tuple] = final_df[bsp_win_key_lower]
        final_mi_tuples_for_df.append(bsp_win_tuple)
    elif 'BSP Price Win' in final_df.columns: # Check for direct title case assignment
        bsp_win_tuple = col_map_multi[bsp_win_key_lower]
        out_df[bsp_win_tuple] = final_df['BSP Price Win']
        final_mi_tuples_for_df.append(bsp_win_tuple)
    else:
        logger.debug(f"Column for '{bsp_win_key_lower}' not found in final_df.")

    if bsp_place_key_lower in final_df.columns:
        bsp_place_tuple = col_map_multi[bsp_place_key_lower]
        out_df[bsp_place_tuple] = final_df[bsp_place_key_lower]
        final_mi_tuples_for_df.append(bsp_place_tuple)
    elif 'BSP Price Place' in final_df.columns: # Check for direct title case assignment
        bsp_place_tuple = col_map_multi[bsp_place_key_lower]
        out_df[bsp_place_tuple] = final_df['BSP Price Place']
        final_mi_tuples_for_df.append(bsp_place_tuple)
    else:
        logger.debug(f"Column for '{bsp_place_key_lower}' not found in final_df.")
            
    out_df.columns = pd.MultiIndex.from_tuples(final_mi_tuples_for_df) 
    
    # Final reorder based on the explicitly defined preferred_final_order_tuples if needed
    # The current construction already follows original_input_df order then BSP.
    # This ensures the specific BSP multi-index columns are present.
    
    try:
        out_df.to_csv(output_filename, index=False, encoding='utf-8-sig')
        logger.info(f"SUCCESS: Saved {len(out_df)} entries to '{output_filename}'")
        if not out_df.empty: logger.debug(f"\n--- Sample of Final Data (first 5 rows) ---\n{out_df.head().to_string()}")
    except Exception as e: logger.error(f"Failed to save data to '{output_filename}': {e}", exc_info=True)

if __name__ == "__main__":
    logger.info("Script execution started.")
    input_tasks_df = get_input_csv() # This is the original DataFrame
    if input_tasks_df is not None and not input_tasks_df.empty:
        # Pass a copy for scraping, as tasks_df inside scrape_and_enrich_csv might be modified (e.g. date_only col)
        enriched_dataframe = scrape_and_enrich_csv(input_tasks_df.copy()) 
        # Pass the original input_tasks_df for formatting reference
        format_and_save_data(enriched_dataframe, input_tasks_df) 
    elif input_tasks_df is None: logger.critical("Input CSV could not be loaded. Script terminated.")
    else: logger.warning("Input CSV empty. No tasks."); format_and_save_data(pd.DataFrame(), input_tasks_df)
    logger.info("Script execution finished.")