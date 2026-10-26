import json
import sys

import requests

API = 'http://127.0.0.1:8001'
question = 'ما شروط صحة العقد'
url = f'{API}/ask/stream'
headers = {'Content-Type': 'application/json'}
payload = {'question': question}

try:
    resp = requests.post(url, headers=headers, json=payload, stream=True, timeout=180)
    resp.raise_for_status()
    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        # SSE lines can start with "event:" or "data:"
        if line.startswith('event:'):
            event = line.split(':', 1)[1].strip()
        elif line.startswith('data:'):
            data = line.split(':', 1)[1].lstrip()
            if event == 'status':
                print('[status] ' + data)
            elif event == 'result':
                result = json.loads(data)
                print('--- RESULT ---')
                print(json.dumps(result, ensure_ascii=False, indent=2))
                break
        # ignore other lines
except Exception as e:
    print('Error:', e, file=sys.stderr)
    sys.exit(1)
