
import time
import pandas as pd
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
import logging
import os
import csv

# --- Logger Setup ( 그대로 유지 ) ---
# name is not defined, so let's define it for the logger to work.
name = __name__
log_formatter_file = logging.Formatter('%(asctime)s - %(levelname)s - %(module)s - %(funcName)s - %(lineno)d - %(message)s')
log_formatter_console = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(name)
logger.setLevel(logging.DEBUG)
for handler in logger.handlers[:]: logger.removeHandler(handler)
log_file_path = 'bsp_scraping_detailed.log'
if os.path.exists(log_file_path):
    try: os.remove(log_file_path); print(f"Removed old log file: {log_file_path}")
    except OSError as e: print(f"Error removing old log file '{log_file_path}': {e}")
file_handler = logging.FileHandler(log_file_path); file_handler.setFormatter(log_formatter_file); file_handler.setLevel(logging.DEBUG); logger.addHandler(file_handler)
stream_handler = logging.StreamHandler(); stream_handler.setFormatter(log_formatter_console); stream_handler.setLevel(logging.INFO); logger.addHandler(stream_handler)

# --- Global Configuration ( 그대로 유지 ) ---
CODE_TO_ID_MAP = {
    "harness": "harness", "greyhounds": "greyhound", "thoroughbred": "thoroughbred",
    "r": "thoroughbred", "g": "greyhound", "h": "harness"
}
MAX_VENUE_FAILURES_PER_DATE = 2
def handle_popups(driver):
    """Checks for and closes known popups that can interfere with clicks."""
    logger.debug("Popup Handler: Checking for known popups...")
    try:
        # Check for InMoment feedback survey close button
        close_button_selector = "div#imClose > button"
        close_button = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.CSS_SELECTOR, close_button_selector)))
        logger.info("Popup Handler: Found and closing feedback survey popup.")
        driver.execute_script("arguments[0].click();", close_button); time.sleep(1)
        return True
    except TimeoutException:
        logger.debug("Popup Handler: No specific popups found (or timed out).")
        return False
    except Exception as e:
        logger.warning(f"Popup Handler: Error while trying to close popup: {e}")
        return False # Changed from 'returN' to 'return False' for consistency
# --- setup_driver ( 그대로 유지 ) ---
def setup_driver():
    logger.info("Initializing Chrome WebDriver setup...")
    options = webdriver.ChromeOptions()
    options.add_argument('--start-maximized'); options.add_argument('--log-level=3')
    # options.add_argument('--headless')
    options.add_argument('--disable-gpu'); options.add_argument('--no-sandbox'); options.add_argument('--disable-dev-shm-usage')
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    try:
        logger.debug("WebDriverManager: Installing/Locating ChromeDriver...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        logger.info("WebDriver setup successful.")
        return driver
    except WebDriverException as e:
        logger.critical(f"Fatal WebDriverException during WebDriver setup: {e.msg if hasattr(e, 'msg') else e}", exc_info=False)
        raise
    except Exception as e:
        logger.critical(f"Fatal generic error during WebDriver setup: {e}", exc_info=True); raise

# --- select_date_on_calendar ( 그대로 유지 ) ---
def select_date_on_calendar(driver, date_wait, target_date_str):
    logger.info(f"Calendar: Selecting date: '{target_date_str}'.")
    calendar_interaction_wait = WebDriverWait(driver, 20)
    try:
        target_date_obj = datetime.strptime(target_date_str.split(' ')[0], "%d/%m/%Y")
        target_day, target_month_name, target_year = str(target_date_obj.day), target_date_obj.strftime("%B"), str(target_date_obj.year)
        logger.debug("Calendar: Clicking icon."); calendar_icon = calendar_interaction_wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "calendar-image"))); calendar_icon.click()
        calendar_widget = calendar_interaction_wait.until(EC.visibility_of_element_located((By.CLASS_NAME, "flatpickr-calendar"))); logger.debug("Calendar: Widget visible.")
        for _ in range(36):
            cur_month_element = calendar_widget.find_element(By.CLASS_NAME, "cur-month")
            cur_year_element = calendar_widget.find_element(By.CSS_SELECTOR, ".numInput.cur-year")
            retries = 3
            while retries > 0:
                try:
                    cur_month = cur_month_element.text.strip(); cur_year = cur_year_element.get_attribute("value"); break
                except StaleElementReferenceException:
                    logger.debug("Calendar: Stale element for month/year, retrying..."); time.sleep(0.3)
                    calendar_widget = calendar_interaction_wait.until(EC.visibility_of_element_located((By.CLASS_NAME, "flatpickr-calendar")))
                    cur_month_element = calendar_widget.find_element(By.CLASS_NAME, "cur-month")
                    cur_year_element = calendar_widget.find_element(By.CSS_SELECTOR, ".numInput.cur-year")
                    retries -= 1
                if retries == 0: raise
            logger.debug(f"Calendar: Display: {cur_month} {cur_year}. Target: {target_month_name} {target_year}.")
            if cur_month == target_month_name and cur_year == target_year: logger.debug("Calendar: Correct month/year."); break
            nav_button_class = "flatpickr-prev-month" if target_date_obj < datetime.strptime(f"1 {cur_month} {cur_year}", "%d %B %Y") else "flatpickr-next-month"
            logger.debug(f"Calendar: Clicking '{nav_button_class}'."); calendar_widget.find_element(By.CLASS_NAME, nav_button_class).click()
            time.sleep(0.4); calendar_widget = calendar_interaction_wait.until(EC.visibility_of_element_located((By.CLASS_NAME, "flatpickr-calendar")))
        else: logger.error(f"Calendar: Failed to navigate to {target_month_name} {target_year}."); return False
        day_xpath = f"//span[contains(@class, 'flatpickr-day') and not(contains(@class, 'prevMonthDay')) and not(contains(@class, 'nextMonthDay')) and normalize-space()='{target_day}']"
        logger.debug(f"Calendar: Clicking day XPath: {day_xpath}"); calendar_interaction_wait.until(EC.element_to_be_clickable((By.XPATH, day_xpath))).click()
        logger.info(f"Calendar: Day '{target_day}' selected.")
        logger.debug("Calendar: Waiting for spinner post-day selection (up to 15s)...")
        try:
            calendar_spinner_wait = WebDriverWait(driver, 15)
            spinner_locator = (By.CSS_SELECTOR, "img.loading[style*='display: block'], img.loading:not([style*='display: none'])")
            calendar_spinner_wait.until(EC.visibility_of_element_located(spinner_locator))
            logger.debug("Calendar: Spinner detected. Waiting for invisibility.")
            calendar_spinner_wait.until(EC.invisibility_of_element_located(spinner_locator))
            logger.info("Calendar: Date selection action complete, spinner gone.")
        except TimeoutException: logger.warning("Calendar: Spinner NOT detected or timed out after 15s for day selection. Proceeding, main data load wait will follow.")
        return True
    except Exception as e: logger.error(f"Calendar: Error selecting date '{target_date_str}': {e}", exc_info=True); return False

