import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import json
from urllib.parse import urljoin, urlparse
import logging
from typing import List, Dict, Optional
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException


class CibusScraperException(Exception):
    """Custom exception for Cibus scraper errors"""
    pass


class CibusCatalogScraper:
    """
    A comprehensive scraper for the Cibus 2024 catalog website
    https://catalogo.fiereparma.it/manifestazione/cibus-2024/
    """

    def __init__(self, base_url: str = "https://catalogo.fiereparma.it/manifestazione/cibus-2024/",
                 use_selenium: bool = True):
        self.base_url = base_url
        self.use_selenium = use_selenium

        # Setup requests session
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

        # Setup Selenium if needed
        self.driver = None
        if use_selenium:
            self.setup_selenium()

        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

        # Storage for scraped data
        self.exhibitors_data = []
        self.raw_text_data = []

    def setup_selenium(self):
        """Setup Selenium WebDriver"""
        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless")  # Run in background
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument(
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

            self.driver = webdriver.Chrome(options=chrome_options)
            self.logger.info("Selenium WebDriver initialized successfully")
        except Exception as e:
            self.logger.warning(f"Failed to initialize Selenium: {e}. Will use requests only.")
            self.use_selenium = False

    def get_page_selenium(self, url: str) -> Optional[BeautifulSoup]:
        """Get page content using Selenium"""
        if not self.driver:
            return None

        try:
            self.driver.get(url)
            time.sleep(3)  # Wait for page to load

            # Try to find and click "Load More" or similar buttons
            try:
                load_more_button = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH,
                                                "//button[contains(text(), 'Load') or contains(text(), 'More') or contains(text(), 'Carica')]"))
                )
                load_more_button.click()
                time.sleep(2)
            except TimeoutException:
                pass  # No load more button found

            # Get page source and parse with BeautifulSoup
            page_source = self.driver.page_source
            return BeautifulSoup(page_source, 'html.parser')

        except Exception as e:
            self.logger.error(f"Error getting page with Selenium: {e}")
            return None

    def get_page_requests(self, url: str, max_retries: int = 3) -> Optional[BeautifulSoup]:
        """Get page content using requests"""
        for attempt in range(max_retries):
            try:
                response = self.session.get(url, timeout=10)
                response.raise_for_status()
                return BeautifulSoup(response.content, 'html.parser')
            except requests.RequestException as e:
                self.logger.warning(f"Attempt {attempt + 1} failed for {url}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    self.logger.error(f"Failed to fetch {url} after {max_retries} attempts")
                    return None

    def get_page(self, url: str) -> Optional[BeautifulSoup]:
        """Get page using preferred method"""
        if self.use_selenium:
            return self.get_page_selenium(url)
        else:
            return self.get_page_requests(url)

    def parse_raw_text_data(self, text: str) -> List[Dict]:
        """Parse exhibitor data from raw text"""
        exhibitors = []

        # Split text into lines and process
        lines = [line.strip() for line in text.split('\n') if line.strip()]

        current_exhibitor = {}
        i = 0

        while i < len(lines):
            line = lines[i]

            # Look for pavilion and stand pattern
            pavilion_match = re.search(r'Padiglione\s+(\d+(?:-\d+)?)\s+-\s+Stand\s+([A-Z]\s+\d+)', line)
            if pavilion_match:
                # If we have a current exhibitor, save it
                if current_exhibitor:
                    exhibitors.append(current_exhibitor)

                # Start new exhibitor
                current_exhibitor = {
                    'pavilion': pavilion_match.group(1),
                    'stand': pavilion_match.group(2),
                    'name': '',
                    'type': 'Espositore',
                    'description': '',
                    'products': []
                }

                # Check next line for exhibitor type
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    if next_line in ['Co-espositore', 'Marchio', 'Azienda Rappresentata']:
                        current_exhibitor['type'] = next_line
                        i += 1  # Skip this line
                    else:
                        # Next line might be company name
                        if not re.search(r'Padiglione', next_line):
                            current_exhibitor['name'] = next_line
                            i += 1

            elif line in ['Co-espositore', 'Marchio', 'Azienda Rappresentata']:
                if current_exhibitor:
                    current_exhibitor['type'] = line

            elif line and not re.search(r'Padiglione', line):
                # This might be a company name or description
                if current_exhibitor and not current_exhibitor.get('name'):
                    current_exhibitor['name'] = line
                elif current_exhibitor and current_exhibitor.get('name'):
                    # Additional info
                    if 'description' not in current_exhibitor:
                        current_exhibitor['description'] = line
                    else:
                        current_exhibitor['description'] += ' ' + line

            i += 1

        # Add last exhibitor if exists
        if current_exhibitor:
            exhibitors.append(current_exhibitor)

        return exhibitors

    def extract_exhibitors_from_page(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract exhibitor data from parsed page"""
        exhibitors = []

        # Method 1: Look for structured data
        exhibitor_elements = soup.find_all(['div', 'section', 'article'],
                                           class_=re.compile(r'(exhibitor|espositore|stand|company)', re.I))

        if exhibitor_elements:
            self.logger.info(f"Found {len(exhibitor_elements)} structured exhibitor elements")
            for element in exhibitor_elements:
                exhibitor_data = self.extract_exhibitor_from_element(element)
                if exhibitor_data:
                    exhibitors.append(exhibitor_data)

        # Method 2: Extract from raw text if no structured data found
        if not exhibitors:
            self.logger.info("No structured data found, parsing raw text")
            page_text = soup.get_text()
            self.raw_text_data.append(page_text)
            exhibitors = self.parse_raw_text_data(page_text)

        # Method 3: Look for table data
        if not exhibitors:
            tables = soup.find_all('table')
            for table in tables:
                table_exhibitors = self.extract_exhibitors_from_table(table)
                exhibitors.extend(table_exhibitors)

        return exhibitors

    def extract_exhibitor_from_element(self, element) -> Optional[Dict]:
        """Extract exhibitor data from a single element"""
        try:
            exhibitor_data = {
                'name': '',
                'pavilion': '',
                'stand': '',
                'type': 'Espositore',
                'description': '',
                'contact_info': {}
            }

            text_content = element.get_text()

            # Extract name from links or headers
            name_element = element.find(['a', 'h1', 'h2', 'h3', 'h4', 'strong'])
            if name_element:
                exhibitor_data['name'] = name_element.get_text(strip=True)

            # Extract pavilion and stand
            pavilion_match = re.search(r'Padiglione\s+(\d+(?:-\d+)?)', text_content)
            if pavilion_match:
                exhibitor_data['pavilion'] = pavilion_match.group(1)

            stand_match = re.search(r'Stand\s+([A-Z]\s+\d+)', text_content)
            if stand_match:
                exhibitor_data['stand'] = stand_match.group(1)

            # Extract type
            if 'Co-espositore' in text_content:
                exhibitor_data['type'] = 'Co-espositore'
            elif 'Marchio' in text_content:
                exhibitor_data['type'] = 'Marchio'
            elif 'Azienda Rappresentata' in text_content:
                exhibitor_data['type'] = 'Azienda Rappresentata'

            return exhibitor_data if exhibitor_data['name'] or exhibitor_data['pavilion'] else None

        except Exception as e:
            self.logger.error(f"Error extracting exhibitor from element: {e}")
            return None

    def extract_exhibitors_from_table(self, table) -> List[Dict]:
        """Extract exhibitor data from table"""
        exhibitors = []

        try:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:  # At least name and location
                    exhibitor_data = {
                        'name': cells[0].get_text(strip=True),
                        'pavilion': '',
                        'stand': '',
                        'type': 'Espositore',
                        'description': ''
                    }

                    # Try to extract pavilion/stand from second column
                    location_text = cells[1].get_text(strip=True)
                    pavilion_match = re.search(r'Padiglione\s+(\d+(?:-\d+)?)', location_text)
                    if pavilion_match:
                        exhibitor_data['pavilion'] = pavilion_match.group(1)

                    stand_match = re.search(r'Stand\s+([A-Z]\s+\d+)', location_text)
                    if stand_match:
                        exhibitor_data['stand'] = stand_match.group(1)

                    if exhibitor_data['name']:
                        exhibitors.append(exhibitor_data)

        except Exception as e:
            self.logger.error(f"Error extracting from table: {e}")

        return exhibitors

    def scrape_exhibitors_list(self, limit: Optional[int] = None) -> List[Dict]:
        """Main method to scrape exhibitors"""
        self.logger.info("Starting to scrape exhibitors list...")

        # Try main page first
        soup = self.get_page(self.base_url)
        if not soup:
            raise CibusScraperException("Failed to fetch main page")

        exhibitors = self.extract_exhibitors_from_page(soup)

        # If no exhibitors found, try alternative URLs
        if not exhibitors:
            alternative_urls = [
                f"{self.base_url}espositori/",
                f"{self.base_url}exhibitors/",
                f"{self.base_url}elenco-espositori/",
                f"{self.base_url}lista-espositori/"
            ]

            for alt_url in alternative_urls:
                self.logger.info(f"Trying alternative URL: {alt_url}")
                soup = self.get_page(alt_url)
                if soup:
                    alt_exhibitors = self.extract_exhibitors_from_page(soup)
                    if alt_exhibitors:
                        exhibitors.extend(alt_exhibitors)
                        break

        # Apply limit if specified
        if limit and len(exhibitors) > limit:
            exhibitors = exhibitors[:limit]

        # Clean and deduplicate
        exhibitors = self.clean_exhibitors_data(exhibitors)

        self.exhibitors_data = exhibitors
        self.logger.info(f"Successfully scraped {len(exhibitors)} exhibitors")

        return exhibitors

    def clean_exhibitors_data(self, exhibitors: List[Dict]) -> List[Dict]:
        """Clean and deduplicate exhibitor data"""
        cleaned = []
        seen = set()

        for exhibitor in exhibitors:
            # Create a unique key for deduplication
            key = f"{exhibitor.get('name', '')}-{exhibitor.get('pavilion', '')}-{exhibitor.get('stand', '')}"

            if key not in seen and (exhibitor.get('name') or exhibitor.get('pavilion')):
                seen.add(key)

                # Clean up data
                for field in ['name', 'pavilion', 'stand', 'type', 'description']:
                    if field in exhibitor:
                        exhibitor[field] = str(exhibitor[field]).strip()

                cleaned.append(exhibitor)

        return cleaned

    def save_to_csv(self, filename: str = "cibus_2024_exhibitors.csv"):
        """Save scraped data to CSV file"""
        if not self.exhibitors_data:
            self.logger.warning("No exhibitor data to save")
            return

        df = pd.DataFrame(self.exhibitors_data)
        df.to_csv(filename, index=False, encoding='utf-8')
        self.logger.info(f"Data saved to {filename}")

    def save_to_json(self, filename: str = "cibus_2024_exhibitors.json"):
        """Save scraped data to JSON file"""
        data = {
            'exhibitors': self.exhibitors_data,
            'raw_text': self.raw_text_data,
            'scraped_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'total_exhibitors': len(self.exhibitors_data)
        }

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Data saved to {filename}")

    def get_statistics(self) -> Dict:
        """Get statistics about the scraped data"""
        if not self.exhibitors_data:
            return {'total_exhibitors': 0}

        stats = {
            'total_exhibitors': len(self.exhibitors_data),
            'pavilions': {},
            'types': {},
            'with_names': 0
        }

        for exhibitor in self.exhibitors_data:
            # Count pavilions
            pavilion = exhibitor.get('pavilion', 'Unknown')
            stats['pavilions'][pavilion] = stats['pavilions'].get(pavilion, 0) + 1

            # Count types
            exhibitor_type = exhibitor.get('type', 'Unknown')
            stats['types'][exhibitor_type] = stats['types'].get(exhibitor_type, 0) + 1

            # Count with names
            if exhibitor.get('name'):
                stats['with_names'] += 1

        return stats

    def close(self):
        """Clean up resources"""
        if self.driver:
            self.driver.quit()


def main():
    """Example usage of the CibusCatalogScraper"""
    # Try without Selenium first (faster)
    scraper = CibusCatalogScraper(use_selenium=False)

    try:
        # Scrape exhibitors
        exhibitors = scraper.scrape_exhibitors_list(limit=100)

        # If no results, try with Selenium
        if not exhibitors:
            print("No results with requests, trying with Selenium...")
            scraper.close()
            scraper = CibusCatalogScraper(use_selenium=True)
            exhibitors = scraper.scrape_exhibitors_list(limit=100)

        # Save data
        scraper.save_to_csv()
        scraper.save_to_json()

        # Print statistics
        stats = scraper.get_statistics()
        print("\n=== SCRAPING STATISTICS ===")
        print(f"Total exhibitors: {stats['total_exhibitors']}")
        print(f"Exhibitors with names: {stats.get('with_names', 0)}")

        if stats.get('pavilions'):
            print("\nPavilions:")
            for pavilion, count in stats['pavilions'].items():
                print(f"  {pavilion}: {count} exhibitors")

        if stats.get('types'):
            print("\nExhibitor types:")
            for type_name, count in stats['types'].items():
                print(f"  {type_name}: {count} exhibitors")

        # Show sample data
        if exhibitors:
            print("\n=== SAMPLE EXHIBITOR DATA ===")
            for i, exhibitor in enumerate(exhibitors[:5]):
                print(f"{i + 1}. {exhibitor}")

    except Exception as e:
        print(f"Error: {e}")

    finally:
        scraper.close()


if __name__ == "__main__":
    main()