import os
import json
import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.getcwd(), '.env'))
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    print('Missing SUPABASE_URL or SUPABASE_KEY')
    raise SystemExit(1)

rest_url = f"{SUPABASE_URL}/rest/v1/account_state?id=eq.1"
headers = {
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {SUPABASE_KEY}',
    'Content-Type': 'application/json',
    'Prefer': 'return=representation'
}

print('GET before update')
resp = requests.get(rest_url, headers=headers)
print('GET status', resp.status_code)
try:
    print('GET body', resp.json())
except Exception:
    print('GET text', resp.text)

payload = {'high_watermark': 5150}
print('\nPATCHing', payload)
patch = requests.patch(rest_url, headers=headers, data=json.dumps(payload))
print('PATCH status', patch.status_code)
print('PATCH headers', patch.headers.get('content-type'))
try:
    print('PATCH body', patch.json())
except Exception:
    print('PATCH text', patch.text)

print('\nGET after update')
resp2 = requests.get(rest_url, headers=headers)
print('GET2 status', resp2.status_code)
try:
    print('GET2 body', resp2.json())
except Exception:
    print('GET2 text', resp2.text)
