import re
import time
from concurrent.futures import ThreadPoolExecutor
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET

# Constants
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 5
BACKOFF_FACTOR = 2
THREAD_POOL_SIZE = 10

# Log file to store problematic links
failed_links = []

# Function to clean the URL by removing leading text before the URL
def clean_url(url):
    match = re.search(r'https?://[^\s]+', url)
    if match:
        return match.group(0)
    return None

# Function to scrape and check a single URL
def scrape_and_check(url, element):
    retries = 0
    retry_delay = INITIAL_RETRY_DELAY
    while retries < MAX_RETRIES:
        try:
            cleaned_url = clean_url(url)
            if not cleaned_url:
                print(f"Invalid URL in string: {url}")
                return True
            
            print(f"Checking URL: {cleaned_url}")
            options = webdriver.ChromeOptions()
            options.add_argument("--headless")
            driver = webdriver.Chrome(options=options)

            driver.get(cleaned_url)
            try:
                WebDriverWait(driver, 30).until(
                    EC.invisibility_of_element_located((By.XPATH, "//div[contains(text(), 'Loading...')]"))
                )
            except TimeoutException:
                print(f"Timeout waiting for content to load at URL: {cleaned_url}")
                retries += 1
                print(f"Retrying... ({retries}/{MAX_RETRIES})")
                print(f"Waiting for {retry_delay} seconds before retrying...")
                time.sleep(retry_delay)
                retry_delay *= BACKOFF_FACTOR
                continue

            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            json_div = soup.find('div', string=re.compile(r'^\s*\{.*"_errors".*\}\s*$', re.DOTALL))
            driver.quit()

            if json_div:
                print(f"Error JSON found at URL: {cleaned_url}")
                return True
            
            print(f"Page loaded successfully: {cleaned_url}")
            return False
        except Exception as e:
            print(f"Error with URL {url}: {e}")
            retries += 1
            time.sleep(retry_delay)
            retry_delay *= BACKOFF_FACTOR
    return True

# Function to process a single element
def process_element(element, namespaces):
    iao_element = element.find('obo:IAO_0000412', namespaces)
    if iao_element is not None and iao_element.text:
        url = iao_element.text.strip()
        class_url = element.get('{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about')
        label = element.find('rdfs:label', namespaces)
        label_text = label.text.strip() if label is not None else "No label"

        if 'unite community' not in url.lower():
            print(f"Skipping URL (does not contain 'UNITE community'): {url}")
            return None
        
        if scrape_and_check(url, element):
            return f"{label_text}\n{url}\n{class_url}"
    return None

# Function to parse XML and process elements with threads
def process_xml(xml_file):
    tree = ET.parse(xml_file)
    root = tree.getroot()

    namespaces = {
        'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
        'obo': 'http://purl.obolibrary.org/obo/',
        'owl': 'http://www.w3.org/2002/07/owl#',
        'rdfs': 'http://www.w3.org/2000/01/rdf-schema#',
        'dc': 'http://purl.org/dc/elements/1.1/'
    }

    elements = root.findall('.//owl:Class', namespaces)
    print(f"Found {len(elements)} elements to process.")

    with ThreadPoolExecutor(max_workers=THREAD_POOL_SIZE) as executor:
        results = list(executor.map(lambda e: process_element(e, namespaces), elements))

    global failed_links
    failed_links = [result for result in results if result is not None]

    if failed_links:
        with open("failed_links.txt", "w") as log_file:
            log_file.write("\n\n".join(failed_links) + "\n\n")
        print(f"Found {len(failed_links)} failed links. See 'failed_links.txt' for details.")
    else:
        print("No failed links found.")

# Main function to run the process
def main():
    xml_file = 'mido.xml'
    process_xml(xml_file)

if __name__ == "__main__":
    main()