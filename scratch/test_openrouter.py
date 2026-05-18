import os
import requests
import json
from dotenv import load_dotenv

# Load env
load_dotenv(override=True)
api_key = os.getenv("OPENROUTER_API_KEY", "")

print(f"API Key length: {len(api_key)}")
print(f"API Key prefix: {api_key[:10]}...")

url = "https://openrouter.ai/api/v1/models"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

try:
    resp = requests.get(url, headers=headers, timeout=30)
    print(f"Response HTTP Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        models = data.get("data", [])
        print(f"Total available models: {len(models)}")
        
        # Look for free models or specific ones
        free_models = [m.get("id") for m in models if "free" in m.get("id", "")]
        print(f"\nFree models found ({len(free_models)}):")
        for fm in free_models:
            print(f" - {fm}")
            
        # Check specific models
        targets = ["deepseek/deepseek-r1:free", "google/gemini-2.0-flash-exp:free", "meta-llama/llama-3.1-8b-instruct:free"]
        print("\nChecking target models in listing:")
        all_ids = [m.get("id") for m in models]
        for t in targets:
            found = t in all_ids
            print(f" - {t}: {'FOUND' if found else 'NOT FOUND'}")
            
    else:
        print(f"Error body: {resp.text}")
except Exception as e:
    print(f"Exception raised: {e}")
