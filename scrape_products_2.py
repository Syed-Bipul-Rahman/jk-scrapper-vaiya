"""
Script Name: scrape_products.py

Description
-----------
This script logs in to the J&K Cabinetry website using the provided
credentials and scrapes product information for a set of cabinet
category IDs. Each category is represented by a unique identifier
provided by the user. The script attempts to discover an API endpoint
per category that returns structured product data. Once products are
retrieved, it downloads the associated high‑resolution images, saves
them into an `output/<category_id>/` folder, and writes a
`products.json` file containing the product details. Low‑resolution
markers (e.g. `_352x192`) are removed from image file names so
high‑resolution versions are saved instead.

Key Features
------------
* Uses `requests.Session` to persist cookies across requests and
  maintain authentication state.
* Handles CSRF tokens or hidden form fields if present on the login
  page.
* Implements a backoff mechanism with delays between requests to
  avoid overwhelming the server.
* Logs progress and warnings without halting execution when
  encountering missing images, timeouts or other recoverable errors.
* Creates a clean folder structure under `output/` with one folder
  per category ID. Each folder contains a `products.json` file and
  all downloaded images.

Usage
-----
Run the script as a standalone program. No command line arguments
are required because the category identifiers and login credentials
are baked into the code for simplicity. Ensure that the `requests`
and `beautifulsoup4` packages are installed in your environment.

    python scrape_products.py

Limitations
-----------
* The exact API endpoints used by J&K Cabinetry are not publicly
  documented. This script makes a best effort to guess a
  `get‑parts/<category_id>` endpoint based on the user’s guidance.
  Should the endpoints differ, you may need to adjust the
  `fetch_products` function accordingly.
* If the site changes its login workflow or introduces additional
  security measures (e.g. reCAPTCHA or hidden fields), you may need
  to update the `login` function to handle those changes.
* Because the site restricts access from unknown origins, calls to
  the API may return HTTP 403 or 404 responses. The script will
  continue gracefully but will not be able to scrape products for
  such categories.
"""

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup


# -----------------------------------------------------------------------------
# Configuration
#
# Update the email, password and access token with the credentials provided by
# the user. Be careful not to commit sensitive credentials to public
# repositories. In a production environment you should load these values from
# environment variables or a secrets manager.

EMAIL: str = "Ngobuildersinc@gmail.com"
PASSWORD: str = "Hammer2025!"

# Bearer token for API requests. This may expire; if you receive 401/403
# responses you may need to refresh it via the appropriate authentication
# endpoint or obtain a new token.
ACCESS_TOKEN: str = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJ1c2VySWQiOiI2ODk5OGEyOGNhNmE0MmY1NTQ5MjE2MWQiLCJyb2xlIjoiYWRtaW4iLCJpYXQiOjE3NTQ5MDQ5NDQs"
    "ImV4cCI6MTc1NzQ5Njk0NH0."
    "id4ix6EgKTM739DgKVznL8Wbu9k9blCM7SHmuWYqpVE"
)

# List of category identifiers provided by the user. The script will iterate
# through each of these IDs and attempt to fetch products belonging to that
# category via the API. If the endpoint is unavailable, the script logs a
# warning and moves on to the next category.
CATEGORY_IDS: List[str] = [
    "689cba9eca19d8fef712c080",  # Sink Base Cabinet
    "689cbaa6ca19d8fef712c087",  # Vanity Cabinet
    "689cbac5ca19d8fef712c094",  # Wall Cabinet
    "689cbad7ca19d8fef712c09b",  # Wall Diagonal Cabinet
    "689cbae2ca19d8fef712c0a3",  # Wall Shelf Cabinet
    "689d86fbca19d8fef712c6b1",  # Pantry Cabinet
    "689d8704ca19d8fef712c6ba",  # Oven Cabinet
    "689d8713ca19d8fef712c6d5",  # Wall Glass Cabinet
    "689d871fca19d8fef712c6e4",  # Wall Diagonal Glass Cabinet
    "689d8727ca19d8fef712c6ec",  # Glass Frame
    "689d9e2dca19d8fef712c918",  # Base Cabinet
    "689d9e36ca19d8fef712c91f",  # Drawer Base Cabinet
    "689d9e3fca19d8fef712c927",  # Corner Base Cabinet
    "689d8758ca19d8fef712c70a",  # Molding
    "689d8761ca19d8fef712c711",  # Filler
    "689d8769ca19d8fef712c719",  # Base Filler
    "689d8770ca19d8fef712c722",  # Wall Filler
    "689d8798ca19d8fef712c745",  # Sample Door
    "689d879eca19d8fef712c74c",  # Touchup
    "689d87a5ca19d8fef712c75c",  # Turn Post
    "689d87abca19d8fef712c76b",  # Corbel
    "689d87b2ca19d8fef712c775",  # Accessory
    "689d87bdca19d8fef712c780",  # Valance
    "689d87c6ca19d8fef712c78c",  # Knee Drawer
    "689d87ceca19d8fef712c799",  # Roll‑Out Trays
]

