import requests
import json
from datetime import datetime
import os

def download_json_data():
    """
    Download JSON data from JK Cabinetry products API and save with timestamp
    """
    url = "https://www.jkcabinetry.com/products.json?limit=1000"
    
    try:
        print("Downloading JSON data...")
        print(f"URL: {url}")
        
        # Make the HTTP request
        response = requests.get(url, timeout=30)
        
        # Check if request was successful
        response.raise_for_status()
        
        # Parse JSON data
        json_data = response.json()
        
        # Create filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_products.json"
        
        # Save to file
        with open(filename, 'w', encoding='utf-8') as file:
            json.dump(json_data, file, indent=2, ensure_ascii=False)
        
        # Get file size
        file_size = os.path.getsize(filename)
        file_size_mb = file_size / (1024 * 1024)
        
        print(f"✅ Success!")
        print(f"📁 File saved as: {filename}")
        print(f"📊 File size: {file_size_mb:.2f} MB ({file_size:,} bytes)")
        print(f"📈 Records count: {len(json_data) if isinstance(json_data, list) else 'N/A'}")
        
        return filename
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error occurred: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ JSON parsing error: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return None

if __name__ == "__main__":
    print("🔄 Starting JSON download process...")
    print("-" * 50)
    
    result = download_json_data()
    
    print("-" * 50)
    if result:
        print(f"🎉 Download completed successfully!")
        print(f"📍 File location: {os.path.abspath(result)}")
    else:
        print("💥 Download failed. Please check the error messages above.")