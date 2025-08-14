#!/usr/bin/env python3
"""
Comprehensive Python script for sending multipart form data requests to API
Author: Generated Script
Description: Sends POST request with form data including file upload
"""

import requests
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any, Union
import mimetypes

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('api_requests.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

class APIClient:
    """
    API Client for handling requests to the server
    """
    
    def __init__(self, base_url: str, access_token: str):
        """
        Initialize API client
        
        Args:
            base_url (str): Base URL of the API
            access_token (str): JWT access token for authentication
        """
        self.base_url = base_url.rstrip('/')
        self.access_token = access_token
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {self.access_token}',
            'User-Agent': 'Python-API-Client/1.0'
        })
    
    def create_parts(
        self, 
        title: str,
        sub_title: str,
        description: str,
        price: Union[str, float],
        image_path: str,
        endpoint_id: str = "689cba9eca19d8fef712c080"
    ) -> Dict[str, Any]:
        """
        Create parts using multipart form data
        
        Args:
            title (str): Title of the part
            sub_title (str): Subtitle of the part
            description (str): Description of the part
            price (Union[str, float]): Price of the part
            image_path (str): Path to the image file
            endpoint_id (str): Endpoint ID for the API call
            
        Returns:
            Dict[str, Any]: API response
        """
        url = f"{self.base_url}/parts/create-parts/{endpoint_id}"
        
        # Validate image file exists
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image file not found: {image_path}")
        
        # Prepare form data
        form_data = {
            'title': (None, str(title)),
            'subTitle': (None, str(sub_title)),
            'description': (None, str(description)),
            'price': (None, str(price))
        }
        
        # Prepare file data
        file_name = Path(image_path).name
        mime_type = mimetypes.guess_type(image_path)[0] or 'application/octet-stream'
        
        try:
            with open(image_path, 'rb') as image_file:
                files = {
                    'images': (file_name, image_file, mime_type)
                }
                
                logger.info(f"Sending request to: {url}")
                logger.info(f"Form data: {json.dumps({k: v[1] for k, v in form_data.items()}, indent=2)}")
                logger.info(f"File: {file_name} ({mime_type})")
                
                # Make the request
                response = self.session.post(
                    url=url,
                    data=form_data,
                    files=files,
                    timeout=30
                )
                
                return self._handle_response(response)
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            raise
    
    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        """
        Handle API response
        
        Args:
            response (requests.Response): Response object
            
        Returns:
            Dict[str, Any]: Processed response
        """
        logger.info(f"Response Status Code: {response.status_code}")
        logger.info(f"Response Headers: {dict(response.headers)}")
        
        try:
            response_data = response.json()
        except ValueError:
            response_data = {"raw_content": response.text}
        
        result = {
            "status_code": response.status_code,
            "success": response.status_code < 400,
            "data": response_data,
            "headers": dict(response.headers)
        }
        
        if response.status_code < 400:
            logger.info("Request successful!")
            logger.info(f"Response: {json.dumps(response_data, indent=2)}")
        else:
            logger.error(f"Request failed with status {response.status_code}")
            logger.error(f"Error response: {json.dumps(response_data, indent=2)}")
        
        return result
    
    def test_connection(self) -> bool:
        """
        Test API connection
        
        Returns:
            bool: True if connection is successful
        """
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=10)
            return response.status_code < 400
        except:
            return False

def main():
    """
    Main function to demonstrate API usage
    """
    # Configuration
    API_BASE_URL = "https://api.jkcabinetryct.com"
    ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiI2ODk5OGEyOGNhNmE0MmY1NTQ5MjE2MWQiLCJyb2xlIjoiYWRtaW4iLCJpYXQiOjE3NTQ5MDQ5NDQsImV4cCI6MTc1NzQ5Njk0NH0.id4ix6EgKTM739DgKVznL8Wbu9k9blCM7SHmuWYqpVE"
    
    # Sample data
    part_data = {
        "title": "joy banlga",
        "sub_title": "joy bangla", 
        "description": "joybangla",
        "price": "20",
        "image_path": "/Users/shuvosta/Desktop/jk-scrapper-vaiya/iamge.webp"  # Replace with actual image path
    }
    
    try:
        # Initialize API client
        client = APIClient(API_BASE_URL, ACCESS_TOKEN)
        
        # Test connection (optional)
        logger.info("Testing API connection...")
        if client.test_connection():
            logger.info("API connection test passed")
        else:
            logger.warning("API connection test failed, proceeding anyway...")
        
        # Create parts
        logger.info("Creating parts...")
        result = client.create_parts(**part_data)
        
        # Print results
        print("\n" + "="*50)
        print("API CALL RESULTS")
        print("="*50)
        print(f"Status Code: {result['status_code']}")
        print(f"Success: {result['success']}")
        print(f"Response Data:")
        print(json.dumps(result['data'], indent=2))
        
        if result['success']:
            print("\n✅ Parts created successfully!")
        else:
            print("\n❌ Failed to create parts")
            
    except FileNotFoundError as e:
        logger.error(f"File error: {e}")
        print(f"❌ Error: {e}")
        print("Please ensure the image file exists at the specified path")
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error: {e}")
        print(f"❌ Network Error: {e}")
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        print(f"❌ Unexpected Error: {e}")

def create_sample_request():
    """
    Alternative function for custom requests
    """
    import argparse
    
    parser = argparse.ArgumentParser(description='Send API request with custom data')
    parser.add_argument('--title', required=True, help='Title of the part')
    parser.add_argument('--subtitle', required=True, help='Subtitle of the part')
    parser.add_argument('--description', required=True, help='Description of the part')
    parser.add_argument('--price', required=True, help='Price of the part')
    parser.add_argument('--image', required=True, help='Path to image file')
    parser.add_argument('--endpoint-id', default="689cba9eca19d8fef712c080", help='Endpoint ID')
    
    args = parser.parse_args()
    
    API_BASE_URL = "https://api.jkcabinetryct.com"
    ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiI2ODk5OGEyOGNhNmE0MmY1NTQ5MjE2MWQiLCJyb2xlIjoiYWRtaW4iLCJpYXQiOjE3NTQ5MDQ5NDQsImV4cCI6MTc1NzQ5Njk0NH0.id4ix6EgKTM739DgKVznL8Wbu9k9blCM7SHmuWYqpVE"
    
    try:
        client = APIClient(API_BASE_URL, ACCESS_TOKEN)
        
        result = client.create_parts(
            title=args.title,
            sub_title=args.subtitle,
            description=args.description,
            price=args.price,
            image_path=args.image,
            endpoint_id=args.endpoint_id
        )
        
        print(json.dumps(result, indent=2))
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Check if running with command line arguments
    if len(sys.argv) > 1:
        create_sample_request()
    else:
        main()