# Endpoints used by the script. These may need to be adjusted if the
# underlying API changes.  The login URL is used to authenticate with the
# website, while the base API URL is used to fetch product information.  The
# `PRODUCTS_ENDPOINT_TEMPLATE` uses the category identifier to construct the
# full URL for retrieving products.
LOGIN_URL: str = "https://www.jkcabinetry.com/account/login"
BASE_API_URL: str = "https://api.jkcabinetryct.com"
PRODUCTS_ENDPOINT_TEMPLATE: str = (
    BASE_API_URL + "/parts/get-parts/{category_id}"
)


@dataclass
class Product:
    """Represents a single product scraped from the API."""

    id: str
    name: str
    price: Optional[float]
    description: str
    image: str  # Filename of the downloaded image


def sanitize_filename(filename: str) -> str:
    """Sanitize filenames to remove characters not allowed on most filesystems.

    Args:
        filename: The original filename extracted from the image URL.

    Returns:
        A sanitized filename safe for writing to disk.
    """
    # Remove any query strings or fragments
    filename = filename.split("?")[0]
    # Remove path separators and strip leading/trailing whitespace
    filename = os.path.basename(filename).strip()
    # Replace spaces and invalid characters with underscores
    filename = re.sub(r"[^A-Za-z0-9_.-]", "_", filename)
    return filename


def strip_resolution_suffix(url: str) -> str:
    """Remove resolution suffix patterns (e.g. `_352x192`) from an image URL.

    Many of the product image URLs include suffixes that denote a low
    resolution version of the image. To download the high‑resolution
    equivalent, we strip those suffixes before the file extension.

    Args:
        url: The URL of the image as provided by the API or product page.

    Returns:
        The modified URL pointing to the high‑resolution image.
    """
    # Split URL into base and query components
    base, sep, query = url.partition("?")
    # Replace patterns like `_123x456` just before the extension
    new_base = re.sub(r"_(\d{2,5}x\d{2,5})(?=\.[A-Za-z]+$)", "", base)
    # Reassemble the URL, preserving query if present
    return new_base + (sep + query if sep else "")