# --- get_input_csv ( 그대로 유지 ) ---
def get_input_csv():
    filename = "bet sample.csv"; logger.info(f"CSV: Reading input: '{filename}'")
    if not os.path.exists(filename): logger.critical(f"CSV: File '{filename}' not found."); return None
    data = []
    try:
        with open(filename, mode='r', encoding='utf-8-sig') as infile:
            reader = csv.reader(infile); header = [h.strip() for h in next(reader)]; logger.debug(f"CSV: Header: {header}")
            header_lower = [h.lower() for h in header]
            try: odds_index = header_lower.index('odds')
            except ValueError: logger.critical("CSV: 'Odds' header not found."); return None
            logger.debug(f"CSV: 'Odds' column at index {odds_index}.")
            for i, row in enumerate(reader):
                if not any(field.strip() for field in row): logger.debug(f"CSV: Skipping blank row #{i+2}."); continue
                if len(row) > len(header):
                    logger.warning(f"CSV: Row #{i+2} has {len(row)} fields (expected {len(header)}). Consolidating 'Odds' based on index {odds_index}: {row}")
                    num_extra_fields = len(row) - len(header)
                    std_fields_before_odds = row[:odds_index]
                    combined_odds_fields = row[odds_index : odds_index + 1 + num_extra_fields]
                    std_fields_after_odds = row[odds_index + 1 + num_extra_fields:]
                    combined_odds_value = ''.join(combined_odds_fields)
                    processed_row = std_fields_before_odds + [combined_odds_value] + std_fields_after_odds
                    if len(processed_row) == len(header):
                        logger.debug(f"CSV: Row #{i+2} after Odds consolidation: {processed_row}"); data.append(processed_row)
                    else: logger.error(f"CSV: Row #{i+2} after 'Odds' consolidation still mismatched. Expected {len(header)}, got {len(processed_row)}. Original: {row}. Skipping."); continue
                elif len(row) == len(header): data.append(row)
                else:
                    logger.warning(f"CSV: Malformed row #{i+2} ({len(row)} fields, expected {len(header)}). Padding with empty strings. Row: {row}")
                    padded_row = row + [''] * (len(header) - len(row)); data.append(padded_row)
        df = pd.DataFrame(data, columns=header); df.columns = [c.strip().lower() for c in df.columns]
        if 'time' not in df.columns and 'date' in df.columns: logger.debug("CSV: Renaming 'date' to 'time'."); df.rename(columns={'date': 'time'}, inplace=True)
        req_cols = ['time', 'venue', 'code', 'raceno', 'runnerno', 'runnername']
        missing_cols = [c for c in req_cols if c not in df.columns]
        if missing_cols: logger.critical(f"CSV: Missing required columns: {missing_cols}. Found columns: {df.columns.tolist()}"); return None
        logger.info(f"CSV: Loaded {len(df)} tasks from '{filename}'.")
        if df.empty: logger.warning("CSV: Parsed file is empty after processing.")
        return df
    except Exception as e: logger.critical(f"CSV: Error reading/processing '{filename}': {e}", exc_info=True); return None

# --- filter_tasks_for_last_n_days ( 그대로 유지 ) ---
def filter_tasks_for_last_n_days(df_input, days=11):
    if df_input is None or df_input.empty: logger.info("Date Filter: Input DataFrame is empty or None."); return df_input
    logger.info(f"Date Filter: Starting to filter tasks for the last {days} days (today inclusive).")
    df = df_input.copy()
    def robust_to_datetime(time_val):
        if pd.isna(time_val) or str(time_val).strip() == '': return pd.NaT
        for fmt in ('%d/%m/%Y %H:%M', '%m/%d/%Y %H:%M', '%Y-%m-%d %H:%M:%S', '%d/%m/%Y', '%m/%d/%Y', '%Y-%m-%d'):
            try: return pd.to_datetime(time_val, format=fmt, errors='raise')
            except (ValueError, TypeError): continue
        try: return pd.to_datetime(time_val, errors='coerce')
        except Exception: return pd.NaT
    df['temp_parsed_datetime'] = df['time'].apply(robust_to_datetime)
    original_count = len(df); df.dropna(subset=['temp_parsed_datetime'], inplace=True)
    dropped_for_unparseable = original_count - len(df)
    if dropped_for_unparseable > 0: logger.warning(f"Date Filter: Dropped {dropped_for_unparseable} tasks due to unparseable 'time' field.")
    if df.empty:
        logger.warning("Date Filter: DataFrame empty after parsing dates. No tasks to process.")
        if 'temp_parsed_datetime' in df.columns: df = df.drop(columns=['temp_parsed_datetime'])
        return df
    today = datetime.now().date(); cutoff_date = today - timedelta(days=days - 1)
    logger.info(f"Date Filter: Applying date range: >= {cutoff_date.strftime('%d/%m/%Y')} and <= {today.strftime('%d/%m/%Y')}.")
    tasks_before_range_filter = len(df)
    df_filtered = df[(df['temp_parsed_datetime'].dt.date >= cutoff_date) & (df['temp_parsed_datetime'].dt.date <= today)].copy()
    tasks_after_filter = len(df_filtered); tasks_dropped_by_range = tasks_before_range_filter - tasks_after_filter
    if tasks_dropped_by_range > 0: logger.info(f"Date Filter: {tasks_dropped_by_range} tasks were outside the {days}-day window and removed.")
    logger.info(f"Date Filter: {tasks_after_filter} tasks remain after date range filtering.")
    df_filtered.drop(columns=['temp_parsed_datetime'], inplace=True, errors='ignore')
    return df_filtered

