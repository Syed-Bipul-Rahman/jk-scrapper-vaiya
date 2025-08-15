"""
scrape_products_3.py
======================

This script is a fully self‑contained web scraper designed to extract
product information from the public J&K Cabinetry website. Unlike the
prior attempt, it does not rely on proprietary API endpoints (which
returned 403 errors) but instead crawls each collection page on the
J&K site directly. The goal is to gather product data for roughly
25 cabinet categories across every available cabinet line (style) and
save the results in a structured manner.

Key features
------------

* **Category mapping** – Each of the 25 category IDs provided by the
  user is mapped to a human‑friendly name and a collection slug. The
  slug reflects the pattern used on the website (e.g., ``sink-base-cabinet``)
  and is combined with a cabinet line code (``s8``, ``a7``, etc.) to
  construct URLs like ``https://www.jkcabinetry.com/collections/s8-sink-base-cabinet``.

* **Style discovery** – A hard‑coded list of cabinet line codes
  (e.g. ``s8``, ``s1``, ``s2``, ``s5``, ``k3``, ``h9``, ``h8``, ``h3``,
  ``a7``, ``c066``, ``m01``, ``k10``, ``k8``, ``j5``) is iterated for
  each category. If a particular style does not offer a given
  category, the script simply skips that combination.

* **Pagination support** – Collection pages often span multiple
  pages. The scraper follows ``?page=N`` links until no new product
  cards are found.

* **Product page parsing** – For each product URL discovered,
  ``parse_product_page`` fetches the full detail page, extracts
  identifiers, names, prices, descriptions and the primary image
  URL. Resolution suffixes (e.g. ``_352x192``) are removed to obtain
  high‑resolution images. The images are downloaded and stored
  alongside a JSON record.

* **Graceful error handling** – Network timeouts, HTML parsing
  irregularities and missing elements are handled gracefully. The
  scraper logs warnings and continues processing without aborting
  entirely. Delays are inserted between requests to reduce the risk
  of being rate limited.

Usage
-----

To run the scraper, simply execute this file with Python 3. It
requires the ``requests`` and ``beautifulsoup4`` packages. The
credentials provided by the user are optional: many product pages are
publicly visible without logging in. However, if certain details are
hidden behind authentication, the script will attempt to log in using
the supplied email and password.

    python scrape_products_3.py

The results are written into an ``output/`` directory. Each category
ID has its own subfolder containing a ``products.json`` file and the
downloaded high‑resolution images.

Limitations
-----------

* **Network access** – This script assumes you have internet
  connectivity to ``www.jkcabinetry.com``. It will not function in
  restricted environments where outbound connections are blocked.
* **Site changes** – If J&K Cabinetry redesigns its site or changes
  the HTML structure of collection or product pages, some parsing
  logic may need to be updated. The current implementation uses
  generic patterns (e.g. product cards and metadata tags) to remain
  resilient, but no parser is completely future‑proof.
* **Login** – The login workflow is rudimentary. It performs a
  best‑effort form submission but may not handle complex
  authentication challenges such as CAPTCHAs or multifactor prompts.
"""

import json
import os
import re
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Set, Tuple

import requests
from bs4 import BeautifulSoup
import html  # Added to unescape HTML entities in Shopify JSON blobs


# -----------------------------------------------------------------------------
# Configuration
#
# Update these values with the credentials provided by the user. If the site
# exposes pricing and descriptions publicly, leaving EMAIL and PASSWORD blank
# will still allow the scraper to run.

EMAIL: str = "Ngobuildersinc@gmail.com"
PASSWORD: str = "Hammer2025!"

# Base URL for the J&K Cabinetry website. Trailing slash omitted so
# paths can be concatenated cleanly.
BASE_URL: str = "https://www.jkcabinetry.com"