def login(session: requests.Session) -> bool:
    """Authenticate with the J&K Cabinetry website.

    The function performs a GET request to fetch the login page and parse
    hidden fields (e.g. CSRF tokens). It then submits the login form with
    the user’s email and password. If additional hidden fields are present,
    they are passed through automatically.

    Args:
        session: A `requests.Session` object used to persist cookies.

    Returns:
        True if login was successful, False otherwise.
    """
    try:
        # Fetch the login page to obtain cookies and hidden fields
        print("Fetching login page…")
        # Use a common browser User-Agent to reduce the likelihood of being blocked
        default_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:98.0) Gecko/20100101 Firefox/98.0"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        resp = session.get(LOGIN_URL, headers=default_headers, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Find the correct login form by searching for a form that contains a
        # password field. Some pages include multiple forms (e.g. search bar), so
        # picking the first form blindly can lead to submitting credentials to
        # the wrong endpoint (such as /search).  We iterate over all forms and
        # choose the first one that has an input whose type is "password" or
        # whose name includes "pass".
        forms = soup.find_all("form") or []
        login_form = None
        for frm in forms:
            # Look for any password input inside the form
            pw_field = frm.find("input", {"type": "password"})
            if pw_field:
                login_form = frm
                break
            # Alternatively, check input names for typical password keywords
            for inp in frm.find_all("input"):
                name_attr = inp.get("name", "").lower()
                if "pass" in name_attr:
                    login_form = frm
                    break
            if login_form:
                break

        if login_form is None:
            print(
                "Warning: No login form with a password field found; attempting to post credentials directly."
            )
            payload = {"Email": EMAIL, "Password": PASSWORD}
            post_resp = session.post(LOGIN_URL, headers=default_headers, data=payload, timeout=20)
            return post_resp.status_code == 200

        # Extract the form action; default to the current URL if missing
        action = login_form.get("action") or LOGIN_URL
        login_action_url = (
            action if action.startswith("http") else requests.compat.urljoin(LOGIN_URL, action)
        )

        # Prepare payload with all hidden inputs and default values
        payload: Dict[str, str] = {}
        for input_elem in login_form.find_all("input"):
            name = input_elem.get("name")
            if not name:
                continue
            value = input_elem.get("value", "")
            payload[name] = value

        # Fill in credentials based on input names
        for key in list(payload.keys()):
            lower_key = key.lower()
            if "email" in lower_key or "username" in lower_key or "customer[email]" in lower_key:
                payload[key] = EMAIL
            elif "pass" in lower_key:
                payload[key] = PASSWORD

        # In case the form did not include fields for email or password, set them
        if not any("email" in k.lower() or "username" in k.lower() for k in payload):
            payload["email"] = EMAIL
        if not any("pass" in k.lower() for k in payload):
            payload["password"] = PASSWORD

        print(f"Submitting login form to {login_action_url}…")
        post_resp = session.post(
            login_action_url, headers=default_headers, data=payload, timeout=20
        )
        post_resp.raise_for_status()

        # Check for redirects (HTTP 301/302).  A successful login will often
        # redirect to the account dashboard or home page.
        if post_resp.history and post_resp.history[0].status_code in (301, 302):
            print("Login redirects detected; assuming success.")
            return True

        # Check response text for markers of successful login
        if "logout" in post_resp.text.lower() or "my account" in post_resp.text.lower():
            print("Login successful.")
            return True

        print("Login may have failed; please verify credentials.")
        return False
    except Exception as exc:
        print(f"Error during login: {exc}")
        return False


def fetch_products(session: requests.Session, category_id: str) -> Optional[List[Dict]]:
    """Retrieve products for a given category identifier.

    The function constructs the API URL using the category ID and the
    `PRODUCTS_ENDPOINT_TEMPLATE`. It then performs a GET request with
    appropriate authorization headers. If the response contains a JSON
    payload with a `data` field, it returns the list of products.  If
    the request fails or the response cannot be parsed, the function
    logs a warning and returns None.

    Args:
        session: Authenticated `requests.Session` instance.
        category_id: The unique identifier for the cabinet category.

    Returns:
        A list of dictionaries representing products, or None if the
        request failed.
    """
    url = PRODUCTS_ENDPOINT_TEMPLATE.format(category_id=category_id)
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; scrape_products/1.0)",
    }
    try:
        response = session.get(url, headers=headers, timeout=30)
        if response.status_code != 200:
            print(f"Warning: Failed to fetch products for category {category_id} (status {response.status_code}).")
            return None
        data = response.json()
        # Some APIs wrap results in a 'data' or 'result' field; adjust as needed
        if isinstance(data, dict):
            # Try direct list
            if isinstance(data.get("data"), list):
                return data["data"]
            elif isinstance(data.get("result"), list):
                return data["result"]
            elif isinstance(data.get("products"), list):
                return data["products"]
        elif isinstance(data, list):
            return data
        print(f"Warning: Unexpected response format for category {category_id}.")
        return None
    except requests.exceptions.JSONDecodeError:
        print(f"Warning: Unable to decode JSON for category {category_id}.")
        return None
    except Exception as exc:
        print(f"Warning: Exception while fetching category {category_id}: {exc}")
        return None


