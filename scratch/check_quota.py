import os
import requests
import json
from dotenv import load_dotenv

load_dotenv(override=True)
api_key = os.getenv("OPENROUTER_API_KEY", "")

url = "https://openrouter.ai/api/v1/key"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

try:
    print("Checking OpenRouter account credit and limits...")
    resp = requests.get(url, headers=headers, timeout=20)
    print(f"Status Code: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print("\n--- ACCOUNT KEY LIMITS & CREDIT ---")
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(f"Error checking key: {resp.text}")
except Exception as e:
    print(f"Exception raised: {e}")
