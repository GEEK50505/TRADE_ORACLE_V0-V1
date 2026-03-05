import requests
from config import settings

print("Base URL:", settings.MATCH_TRADER_BASE_URL)

try:
    resp = requests.get(settings.MATCH_TRADER_BASE_URL, timeout=5)
    print("Status code", resp.status_code)
    print("Response snippet", resp.text[:200])
except Exception as e:
    print("Connection error:", e)