def download_image(session: requests.Session, url: str, dest_path: str) -> bool:
    """Download an image from a URL and save it to a destination path.

    If the download fails (e.g. due to HTTP error or timeout), a
    warning is logged and the function returns False.

    Args:
        session: Authenticated `requests.Session` instance.
        url: The URL of the image to download.
        dest_path: The full path on disk where the image will be saved.

    Returns:
        True on success, False on failure.
    """
    try:
        resp = session.get(url, timeout=40)
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            f.write(resp.content)
        return True
    except Exception as exc:
        print(f"Warning: Failed to download image {url}: {exc}")
        return False


def process_category(session: requests.Session, category_id: str) -> None:
    """Process a single category: fetch products, download images and write JSON.

    This function coordinates all steps needed for a category: it calls
    the API to retrieve product details, creates a dedicated output
    directory, downloads high‑resolution images, and writes the
    `products.json` file.

    Args:
        session: Authenticated `requests.Session` instance.
        category_id: The unique identifier for the cabinet category.
    """
    print(f"\nScraping category: {category_id}…")
    products_data = fetch_products(session, category_id)
    if not products_data:
        print(f"No products found for category {category_id} or unable to fetch data.")
        return

    # Prepare output directory
    category_folder = os.path.join("output", category_id)
    os.makedirs(category_folder, exist_ok=True)

    products_list: List[Product] = []

    for product in products_data:
        # Extract basic fields with fallbacks
        pid = str(product.get("id") or product.get("_id") or "")
        name = str(product.get("name") or product.get("title") or product.get("product_name") or "").strip()
        description = str(product.get("description") or product.get("desc") or product.get("product_description") or "").strip()
        price_raw = product.get("price") or product.get("product_price")
        try:
            price = float(price_raw) if price_raw is not None else None
        except (TypeError, ValueError):
            # Strip non‑numeric characters and try again
            cleaned = re.sub(r"[^0-9.]+", "", str(price_raw))
            try:
                price = float(cleaned) if cleaned else None
            except ValueError:
                price = None

        # Determine image URL; some APIs may return a list of images
        image_url = None
        # Try typical keys
        for key in ("image", "images", "product_image", "image_url", "img"):
            if key in product and product[key]:
                if isinstance(product[key], list) and product[key]:
                    image_url = product[key][0]
                else:
                    image_url = product[key]
                break

        if not image_url:
            print(f"Warning: No image found for product {pid} ({name}); skipping image download.")
            filename = ""
        else:
            # Strip resolution suffix from the URL
            high_res_url = strip_resolution_suffix(str(image_url))
            # Determine file extension from URL
            parsed_name = sanitize_filename(high_res_url)
            # If the filename still contains resolution, remove again for safety
            parsed_name = re.sub(r"_\d{2,5}x\d{2,5}(?=\.[A-Za-z]+$)", "", parsed_name)
            dest_file_path = os.path.join(category_folder, parsed_name)
            # Download the image
            success = download_image(session, high_res_url, dest_file_path)
            if success:
                filename = parsed_name
            else:
                filename = ""

        products_list.append(Product(id=pid, name=name, price=price, description=description, image=filename))

        # Respectful delay between product downloads
        time.sleep(1)

    # Write products.json
    json_path = os.path.join(category_folder, "products.json")
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            # Convert dataclass objects to dicts
            json.dump([p.__dict__ for p in products_list], f, ensure_ascii=False, indent=2)
        print(f"Wrote {len(products_list)} products to {json_path}")
    except Exception as exc:
        print(f"Warning: Failed to write JSON for category {category_id}: {exc}")


def main() -> None:
    """Main entry point for the scraping script."""
    with requests.Session() as session:
        # Authenticate with the site
        logged_in = login(session)
        if not logged_in:
            print("Failed to log in. Scraping cannot proceed without authentication.")
            return
        # Iterate through all categories
        for cid in CATEGORY_IDS:
            try:
                process_category(session, cid)
            except Exception as exc:
                print(f"Error processing category {cid}: {exc}")
            # Add a delay between categories
            time.sleep(2)


if __name__ == "__main__":
    main()