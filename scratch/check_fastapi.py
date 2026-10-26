import sys

import requests

base='http://127.0.0.1:8002'
for ep in ['/health','/ready']:
    try:
        r=requests.get(base+ep, timeout=5)
        print(ep, 'status', r.status_code)
        print('body', r.text)
    except Exception as e:
        print(ep, 'error', e)
        sys.exit(1)