# --- _fetch_bsp_for_race_runners ( 그대로 유지 ) ---
def _fetch_bsp_for_race_runners(driver, wait, active_meeting_element_initial_ref, raceno_to_find, tasks_for_this_race_df, venue_name_for_logging):
    processed_tasks_list = []
    str_raceno = str(raceno_to_find)
    logger.info(f"Race R{str_raceno} ({venue_name_for_logging}): Processing {len(tasks_for_this_race_df)} task(s).")
    if tasks_for_this_race_df.empty:
        logger.warning(f"Race R{str_raceno} ({venue_name_for_logging}): No tasks provided. Skipping."); return []
    active_meeting_element = active_meeting_element_initial_ref
    try:
        try:
            active_meeting_element = driver.find_element(By.XPATH, "//div[@class='meetings-list']/div[@class='meeting' and not(contains(@style, 'display: none'))]")
        except NoSuchElementException:
            logger.error(f"Race R{str_raceno} ({venue_name_for_logging}): Active meeting element lost. Marking tasks as error.")
            error_type = 'Venue Element Error Mid-Race'
            for _, task_series in tasks_for_this_race_df.iterrows():
                task_copy = task_series.copy(); task_copy['BSP Price Win'], task_copy['BSP Price Place'] = error_type, error_type; processed_tasks_list.append(task_copy)
            return processed_tasks_list

        tab_xpath = f".//div[contains(@class, 'race-tab') and div[@class='race-number' and normalize-space(text())='{str_raceno}']]"
        logger.debug(f"Race R{str_raceno}: Locating Tab XPath: {tab_xpath} within active meeting.")
        tab_element = wait.until(EC.element_to_be_clickable(active_meeting_element.find_element(By.XPATH, tab_xpath)))

        if "active-grad" not in tab_element.get_attribute("class"):
            logger.debug(f"Race R{str_raceno}: Tab not active. Clicking.")
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", tab_element); time.sleep(0.3)
            driver.execute_script("arguments[0].click();", tab_element)
            runners_loaded_xpath = f".//div[@class='races']/div[contains(@class, 'betfair-url') and not(contains(@style,'display: none'))]//div[@class='runners']/div[@class='runner']"
            try:
                WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, runners_loaded_xpath)))
                logger.debug(f"Race R{str_raceno}: Runners appear to be loaded for the new tab.")
            except TimeoutException:
                logger.warning(f"Race R{str_raceno}: Timeout (20s) waiting for runners to load after tab click. Content might be missing/slow.")
            time.sleep(1.0)
        else: logger.debug(f"Race R{str_raceno}: Tab already active."); time.sleep(0.5)

        runners_container_xpath = f".//div[@class='races']/div[contains(@class, 'betfair-url') and not(contains(@style,'display: none'))]//div[@class='runners']"
        logger.debug(f"Race R{str_raceno}: Locating runners container XPath: {runners_container_xpath}")
        runners_container = wait.until(EC.visibility_of(active_meeting_element.find_element(By.XPATH, runners_container_xpath)))

        for _, task_series in tasks_for_this_race_df.iterrows():
            task_copy = task_series.copy()
            runner_no_str, runner_name_str = str(task_copy['runnerno']), task_copy['runnername']
            log_prefix = f"  Runner {runner_no_str} ('{runner_name_str}') in R{str_raceno} ({venue_name_for_logging}):"
            logger.debug(f"{log_prefix} Scraping BSP.")
            try:
                runner_row_xpath = f".//div[@class='runner-info' and .//div[@class='number' and normalize-space(text())='{runner_no_str}']]/ancestor::div[@class='runner']"
                runner_row_element = runners_container.find_element(By.XPATH, runner_row_xpath)
                win_price_text = runner_row_element.find_element(By.CSS_SELECTOR, "div.price.win").text.strip()
                place_price_text = runner_row_element.find_element(By.CSS_SELECTOR, "div.price.place").text.strip()
                logger.debug(f"{log_prefix} SUCCESS. BSP Win: '{win_price_text}', Place: '{place_price_text}'.")
                task_copy['BSP Price Win'], task_copy['BSP Price Place'] = win_price_text or "N/A", place_price_text or "N/A"
            except NoSuchElementException: logger.warning(f"{log_prefix} FAILED. Runner not found."); task_copy['BSP Price Win'], task_copy['BSP Price Place'] = 'Runner Not Found on Page', 'Runner Not Found on Page'
            except StaleElementReferenceException: logger.warning(f"{log_prefix} FAILED. Stale element."); task_copy['BSP Price Win'], task_copy['BSP Price Place'] = 'Stale Element', 'Stale Element'
            except Exception as e_runner_scrape: logger.warning(f"{log_prefix} FAILED. Scrape error: {e_runner_scrape}", exc_info=False); task_copy['BSP Price Win'], task_copy['BSP Price Place'] = 'Scrape Error', 'Scrape Error'
            finally: processed_tasks_list.append(task_copy)

        num_input_tasks_for_race = len(tasks_for_this_race_df)
        successful_scrapes_in_race = sum(1 for t_item in processed_tasks_list if t_item.get('BSP Price Win') not in ['Runner Not Found on Page', 'Stale Element', 'Scrape Error', 'Race Timeout', 'Race Element Missing', 'Race Stale Element', 'Race Error', 'Venue Element Error Mid-Race'])
        logger.info(f"Race R{str_raceno} ({venue_name_for_logging}): Processed {successful_scrapes_in_race}/{num_input_tasks_for_race} tasks for BSP.")
        if len(processed_tasks_list) != num_input_tasks_for_race: logger.warning(f"Race R{str_raceno}: Mismatch! Processed {len(processed_tasks_list)} results for {num_input_tasks_for_race} tasks.")
    except Exception as e_race_level:
        error_label = 'Race Timeout' if isinstance(e_race_level, TimeoutException) else 'Race Element Missing' if isinstance(e_race_level, NoSuchElementException) else 'Race Stale Element' if isinstance(e_race_level, StaleElementReferenceException) else 'Race Error'
        logger.error(f"Race R{str_raceno} ({venue_name_for_logging}): {error_label.upper()} at race level. Details: {e_race_level}", exc_info=True)
        processed_tasks_list = []
        for _, task_series in tasks_for_this_race_df.iterrows():
            task_copy = task_series.copy(); task_copy['BSP Price Win'] = error_label; task_copy['BSP Price Place'] = error_label; processed_tasks_list.append(task_copy)
    logger.debug(f"Race R{str_raceno}: Finished BSP fetch. Returning {len(processed_tasks_list)} task results.")
    return processed_tasks_list

