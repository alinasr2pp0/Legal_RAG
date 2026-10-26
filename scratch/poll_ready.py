import sys
import time

import requests

url='http://127.0.0.1:8002/ready'
for i in range(6):
    try:
        r=requests.get(url, timeout=15)
        print(f'Attempt {i} status {r.status_code}')
        if r.status_code==200:
            print('Ready payload:', r.text)
            sys.exit(0)
    except Exception as e:
        print(f'Attempt {i} error', e)
    time.sleep(5)
print('Failed after retries')
sys.exit(1)