# Cabinet line codes (styles). You can add or remove codes here if J&K
# introduces new lines or deprecates existing ones. These values
# correspond to the prefixes used on the site (e.g. ``s8`` for S8
# White Shaker, ``a7`` for A7 Crème Glazed). They should always be
# lowercase.
STYLE_CODES: List[str] = [
    "s8",  # S8 White Shaker
    "s1",  # S1 / S1 Espresso
    "s2",  # S2 / S2 Almond
    "s5",  # S5 / S5 Mocha
    "k3",  # K3 / K3 Greige
    "h9",  # H9 / H9 Pearl Glazed
    "h8",  # H8 / H8 Hazel
    "h3",  # H3 / H3 Chestnut
    "a7",  # A7 / A7 Crème Glazed
    "c066",  # C066 / Chocolate
    "m01",  # M01 / Mahogany Red
    "k10",  # K10 / K10 Smoke Gray
    "k8",  # K8 / K8 Espresso
    "j5",  # J5 / J5 Greige
]

# Mapping of category identifiers to human names and slugs. The slug
# corresponds to the path after the style prefix in the collection URL.
CATEGORY_MAPPING: List[Dict[str, str]] = [
    {"id": "689cba9eca19d8fef712c080", "name": "Sink Base Cabinet", "slug": "sink-base-cabinet"},
    {"id": "689cbaa6ca19d8fef712c087", "name": "Vanity Cabinet", "slug": "vanity-cabinet"},
    {"id": "689cbac5ca19d8fef712c094", "name": "Wall Cabinet", "slug": "wall-cabinet"},
    {"id": "689cbad7ca19d8fef712c09b", "name": "Wall Diagonal Cabinet", "slug": "wall-diagonal-cabinet"},
    {"id": "689cbae2ca19d8fef712c0a3", "name": "Wall Shelf Cabinet", "slug": "wall-shelf-cabinet"},
    {"id": "689d86fbca19d8fef712c6b1", "name": "Pantry Cabinet", "slug": "pantry-cabinet"},
    {"id": "689d8704ca19d8fef712c6ba", "name": "Oven Cabinet", "slug": "oven-cabinet"},
    {"id": "689d8713ca19d8fef712c6d5", "name": "Wall Glass Cabinet", "slug": "wall-glass-cabinet"},
    {"id": "689d871fca19d8fef712c6e4", "name": "Wall Diagonal Glass Cabinet", "slug": "wall-diagonal-glass-cabinet"},
    {"id": "689d8727ca19d8fef712c6ec", "name": "Glass Frame", "slug": "glass-frame"},
    {"id": "689d9e2dca19d8fef712c918", "name": "Base Cabinet", "slug": "base-cabinets-collection"},
    {"id": "689d9e36ca19d8fef712c91f", "name": "Drawer Base Cabinet", "slug": "drawer-base-cabinet"},
    {"id": "689d9e3fca19d8fef712c927", "name": "Corner Base Cabinet", "slug": "corner-base-cabinet"},
    {"id": "689d8758ca19d8fef712c70a", "name": "Molding", "slug": "molding"},
    {"id": "689d8761ca19d8fef712c711", "name": "Filler", "slug": "filler"},
    {"id": "689d8769ca19d8fef712c719", "name": "Base Filler", "slug": "base-filler"},
    {"id": "689d8770ca19d8fef712c722", "name": "Wall Filler", "slug": "wall-filler"},
    {"id": "689d8798ca19d8fef712c745", "name": "Sample Door", "slug": "sample-door"},
    {"id": "689d879eca19d8fef712c74c", "name": "Touchup", "slug": "touchup"},
    {"id": "689d87a5ca19d8fef712c75c", "name": "Turn Post", "slug": "turn-post"},
    {"id": "689d87abca19d8fef712c76b", "name": "Corbel", "slug": "corbel"},
    {"id": "689d87b2ca19d8fef712c775", "name": "Accessory", "slug": "accessory"},
    {"id": "689d87bdca19d8fef712c780", "name": "Valance", "slug": "valance"},
    {"id": "689d87c6ca19d8fef712c78c", "name": "Knee Drawer", "slug": "knee-drawer"},
    {"id": "689d87ceca19d8fef712c799", "name": "Roll-Out Trays", "slug": "roll-out-trays"},
]