# --- _find_and_click_venue ( 그대로 유지 ) ---
def _find_and_click_venue(driver, wait, csv_venue_group, current_phase_name, fuzzy_venue_matching_enabled=False):
    """
    Finds and clicks a venue filter button on the page.
    It first attempts an exact match. If that fails and fuzzy matching is enabled,
    it will attempt to find a single, unambiguous partial match.
    """
    venue_filters_css = "div.filters-list div.filter:not([style*='display: none'])"
    try:
        wait.until(EC.visibility_of_any_elements_located((By.CSS_SELECTOR, venue_filters_css)))
        visible_venue_filters = driver.find_elements(By.CSS_SELECTOR, venue_filters_css)
        logger.debug(f"[{current_phase_name}] Found {len(visible_venue_filters)} venue filters. Searching for '{csv_venue_group}'.")
    except TimeoutException:
        logger.error(f"[{current_phase_name}] Timed out waiting for any venue filters to become visible.")
        return False # No filters are even visible, cannot proceed.

    # Pass 1: Attempt Exact Match
    for venue_filter_el in visible_venue_filters:
        try:
            el_text = venue_filter_el.text.strip()
            if el_text.lower() == csv_venue_group.lower():
                logger.debug(f"[{current_phase_name}] Exact venue match for '{el_text}' found. Clicking.")
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", venue_filter_el)
                time.sleep(0.5)
                venue_filter_el.click()
                return True # Success
        except StaleElementReferenceException:
            logger.warning(f"[{current_phase_name}] StaleElement during exact venue search. Re-querying and continuing.")
            # Re-fetch elements and restart this loop pass
            visible_venue_filters = driver.find_elements(By.CSS_SELECTOR, venue_filters_css)
            continue

    # Pass 2: Attempt Fuzzy Match (only if enabled and exact match failed)
    if fuzzy_venue_matching_enabled:
        logger.info(f"[{current_phase_name}] Exact venue '{csv_venue_group}' not found. Attempting fuzzy match.")
        potential_fuzzy_matches = []
        csv_venue_lower = csv_venue_group.lower()

        # Re-fetch elements to be safe
        visible_venue_filters = driver.find_elements(By.CSS_SELECTOR, venue_filters_css)
        for venue_filter_el in visible_venue_filters:
            try:
                web_venue_name = venue_filter_el.text.strip()
                web_venue_lower = web_venue_name.lower()
                # Check if one name is a substring of the other
                if csv_venue_lower in web_venue_lower or web_venue_lower in csv_venue_lower:
                    potential_fuzzy_matches.append((web_venue_name, venue_filter_el))
            except StaleElementReferenceException:
                logger.warning(f"[{current_phase_name}] StaleElement during fuzzy venue search. Skipping one element.")
                continue

        if len(potential_fuzzy_matches) == 1:
            matched_name, matched_element = potential_fuzzy_matches[0]
            logger.warning(f"[{current_phase_name}] Found unique fuzzy match for '{csv_venue_group}': '{matched_name}'. Using it.")
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", matched_element)
            time.sleep(0.5)
            matched_element.click()
            return True # Success
        elif len(potential_fuzzy_matches) > 1:
            found_names = [name for name, _ in potential_fuzzy_matches]
            logger.error(f"[{current_phase_name}] AMBIGUOUS fuzzy match for '{csv_venue_group}'. Found: {found_names}. Skipping venue.")
            return False # Failure due to ambiguity
        else:
            logger.error(f"[{current_phase_name}] No exact or fuzzy match found for '{csv_venue_group}'.")
            return False # Failure, no match found

    # If we are here, it means exact match failed and fuzzy was not enabled or also failed.
    logger.error(f"[{current_phase_name}] Venue '{csv_venue_group}' NOT FOUND (Exact match failed, fuzzy matching disabled/failed).")
    return False

