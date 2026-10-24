import requests, json, sys
url='http://127.0.0.1:8000/ask'
payload={'question':'ما هو تعريف العقد؟'}
try:
    resp=requests.post(url, json=payload, timeout=10)
    print('status', resp.status_code)
    print('response', resp.text)
except Exception as e:
    print('error', e)