@dataclass
class Product:
    """Represents a single product scraped from the J&K Cabinetry website."""

    id: str
    name: str
    price: Optional[float]
    description: str
    image: str  # local filename of the downloaded high‑resolution image


def sanitize_filename(filename: str) -> str:
    """Sanitize filenames to remove characters unsafe for filesystems.

    Args:
        filename: Raw filename extracted from the image URL.

    Returns:
        A safe filename with problematic characters replaced by underscores.
    """
    # Remove any query string
    filename = filename.split("?")[0]
    # Use basename to discard any path
    filename = os.path.basename(filename)
    # Replace disallowed characters with underscores
    filename = re.sub(r"[^A-Za-z0-9_.-]", "_", filename)
    return filename


def strip_resolution_suffix(url: str) -> str:
    """Remove resolution suffix patterns (e.g. ``_352x192``) from an image URL.

    J&K product images include suffixes in their filenames to indicate
    different resolutions. To retrieve the full‑size image, these
    suffixes must be stripped before the file extension.

    Args:
        url: Image URL containing a low‑resolution suffix.

    Returns:
        The URL without the resolution suffix, preserving any query
        parameters.
    """
    # Separate URL into base and query
    base, sep, query = url.partition("?")
    # Remove patterns like _123x456 before the file extension
    new_base = re.sub(r"_(\d{2,5}x\d{2,5})(?=\.[A-Za-z]+$)", "", base)
    return new_base + (sep + query if sep else "")


def login(session: requests.Session) -> bool:
    """Attempt to log in to the J&K Cabinetry website.

    The site presents its login form in an iframe which may not be
    accessible via direct HTML scraping, but many product pages are
    publicly accessible without authentication. This function is
    nevertheless provided in case login becomes necessary for certain
    categories or to view wholesale pricing. It performs a GET
    request to obtain cookies and hidden form fields, then submits
    the credentials via POST.

    Args:
        session: A persistent ``requests.Session`` object.

    Returns:
        True if login appears to be successful, False otherwise.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            " AppleWebKit/537.36 (KHTML, like Gecko)"
            " Chrome/122.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        print("Fetching login page…")
        resp = session.get(f"{BASE_URL}/account/login", headers=headers, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        # Find form containing a password input
        form = None
        for frm in soup.find_all("form"):
            if frm.find("input", {"type": "password"}):
                form = frm
                break
        if not form:
            print("No login form found; skipping authentication.")
            return False
        action = form.get("action") or "/account/login"
        login_url = action if action.startswith("http") else requests.compat.urljoin(BASE_URL, action)
        payload: Dict[str, str] = {}
        for inp in form.find_all("input"):
            name = inp.get("name")
            if not name:
                continue
            value = inp.get("value", "")
            payload[name] = value
        # Populate credentials based on common names
        inserted_email = False
        inserted_password = False
        for key in list(payload.keys()):
            lower = key.lower()
            if "email" in lower or "username" in lower or "customer[email]" in lower:
                payload[key] = EMAIL
                inserted_email = True
            elif "pass" in lower:
                payload[key] = PASSWORD
                inserted_password = True
        if not inserted_email:
            payload["email"] = EMAIL
        if not inserted_password:
            payload["password"] = PASSWORD
        print(f"Submitting login credentials to {login_url}…")
        post_resp = session.post(login_url, headers=headers, data=payload, timeout=20)
        # A successful login may cause a redirect
        if post_resp.history and any(r.status_code in (301, 302) for r in post_resp.history):
            print("Login redirect detected; assuming success.")
            return True
        if "logout" in post_resp.text.lower() or "my account" in post_resp.text.lower():
            print("Logged in successfully.")
            return True
        print("Login may not have succeeded.")
        return False
    except Exception as exc:
        print(f"Error during login: {exc}")
        return False


def get_soup(session: requests.Session, url: str) -> Optional[BeautifulSoup]:
    """Fetch a URL and return a BeautifulSoup object on success.

    Args:
        session: ``requests.Session`` used for persistent connections.
        url: The URL to fetch.

    Returns:
        A BeautifulSoup instance if the request succeeds (HTTP 200) and the
        content is HTML; otherwise ``None``.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            " AppleWebKit/537.36 (KHTML, like Gecko)"
            " Chrome/122.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        response = session.get(url, headers=headers, timeout=30)
        if response.status_code != 200:
            return None
        return BeautifulSoup(response.text, "html.parser")
    except Exception:
        return None