# --- scrape_and_enrich_csv [MODIFIED] ---
def scrape_and_enrich_csv(tasks_df_input, current_phase_name="Phase Default", fuzzy_venue_matching=False):
    logger.info(f"[{current_phase_name}] Starting scraping process for {len(tasks_df_input)} tasks... (Fuzzy Venue Matching: {fuzzy_venue_matching})")
    if tasks_df_input.empty: logger.warning(f"[{current_phase_name}] Input DataFrame is empty."); return pd.DataFrame(), pd.DataFrame()
    driver = None
    try: driver = setup_driver()
    except Exception as e_driver_setup:
        logger.critical(f"[{current_phase_name}] WebDriver setup failed: {e_driver_setup}. Phase cannot proceed.")
        error_marked_tasks_df = tasks_df_input.copy()
        error_marked_tasks_df['BSP Price Win'] = 'Driver Setup Error Phase'; error_marked_tasks_df['BSP Price Place'] = 'Driver Setup Error Phase'
        return error_marked_tasks_df, pd.DataFrame()
    wait = WebDriverWait(driver, 20); date_load_wait = WebDriverWait(driver, 120); wait_short = WebDriverWait(driver, 10)
    base_url = "https://www.betfair.com.au/hub/racing/horse-racing/racing-results/"
    enriched_rows_collector_list = []; tasks_for_next_phase_collector_list = []; bad_dates_set_this_phase = set()
    tasks_df_processed_in_phase = tasks_df_input.copy()
    try:
        logger.debug(f"[{current_phase_name}] Preprocessing 'time' for 'date_only' grouping.")
        def get_date_only_str_internal(time_val):
            if pd.isna(time_val) or str(time_val).strip() == '': return None
            for fmt in ('%d/%m/%Y %H:%M', '%m/%d/%Y %H:%M', '%d/%m/%Y', '%m/%d/%Y', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
                try: return pd.to_datetime(time_val, format=fmt).strftime('%d/%m/%Y')
                except (ValueError, TypeError): continue
            dt_obj = pd.to_datetime(time_val, errors='coerce'); return dt_obj.strftime('%d/%m/%Y') if pd.notna(dt_obj) else None
        tasks_df_processed_in_phase['date_only'] = tasks_df_processed_in_phase['time'].apply(get_date_only_str_internal)
        original_len_before_date_parse_drop = len(tasks_df_processed_in_phase)
        tasks_df_processed_in_phase.dropna(subset=['date_only'], inplace=True)
        dropped_count = original_len_before_date_parse_drop - len(tasks_df_processed_in_phase)
        if dropped_count > 0: logger.warning(f"[{current_phase_name}] Dropped {dropped_count} tasks due to unparseable 'time' for 'date_only'.")
        if tasks_df_processed_in_phase.empty:
            logger.warning(f"[{current_phase_name}] No tasks after 'date_only' parsing. Phase ends.");
            if driver: driver.quit(); return pd.DataFrame(), pd.DataFrame()
    except Exception as e_date_parse:
        logger.critical(f"[{current_phase_name}] Error during 'date_only' preprocessing: {e_date_parse}. Aborting phase.", exc_info=True)
        error_marked_tasks_df = tasks_df_input.copy(); error_marked_tasks_df['BSP Price Win'] = 'Date Parse Error For Grouping'; error_marked_tasks_df['BSP Price Place'] = 'Date Parse Error For Grouping'
        if driver: driver.quit(); return error_marked_tasks_df, pd.DataFrame()

    grouped_tasks_iter = tasks_df_processed_in_phase.groupby(['date_only', 'code', 'venue'], sort=False)
    logger.info(f"[{current_phase_name}] Tasks grouped into {len(grouped_tasks_iter)} [Date, Code, Venue] groups.")

    try:
        logger.info(f"[{current_phase_name}] Navigating to base URL: {base_url}"); driver.get(base_url)
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "pb-6"))); logger.info(f"[{current_phase_name}] Page loaded: {base_url}")
        cur_date_on_page, cur_code_on_page, cur_venue_on_page = None, None, None; active_meeting_el_on_page = None; venue_failures_on_current_date_count = 0

        for (date_str_group, csv_code_group, csv_venue_group), venue_group_tasks_df in grouped_tasks_iter:
            logger.info(f"[{current_phase_name}] Group: Date='{date_str_group}', Code='{csv_code_group.upper()}', Venue='{csv_venue_group}' ({len(venue_group_tasks_df)} tasks)")
            if date_str_group in bad_dates_set_this_phase:
                logger.warning(f"[{current_phase_name}] Date {date_str_group} previously failed. Skipping group.")
                for _, task_series in venue_group_tasks_df.iterrows(): task_copy = task_series.copy(); task_copy['BSP Price Win'], task_copy['BSP Price Place'] = 'Date Previously Failed This Phase', 'Date Previously Failed This Phase'; enriched_rows_collector_list.append(task_copy)
                continue

            if cur_date_on_page != date_str_group:
                logger.info(f"[{current_phase_name}] DATE CHANGE: Page='{cur_date_on_page or 'None'}', Target='{date_str_group}'."); venue_failures_on_current_date_count = 0
                if not select_date_on_calendar(driver, date_load_wait, date_str_group):
                    logger.error(f"[{current_phase_name}] DATE FAILURE for '{date_str_group}'."); bad_dates_set_this_phase.add(date_str_group)
                    for _, task_series in venue_group_tasks_df.iterrows(): task_copy = task_series.copy(); task_copy['BSP Price Win'],task_copy['BSP Price Place'] = 'Date Selection Error','Date Selection Error'; enriched_rows_collector_list.append(task_copy)
                    cur_date_on_page = "Error_Date_Selection"; cur_code_on_page = None; cur_venue_on_page = None; active_meeting_el_on_page = None; continue

                # *** MODIFICATION: Call the popup handler after a date change action ***
                handle_popups(driver)

                logger.info(f"[{current_phase_name}] DATE '{date_str_group}' selected. Verifying data panel (up to {date_load_wait._timeout}s)...")
                try:
                    wait.until(EC.presence_of_element_located((By.CLASS_NAME, "filter-panel"))); date_load_wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.filters-list div.filter:not([style*='display: none'])")))
                    logger.info(f"[{current_phase_name}] FILTER LIST POPULATED for '{date_str_group}'. OK.")
                    cur_date_on_page = date_str_group; cur_code_on_page = None; cur_venue_on_page = None; active_meeting_el_on_page = None;
                except TimeoutException as e_data_load_timeout:
                    error_label_for_date_load = 'Date Data Not Loaded'; logger.error(f"[{current_phase_name}] {error_label_for_date_load.upper()} for '{date_str_group}': {e_data_load_timeout.msg}. Collecting for retry.")
                    bad_dates_set_this_phase.add(date_str_group)
                    for _, task_series in venue_group_tasks_df.iterrows():
                        task_copy_for_error = task_series.copy(); task_copy_for_error['BSP Price Win'], task_copy_for_error['BSP Price Place'] = error_label_for_date_load, error_label_for_date_load; enriched_rows_collector_list.append(task_copy_for_error)
                        tasks_for_next_phase_collector_list.append(task_series.copy())
                    cur_date_on_page = "Error_Date_Load"; cur_code_on_page = None; cur_venue_on_page = None; active_meeting_el_on_page = None; continue

            target_web_code_id_str = CODE_TO_ID_MAP.get(csv_code_group.lower())
            if not target_web_code_id_str:
                logger.error(f"[{current_phase_name}] CODE UNKNOWN: '{csv_code_group}'. Skipping.");
                for _, task_series in venue_group_tasks_df.iterrows(): task_copy = task_series.copy(); task_copy['BSP Price Win'],task_copy['BSP Price Place']='Unknown Race Code','Unknown Race Code'; enriched_rows_collector_list.append(task_copy)
                continue

            if cur_code_on_page != target_web_code_id_str:
                logger.info(f"[{current_phase_name}] CODE CHANGE: Page='{cur_code_on_page or 'None'}', Target='{target_web_code_id_str}'.")
                try:
                    code_button_el = wait.until(EC.element_to_be_clickable((By.ID, target_web_code_id_str)))
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", code_button_el); time.sleep(0.3)
                    driver.execute_script("arguments[0].click();", code_button_el); logger.debug(f"[{current_phase_name}] Code button '{target_web_code_id_str}' clicked.")
                    try: spinner_locator = (By.CSS_SELECTOR, "img.loading[style*='display: block'], img.loading:not([style*='display: none'])"); wait_short.until(EC.visibility_of_element_located(spinner_locator)); wait.until(EC.invisibility_of_element_located(spinner_locator))
                    except TimeoutException: logger.debug(f"[{current_phase_name}] Spinner not detected/timed out for code change.")
                    wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.filters-list div.filter:not([style*='display: none'])"))); logger.info(f"[{current_phase_name}] CODE SWITCHED to '{target_web_code_id_str}'.")
                    cur_code_on_page = target_web_code_id_str; cur_venue_on_page = None; active_meeting_el_on_page = None;
                except Exception as e_code_change:
                    logger.error(f"[{current_phase_name}] CODE CHANGE ERROR for '{target_web_code_id_str}': {e_code_change}. Skipping.", exc_info=True);
                    for _, task_series in venue_group_tasks_df.iterrows(): task_copy = task_series.copy(); task_copy['BSP Price Win'],task_copy['BSP Price Place']='Code Selection Error','Code Selection Error'; enriched_rows_collector_list.append(task_copy)
                    cur_code_on_page = "Error_Code_Change"; continue

            if cur_venue_on_page != csv_venue_group or active_meeting_el_on_page is None:
                logger.info(f"[{current_phase_name}] VENUE CHANGE/VALIDATION: Page='{cur_venue_on_page or 'None'}', Target='{csv_venue_group}'.")
                try:
                    venue_found_and_clicked = _find_and_click_venue(driver, wait, csv_venue_group, current_phase_name, fuzzy_venue_matching)
                    if not venue_found_and_clicked:
                        raise TimeoutException(f"Venue '{csv_venue_group}' could not be found or clicked.")

                    try: spinner_locator = (By.CSS_SELECTOR, "img.loading[style*='display: block'], img.loading:not([style*='display: none'])"); wait_short.until(EC.visibility_of_element_located(spinner_locator)); wait.until(EC.invisibility_of_element_located(spinner_locator))
                    except TimeoutException: logger.debug(f"[{current_phase_name}] Spinner not detected/timed out for venue '{csv_venue_group}'.")

                    active_meeting_xpath_str = "//div[@class='meetings-list']/div[@class='meeting' and not(contains(@style, 'display: none'))]"
                    active_meeting_el_on_page = wait.until(EC.visibility_of_element_located((By.XPATH, active_meeting_xpath_str))); wait.until(EC.presence_of_all_elements_located((By.XPATH, f"{active_meeting_xpath_str}//div[contains(@class, 'race-tab')]")))
                    logger.info(f"[{current_phase_name}] VENUE SELECTED: '{csv_venue_group}'."); cur_venue_on_page = csv_venue_group; venue_failures_on_current_date_count = 0

                except Exception as e_venue_select:
                    error_msg_type = "Ambiguous Fuzzy Match" if "AMBIGUOUS" in str(e_venue_select) else "Venue Load Error"
                    logger.error(f"[{current_phase_name}] VENUE ERROR for '{csv_venue_group}': {error_msg_type}. Marking tasks.", exc_info=False)
                    venue_failures_on_current_date_count += 1
                    for _, task_series in venue_group_tasks_df.iterrows():
                        task_copy = task_series.copy()
                        task_copy['BSP Price Win'],task_copy['BSP Price Place'] = error_msg_type, error_msg_type
                        enriched_rows_collector_list.append(task_copy)
                        if error_msg_type == "Venue Load Error":
                           tasks_for_next_phase_collector_list.append(task_series.copy())

                    if venue_failures_on_current_date_count >= MAX_VENUE_FAILURES_PER_DATE: logger.warning(f"[{current_phase_name}] MAX VENUE FAILURES ({venue_failures_on_current_date_count}) for date '{date_str_group}'. Marking date bad."); bad_dates_set_this_phase.add(date_str_group)
                    cur_venue_on_page, active_meeting_el_on_page = "Error_Venue_Load", None; continue

            if not active_meeting_el_on_page:
                logger.error(f"[{current_phase_name}] Race processing skipped for '{csv_venue_group}': Active meeting element unavailable."); error_label = 'Venue Data Unavailable'
                for _, task_series in venue_group_tasks_df.iterrows():
                    already_marked = any(all(er.get(k) == task_series.get(k) for k in ['time', 'venue', 'raceno', 'runnerno'] if k in task_series and k in er) and er.get('BSP Price Win') == 'Venue Load Error' for er in enriched_rows_collector_list if isinstance(er, pd.Series))
                    if not already_marked: task_copy = task_series.copy(); task_copy['BSP Price Win'],task_copy['BSP Price Place']=error_label,error_label; enriched_rows_collector_list.append(task_copy)
                continue

            races_in_group_iter = venue_group_tasks_df.groupby('raceno', sort=False)
            logger.debug(f"[{current_phase_name}] Venue '{csv_venue_group}': Processing {len(races_in_group_iter)} race number(s).")
            for raceno_val, race_tasks_for_raceno_df in races_in_group_iter:
                processed_race_task_series_list = _fetch_bsp_for_race_runners(driver, wait, active_meeting_el_on_page, raceno_val, race_tasks_for_raceno_df, csv_venue_group)
                enriched_rows_collector_list.extend(processed_race_task_series_list)
    except WebDriverException as e_webdriver_main_loop:
        logger.critical(f"[{current_phase_name}] CRITICAL WebDriverException in main loop: {e_webdriver_main_loop.msg if hasattr(e_webdriver_main_loop, 'msg') else e_webdriver_main_loop}. Aborting phase.", exc_info=True)
    except Exception as e_main_loop_other: logger.critical(f"[{current_phase_name}] CRITICAL UNHANDLED ERROR in main loop: {e_main_loop_other}", exc_info=True)
    finally:
        if driver: logger.info(f"[{current_phase_name}] Closing WebDriver session."); driver.quit(); logger.info(f"[{current_phase_name}] WebDriver session closed.")
        enriched_df_this_phase = pd.DataFrame()
        if enriched_rows_collector_list:
            enriched_df_this_phase = pd.DataFrame(enriched_rows_collector_list)
            expected_cols_schema = tasks_df_input.columns.tolist() + ['BSP Price Win', 'BSP Price Place']
            if 'date_only' in expected_cols_schema: expected_cols_schema.remove('date_only')
            for col_name in expected_cols_schema:
                if col_name not in enriched_df_this_phase.columns: enriched_df_this_phase[col_name] = pd.NA
            final_cols_for_enriched_df = [c for c in expected_cols_schema if c in enriched_df_this_phase.columns]
            enriched_df_this_phase = enriched_df_this_phase[final_cols_for_enriched_df]

        retry_df_for_next_phase = pd.DataFrame()
        if tasks_for_next_phase_collector_list:
            retry_df_for_next_phase = pd.DataFrame(tasks_for_next_phase_collector_list)
            id_cols_from_original_input = [col for col in tasks_df_input.columns if col in retry_df_for_next_phase.columns and col.lower() not in ['bsp price win', 'bsp price place', 'date_only']]
            if id_cols_from_original_input and not retry_df_for_next_phase.empty: retry_df_for_next_phase.drop_duplicates(subset=id_cols_from_original_input, keep='first', inplace=True)
            if 'date_only' in retry_df_for_next_phase.columns: retry_df_for_next_phase = retry_df_for_next_phase.drop(columns=['date_only'], errors='ignore')

        logger.info(f"[{current_phase_name}] Identified {len(retry_df_for_next_phase)} unique tasks for potential retry.")
        logger.info(f"[{current_phase_name}] Scraping finished. Returning {len(enriched_df_this_phase)} processed rows and {len(retry_df_for_next_phase)} tasks for retry.")
        return enriched_df_this_phase, retry_df_for_next_phase

