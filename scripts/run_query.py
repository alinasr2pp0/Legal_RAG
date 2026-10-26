import os

import requests

# Ensure UTF-8 output
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

def ask(question: str, host: str = '127.0.0.1', port: int = 8001):
    url = f'http://{host}:{port}/ask'
    payload = {'question': question}
    try:
        resp = requests.post(url, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        print('=== Answer ===')
        print(data.get('answer', '(no answer)'))
        print('\n=== Sources ===')
        for src in data.get('sources', []):
            print(f"Article {src.get('article_number')}: {src.get('citation')}")
        crit = data.get('critic')
        if crit:
            print('\n=== Critic ===')
            print(f"Passed: {crit.get('passed')}, Grounding: {crit.get('grounding')}")
    except Exception as e:
        print('Error during request:', e)

if __name__ == '__main__':
    ask('ما شروط صحة العقد')