def parse_product_card(card: BeautifulSoup) -> Optional[str]:
    """Extract the product page URL from a product card element.

    Each collection page lists products as cards or grid items. This
    helper takes a card (e.g. a `<div>` or `<li>` element) and finds the
    anchor pointing to the product page. It returns a relative URL or
    full URL, depending on what the page contains.

    Args:
        card: A BeautifulSoup element representing a product.

    Returns:
        The product URL if found, else ``None``.
    """
    # Look for an <a> tag that links to a product. Often it's the first
    # anchor within the card.
    link = card.find("a", href=True)
    if not link:
        return None
    href = link["href"]
    return href.strip()


def parse_collection_page(session: requests.Session, collection_url: str) -> List[str]:
    """Parse a collection page and return all product URLs found on that page.

    Args:
        session: A ``requests.Session`` for HTTP requests.
        collection_url: The full URL to a specific page of a collection.

    Returns:
        A list of relative or absolute product URLs extracted from the page.
    """
    soup = get_soup(session, collection_url)
    if soup is None:
        return []
    product_urls: List[str] = []
    # First attempt: extract product URLs from Shopify's data-events JSON embedded
    # in a script tag. This is more reliable than parsing HTML which may be
    # rendered client side. The script tag looks like:
    # <script ... data-events="[[&quot;page_viewed&quot;,{}],[&quot;collection_viewed&quot;,{...productVariants...}]]" ...></script>
    try:
        scripts = soup.find_all('script', attrs={'data-events': True})
        for s in scripts:
            raw_events = s.get('data-events')
            if not raw_events:
                continue
            # Unescape HTML entities (&quot; -> ")
            decoded = html.unescape(raw_events)
            # Parse JSON
            events = json.loads(decoded)
            # events is expected to be a list like [["page_viewed",{}], ["collection_viewed", {...}]]
            for ev in events:
                if isinstance(ev, list) and len(ev) == 2 and ev[0] == 'collection_viewed':
                    details = ev[1]
                    # Navigate to collection.productVariants
                    collection_info = details.get('collection') if isinstance(details, dict) else None
                    if collection_info and isinstance(collection_info, dict):
                        variants = collection_info.get('productVariants')
                        if variants and isinstance(variants, list):
                            for variant in variants:
                                prod = variant.get('product') if isinstance(variant, dict) else None
                                if prod and isinstance(prod, dict):
                                    url = prod.get('url')
                                    if url:
                                        # Ensure URL is relative or absolute
                                        product_urls.append(url.strip())
            # If we successfully parsed at least one product from this script, no need to parse others
            if product_urls:
                break
    except Exception:
        # If any parsing error occurs, we fall back to HTML parsing below
        product_urls = []
    # Fallback: parse HTML elements if JSON extraction fails
    if not product_urls:
        selectors = [
            "div.grid__item",  # general grid items
            "div.product-card",  # older theme
            "li.grid__item",
            "li.product-card",
        ]
        cards: List[BeautifulSoup] = []
        for sel in selectors:
            cards = soup.select(sel)
            if cards:
                break
        if not cards:
            # As a last resort, look for any anchor tags within elements whose
            # class contains the word 'product'. This may capture items on
            # unpredictable themes.
            for elem in soup.find_all(True, class_=re.compile("product")):
                anchor = elem.find("a", href=True)
                if anchor and anchor['href']:
                    product_urls.append(anchor['href'].strip())
            return product_urls
        for card in cards:
            url = parse_product_card(card)
            if url:
                product_urls.append(url)
    return product_urls


