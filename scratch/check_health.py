import requests, json, sys
url='http://127.0.0.1:8002/health'
try:
    r=requests.get(url, timeout=5)
    print('Status', r.status_code)
    print('Body', r.text)
except Exception as e:
    print('Error', e)
