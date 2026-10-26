import sys

import requests

url='http://127.0.0.1:11434/v1/models'
try:
    r=requests.get(url, timeout=5)
    print('Status', r.status_code)
    print('Body', r.text)
except Exception as e:
    print('Error', e)
    sys.exit(1)