def parse_product_page(session: requests.Session, product_url: str) -> Optional[Tuple[Product, str]]:
    """Parse a product page and return a ``Product`` and high‑res image URL.

    Args:
        session: ``requests.Session`` used for making the request.
        product_url: The relative or absolute URL to the product page.

    Returns:
        A tuple ``(Product, image_url)`` if parsing succeeds; otherwise
        ``None``. The ``image_url`` is the URL to download (after
        stripping resolution suffix).
    """
    # Normalize product URL
    if not product_url.startswith("http"):
        product_url = requests.compat.urljoin(BASE_URL, product_url)
    soup = get_soup(session, product_url)
    if soup is None:
        return None
    try:
        # Extract product title. J&K uses <h1 class="product-title"> or
        # <h1 itemprop="name">. We'll try multiple selectors.
        title_elem = soup.find("h1")
        title = title_elem.get_text(strip=True) if title_elem else ""
        # Product ID can often be the first token in the title (e.g. "S8/SB30").
        product_id_match = re.search(r"([A-Za-z0-9]+/[A-Za-z0-9]+)", title)
        product_id = product_id_match.group(1) if product_id_match else title
        # Price: look for elements containing currency signs
        price = None
        price_elem = soup.find(class_=re.compile("price"))
        if price_elem:
            price_text = price_elem.get_text(strip=True)
            # Remove currency symbols and commas
            cleaned = re.sub(r"[^0-9.]+", "", price_text)
            if cleaned:
                try:
                    price = float(cleaned)
                except ValueError:
                    price = None
        # Description: look for product description containers
        desc = ""
        # Try multiple possible containers for description
        desc_selectors = [
            "div.product-description",
            "div#ProductDescription",
            "div#product_description",
            "div[itemprop='description']",
        ]
        for sel in desc_selectors:
            desc_elem = soup.select_one(sel)
            if desc_elem:
                desc = desc_elem.get_text(" ", strip=True)
                break
        if not desc:
            # Fallback: take the meta description
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc:
                desc = meta_desc.get("content", "").strip()
        # Image: use og:image meta tag as a reliable source
        image_url = ""
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            image_url = og_image["content"].strip()
        else:
            # Try to locate the first <img> within a gallery or image wrapper
            img_elem = soup.find("img", src=True)
            if img_elem:
                image_url = img_elem["src"].strip()
        if not image_url:
            # If no image found, return without raising
            return None
        # Strip resolution suffix for high‑resolution
        high_res_url = strip_resolution_suffix(image_url)
        # Derive image filename
        filename = sanitize_filename(high_res_url)
        # Remove any remaining resolution suffixes in filename
        filename = re.sub(r"_\d{2,5}x\d{2,5}(?=\.[A-Za-z]+$)", "", filename)
        product = Product(
            id=product_id,
            name=title,
            price=price,
            description=desc,
            image=filename,
        )
        return product, high_res_url
    except Exception:
        return None