# --- format_and_save_data ( 그대로 유지 ) ---
def format_and_save_data(final_df_to_save, original_input_df_for_headers_ref):
    output_filename = "final_results.csv"; logger.debug(f"Preparing to save data to '{output_filename}'.")
    if os.path.exists(output_filename):
        try: os.remove(output_filename); logger.info(f"Removed existing output file: '{output_filename}'.")
        except OSError as e: logger.error(f"Could not remove existing '{output_filename}': {e}.")
    if final_df_to_save is None or final_df_to_save.empty:
        logger.warning(f"No data to save to '{output_filename}'. Empty file with headers might be created.")
        if original_input_df_for_headers_ref is not None and not original_input_df_for_headers_ref.empty:
            header_tuples_for_empty_file = []
            col_map_for_headers = {'time': ('Time', ''), 'venue': ('Venue', ''), 'code': ('Code', ''), 'raceno': ('RaceNo', ''), 'runnerno': ('RunnerNo', ''), 'runnername': ('RunnerName', ''), 'type': ('Type', ''), 'market': ('Market', ''), 'bookie': ('Bookie', ''), 'odds': ('Odds', '')}
            for original_col_name in original_input_df_for_headers_ref.columns:
                col_lower = original_col_name.lower(); second_level = col_map_for_headers.get(col_lower, ('', ''))[1]
                header_tuples_for_empty_file.append((original_col_name, second_level))
            header_tuples_for_empty_file.extend([('BSP', 'Price Win'), ('BSP', 'Price Place')])
            try: pd.DataFrame(columns=pd.MultiIndex.from_tuples(header_tuples_for_empty_file)).to_csv(output_filename, index=False, encoding='utf-8-sig'); logger.info(f"Saved empty '{output_filename}' with expected headers.")
            except Exception as e_save_empty: logger.error(f"Failed to save empty '{output_filename}': {e_save_empty}", exc_info=True)
        else:
            try:
                with open(output_filename, 'w', newline='', encoding='utf-8-sig') as f_empty: csv_writer = csv.writer(f_empty); csv_writer.writerow(['BSP','BSP']); csv_writer.writerow(['Price Win','Price Place'])
                logger.info(f"Created minimal empty file '{output_filename}'.")
            except Exception as e_create_minimal: logger.error(f"Failed to create minimal empty '{output_filename}': {e_create_minimal}", exc_info=True)
        return
    logger.info(f"Formatting {len(final_df_to_save)} rows for '{output_filename}'...")
    df_to_format_internal = final_df_to_save.copy(); df_to_format_internal.columns = [str(c).lower() if pd.notna(c) else f"unnamed_col_{i}" for i, c in enumerate(df_to_format_internal.columns)]
    col_map_multi_output = {'time': ('Time', ''), 'venue': ('Venue', ''), 'code': ('Code', ''), 'raceno': ('RaceNo', ''), 'runnerno': ('RunnerNo', ''), 'runnername': ('RunnerName', ''), 'type': ('Type', ''), 'market': ('Market', ''), 'bookie': ('Bookie', ''), 'odds': ('Odds', ''), 'bsp price win': ('BSP', 'Price Win'), 'bsp price place': ('BSP', 'Price Place')}
    output_df_final_csv = pd.DataFrame(); final_multi_index_header_tuples = []
    if 'date_only' in df_to_format_internal.columns: df_to_format_internal = df_to_format_internal.drop(columns=['date_only'], errors='ignore'); logger.debug("Internal 'date_only' column removed.")
    if original_input_df_for_headers_ref is not None:
        for original_col_name_cased_ref in original_input_df_for_headers_ref.columns:
            original_col_lower_ref = original_col_name_cased_ref.lower()
            mi_tuple_sub_level = col_map_multi_output.get(original_col_lower_ref, ('', ''))[1]
            current_mi_tuple = (original_col_name_cased_ref, mi_tuple_sub_level)
            if original_col_lower_ref in df_to_format_internal: output_df_final_csv[current_mi_tuple] = df_to_format_internal[original_col_lower_ref]
            else: logger.debug(f"Original column '{original_col_name_cased_ref}' not in processed data. Outputting empty."); output_df_final_csv[current_mi_tuple] = pd.Series([pd.NA] * len(df_to_format_internal), index=df_to_format_internal.index if not df_to_format_internal.empty else None)
            final_multi_index_header_tuples.append(current_mi_tuple)
        bsp_win_def_tuple = col_map_multi_output['bsp price win']
        if bsp_win_def_tuple not in final_multi_index_header_tuples:
            if 'bsp price win' in df_to_format_internal: output_df_final_csv[bsp_win_def_tuple] = df_to_format_internal['bsp price win']
            else: output_df_final_csv[bsp_win_def_tuple] = pd.Series([pd.NA] * len(df_to_format_internal), index=df_to_format_internal.index if not df_to_format_internal.empty else None)
            final_multi_index_header_tuples.append(bsp_win_def_tuple)
        bsp_place_def_tuple = col_map_multi_output['bsp price place']
        if bsp_place_def_tuple not in final_multi_index_header_tuples:
            if 'bsp price place' in df_to_format_internal: output_df_final_csv[bsp_place_def_tuple] = df_to_format_internal['bsp price place']
            else: output_df_final_csv[bsp_place_def_tuple] = pd.Series([pd.NA] * len(df_to_format_internal), index=df_to_format_internal.index if not df_to_format_internal.empty else None)
            final_multi_index_header_tuples.append(bsp_place_def_tuple)
        if not output_df_final_csv.empty: output_df_final_csv.columns = pd.MultiIndex.from_tuples(final_multi_index_header_tuples)
        elif final_multi_index_header_tuples: output_df_final_csv = pd.DataFrame(columns=pd.MultiIndex.from_tuples(final_multi_index_header_tuples))
    try:
        output_df_final_csv.to_csv(output_filename, index=False, encoding='utf-8-sig'); logger.info(f"SUCCESS: Saved {len(output_df_final_csv)} entries to '{output_filename}'")
        if not output_df_final_csv.empty and len(output_df_final_csv) > 1 : logger.debug(f"\n--- Sample of Final Data (first 2 rows) ---\n{output_df_final_csv.head(2).to_string()}")
        elif not output_df_final_csv.empty: logger.debug(f"\n--- Sample of Final Data (1 row) ---\n{output_df_final_csv.head(1).to_string()}")
    except Exception as e_final_save: logger.error(f"Failed to save final data to '{output_filename}': {e_final_save}", exc_info=True)

