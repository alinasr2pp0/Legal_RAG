import requests, json, time
url = 'http://127.0.0.1:8000/ask'
payload = {"question": "ما هو التعويض عن الضرر؟"}
for i in range(5):
    try:
        r = requests.post(url, json=payload, timeout=20)
        print('Status:', r.status_code)
        print('Response:', r.text)
        break
    except Exception as e:
        print('Retry', i, e)
        time.sleep(2)
