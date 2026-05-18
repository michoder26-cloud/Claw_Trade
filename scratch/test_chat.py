import os
import requests
import json
from dotenv import load_dotenv

# Load env
load_dotenv(override=True)
api_key = os.getenv("OPENROUTER_API_KEY", "")

url = "https://openrouter.ai/api/v1/chat/completions"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://github.com/antigravity/xau_trading_system",
    "X-Title": "XAU Trading Bot Test"
}

payload = {
    "model": "deepseek/deepseek-chat",
    "messages": [{"role": "user", "content": "Say hello!"}],
    "temperature": 0.2,
    "max_tokens": 100
}

try:
    print("Sending request to OpenRouter...")
    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    print(f"Status Code: {resp.status_code}")
    print("Response JSON Body:")
    print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
except Exception as e:
    print(f"Exception raised: {e}")