# --- main ( 그대로 유지 ) ---
if __name__ == "__main__":
    logger.info("Script execution started.")
    input_tasks_df_raw_schema_ref = get_input_csv()
    if input_tasks_df_raw_schema_ref is None: logger.critical("Input CSV could not be loaded. Script terminated.")
    elif input_tasks_df_raw_schema_ref.empty:
        logger.warning("Input CSV loaded but is empty. No tasks to process.")
        format_and_save_data(pd.DataFrame(), input_tasks_df_raw_schema_ref)
    else:
        logger.info(f"Successfully loaded {len(input_tasks_df_raw_schema_ref)} raw tasks from CSV.")

        id_cols_raw_input = [col.lower() for col in ['Time', 'Venue', 'Code', 'RaceNo', 'RunnerNo', 'RunnerName'] if col.lower() in input_tasks_df_raw_schema_ref.columns]
        if id_cols_raw_input:
            initial_count = len(input_tasks_df_raw_schema_ref)
            input_tasks_df_raw_schema_ref.drop_duplicates(subset=id_cols_raw_input, keep='first', inplace=True)
            deduped_count = initial_count - len(input_tasks_df_raw_schema_ref)
            if deduped_count > 0:
                logger.info(f"Deduplicated raw input: Removed {deduped_count} identical task rows. {len(input_tasks_df_raw_schema_ref)} tasks remain.")
        else:
            logger.warning("Could not determine key ID columns for raw input deduplication.")

        tasks_for_phase1_input = filter_tasks_for_last_n_days(input_tasks_df_raw_schema_ref.copy(), days=8)

        if tasks_for_phase1_input is None or tasks_for_phase1_input.empty:
            logger.warning("No tasks remaining after 8-day date filtering. No scraping.")
            format_and_save_data(pd.DataFrame(), input_tasks_df_raw_schema_ref)
        else:
            logger.info(f"{len(tasks_for_phase1_input)} tasks for Phase 1 after 8-day filter.")
            logger.info("--- Starting Scraping Phase 1 (Exact Venue Match) ---")
            phase1_enriched_results_df, phase1_retry_candidates_tasks_df = scrape_and_enrich_csv(
                tasks_for_phase1_input.copy(),
                current_phase_name="Phase 1 (Exact Venue)"
            )
            logger.info(f"--- Phase 1 Finished. Processed {len(phase1_enriched_results_df)} task results. Identified {len(phase1_retry_candidates_tasks_df)} for retry. ---")

            all_phases_results_list = [phase1_enriched_results_df]

            if phase1_retry_candidates_tasks_df is not None and not phase1_retry_candidates_tasks_df.empty:
                logger.info(f"--- Starting Scraping Phase 2 (Retry & Fuzzy Venue Match for {len(phase1_retry_candidates_tasks_df)} tasks) ---")
                phase2_enriched_results_df, phase2_still_needs_retry_df = scrape_and_enrich_csv(
                    phase1_retry_candidates_tasks_df.copy(),
                    current_phase_name="Phase 2 (Fuzzy Venue)",
                    fuzzy_venue_matching=True # Enable fuzzy matching for the retry phase
                )
                logger.info(f"--- Phase 2 Finished. Processed {len(phase2_enriched_results_df)} retry task results. ---")
                if phase2_still_needs_retry_df is not None and not phase2_still_needs_retry_df.empty:
                    logger.warning(f"{len(phase2_still_needs_retry_df)} tasks still marked for retry after Phase 2 (will not be retried further).")
                all_phases_results_list.append(phase2_enriched_results_df)
            else:
                logger.info("No tasks identified for Phase 2 retry.")

            final_combined_output_df = pd.DataFrame()
            valid_phase_results_dfs = [df for df in all_phases_results_list if df is not None and not df.empty]

            if valid_phase_results_dfs:
                temp_combined_df_all_attempts = pd.concat(valid_phase_results_dfs, ignore_index=True)
                id_cols_for_deduplication_ref = ['Time', 'Venue', 'Code', 'RaceNo', 'RunnerNo', 'RunnerName']
                id_cols_for_deduplication_lower = [col.lower() for col in id_cols_for_deduplication_ref if col.lower() in temp_combined_df_all_attempts.columns]

                if not id_cols_for_deduplication_lower:
                    logger.warning("Fallback ID columns for deduplication, as primary could not be mapped.")
                    standard_id_cols = ['time', 'venue', 'code', 'raceno', 'runnerno', 'runnername']
                    id_cols_for_deduplication_lower = [c for c in standard_id_cols if c in temp_combined_df_all_attempts.columns]

                if id_cols_for_deduplication_lower and not temp_combined_df_all_attempts.empty:
                    logger.info(f"Combining results. Total rows from all attempts: {len(temp_combined_df_all_attempts)}. Deduplicating by {id_cols_for_deduplication_lower}, keeping 'last' attempt.")
                    final_combined_output_df = temp_combined_df_all_attempts.drop_duplicates(subset=id_cols_for_deduplication_lower, keep='last')
                    dropped_duplicates_count = len(temp_combined_df_all_attempts) - len(final_combined_output_df)
                    if dropped_duplicates_count > 0: logger.info(f"Dropped {dropped_duplicates_count} earlier attempts for retried tasks.")
                else:
                    logger.error("Could not determine ID columns for combining, or no valid data. Using raw concatenated data (may contain duplicates).")
                    final_combined_output_df = temp_combined_df_all_attempts
            else:
                logger.warning("No valid results from any scraping phase.")

            logger.info(f"Total unique task rows after combining all phases: {len(final_combined_output_df)}")
            if not final_combined_output_df.empty:
                script_error_values = [
                    'date previously failed this phase', 'date selection error', 'date data not loaded',
                    'unknown race code', 'code selection error', 'venue load error', 'driver setup error phase',
                    'date parse error for grouping', 'venue data unavailable', 'venue element error',
                    'venue element error mid-race', 'race timeout', 'race element missing',
                    'race stale element', 'race error', 'runner not found on page',
                    'stale element', 'scrape error', 'processing incomplete', 'ambiguous fuzzy match' # Added new error type
                ]
                bsp_win_col_name_lower = 'bsp price win'
                if bsp_win_col_name_lower in final_combined_output_df.columns:
                    error_check_series = final_combined_output_df[bsp_win_col_name_lower].fillna('na_placeholder_for_error_check').astype(str).str.lower()
                    failed_scrapes_mask_final = error_check_series.isin(script_error_values)
                    failed_scrapes_count_final = failed_scrapes_mask_final.sum()
                    successful_scrapes_count_final = len(final_combined_output_df) - failed_scrapes_count_final
                else:
                    logger.warning(f"Column '{bsp_win_col_name_lower}' missing from final_combined_output_df. Cannot calculate detailed success/failure stats accurately.")
                    failed_scrapes_count_final = len(final_combined_output_df); successful_scrapes_count_final = 0

                logger.info("--- OVERALL SCRAPING SUMMARY (After All Phases) ---")
                logger.info(f"Total Input Tasks (for Phase 1, after 8-day & initial dedupe): {len(tasks_for_phase1_input if tasks_for_phase1_input is not None else [])}")
                logger.info(f"  Total Unique Task Rows in Final Output CSV: {len(final_combined_output_df)}")
                logger.info(f"  Successfully Scraped (BSP value found or valid 'N/A'): {successful_scrapes_count_final}")
                logger.info(f"  Failed/Error Rows (Script Error, Not Found, etc.): {failed_scrapes_count_final}")
                logger.info("----------------------------------------------------")
            else: logger.info("--- OVERALL SCRAPING SUMMARY --- Final combined DataFrame is empty. ---")

            format_and_save_data(final_combined_output_df, input_tasks_df_raw_schema_ref)
    logger.info("Script execution finished.")