import requests, sys
url='http://127.0.0.1:8002/ready'
try:
    r=requests.get(url, timeout=30)
    print('Status', r.status_code)
    print('Body', r.text)
except Exception as e:
    print('Error', e)
    sys.exit(1)