def download_image(session: requests.Session, url: str, dest_path: str) -> bool:
    """Download an image and save it to ``dest_path``.

    Args:
        session: An authenticated or anonymous ``requests.Session``.
        url: URL of the image to download.
        dest_path: File path where the image will be written.

    Returns:
        True if the download succeeded, False otherwise.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            " AppleWebKit/537.36 (KHTML, like Gecko)"
            " Chrome/122.0 Safari/537.36",
        }
        resp = session.get(url, headers=headers, timeout=40)
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            f.write(resp.content)
        return True
    except Exception as exc:
        print(f"Warning: Failed to download image {url}: {exc}")
        return False


def process_category(session: requests.Session, category: Dict[str, str]) -> None:
    """Scrape all products for a given category across every style.

    This function iterates through each cabinet line code in ``STYLE_CODES``
    and constructs the collection URL by combining the style and category
    slug. It follows pagination links to collect every product URL, then
    visits each product page to extract details and download images. The
    final results are deduplicated by product ID and written to
    ``output/<category_id>/products.json``.

    Args:
        session: A ``requests.Session`` with any necessary cookies.
        category: A dictionary containing ``id``, ``name`` and ``slug`` for
            the target category.
    """
    cid = category["id"]
    slug = category["slug"]
    print(f"\nScraping category: {cid} – {category['name']}…")
    # Create directory for this category
    category_folder = os.path.join("output", cid)
    os.makedirs(category_folder, exist_ok=True)
    # Use a dict to avoid duplicate products across styles
    collected: Dict[str, Product] = {}
    for style in STYLE_CODES:
        # Build base collection URL (without page param)
        base_collection = f"{BASE_URL}/collections/{style}-{slug}"
        # Track product URLs we've seen for this style to detect when
        # pagination repeats. Without this check, some collections may
        # return the same items on every page, leading to an infinite loop.
        seen_links: Set[str] = set()
        page = 1
        max_pages = 20  # fail safe to prevent infinite loops
        while page <= max_pages:
            url = base_collection if page == 1 else f"{base_collection}?page={page}"
            # Fetch product URLs on this page
            product_links = parse_collection_page(session, url)
            if not product_links:
                # No products found on this page – either the style
                # doesn't offer this category or we've reached the end of
                # pagination.
                break
            # Filter out links we've already processed for this style
            new_links = []
            for link in product_links:
                # Normalize to absolute URL
                full_url = link if link.startswith("http") else requests.compat.urljoin(BASE_URL, link)
                # Remove query params and fragments for deduplication
                key = re.sub(r"[/?#].*$", "", full_url)
                if key not in seen_links:
                    seen_links.add(key)
                    new_links.append(full_url)
            # If no new links were found, break to avoid cycling
            if not new_links:
                break
            for full_url in new_links:
                # Skip if we've already collected this product across styles
                key = re.sub(r"[/?#].*$", "", full_url)
                if key in collected:
                    continue
                # Parse product page
                result = parse_product_page(session, full_url)
                if not result:
                    continue
                product, img_url = result
                # Download the image
                dest_img_path = os.path.join(category_folder, product.image)
                if product.image and not os.path.exists(dest_img_path):
                    download_image(session, img_url, dest_img_path)
                # Add to collection
                collected[key] = product
                time.sleep(1)  # polite delay between product requests
            # Proceed to next page
            page += 1
            time.sleep(1)  # delay between pages
    # Write JSON file
    json_path = os.path.join(category_folder, "products.json")
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump([asdict(prod) for prod in collected.values()], f, ensure_ascii=False, indent=2)
        print(f"Finished {category['name']}: {len(collected)} products saved to {json_path}")
    except Exception as exc:
        print(f"Warning: Failed to write products.json for {cid}: {exc}")


def main() -> None:
    """Main entry point for the scraper."""
    # Prepare output directory
    os.makedirs("output", exist_ok=True)
    with requests.Session() as session:
        # Perform login if credentials are provided
        if EMAIL and PASSWORD:
            logged_in = login(session)
            if not logged_in:
                print("Continuing without login – some prices may be hidden.")
        # Iterate through each category
        for category in CATEGORY_MAPPING:
            try:
                process_category(session, category)
            except Exception as exc:
                print(f"Error processing category {category['id']}: {exc}")
            # Pause between categories
            time.sleep(2)


if __name__ == "__main__":
    main()