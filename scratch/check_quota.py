import os
import requests
import json
import sys
import io
from dotenv import load_dotenv

# Fix encoding on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Load env variables
load_dotenv(override=True)
api_key = os.getenv("OPENROUTER_API_KEY", "")

url = "https://openrouter.ai/api/v1/auth/key"
headers = {
    "Authorization": f"Bearer {api_key}"
}

try:
    print("Checking OpenRouter API Key Status...")
    resp = requests.get(url, headers=headers, timeout=15)
    
    if resp.status_code == 200:
        data = resp.json().get("data", {})
        print("\n" + "="*50)
        print(" [KEY QUOTA REPORT]")
        print("="*50)
        print(f"Key Label       : {data.get('label', 'Unnamed')}")
        print(f"Is Active?      : {data.get('is_active', True)}")
        
        # Credit Info
        usage = data.get("usage", 0.0)
        limit = data.get("limit")
        print(f"Usage Balance   : ${usage:.6f} spent")
        
        if limit is not None:
            print(f"Daily Limit     : ${limit:.2f}")
            print(f"Remaining Limit : ${max(0.0, limit - usage):.6f}")
        else:
            print("Daily Limit     : No hard limit set")
            
        # Rate limits info
        rate_limit = data.get("rate_limit", {})
        if rate_limit:
            print(f"Requests Limit  : {rate_limit.get('requests', 'N/A')} requests")
            print(f"Interval        : {rate_limit.get('interval', 'N/A')}")
        
        print("="*50)
    else:
        print("Error details:")
        print(resp.text)
        
except Exception as e:
    print(f"An error occurred: {e}")
