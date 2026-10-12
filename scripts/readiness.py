"""Bounded local readiness checks; does not print credentials or create preview links."""
import os,time
import httpx
base=os.environ.get('HEALTH_BASE_URL','http://127.0.0.1:8088')
last='Services are starting'
for _ in range(30):
    try:
        with httpx.Client(timeout=2,trust_env=False) as client:
            health=client.get(base+'/api/health');health.raise_for_status()
            page=client.get(base+'/');page.raise_for_status()
            if health.json().get('status')=='ok' and 'NewHotMusic' in page.text:
                print('API database health and dashboard document verified');break
        last='Unexpected readiness response'
    except (httpx.HTTPError,ValueError) as exc: last=type(exc).__name__
    time.sleep(1)
else: raise SystemExit('Readiness failed: '+last)
