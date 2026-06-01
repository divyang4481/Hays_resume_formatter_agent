FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY src /app/src
ENV PYTHONPATH=/app

# Report healthy when either:
# - API mode responds on /health, or
# - worker mode process is running.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD python -c "import os,sys,urllib.request; api_ok=False; worker_ok=False; \
try:\
	api_ok = urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200\
except Exception:\
	api_ok = False; \
for p in os.listdir('/proc'):\
	if not p.isdigit():\
		continue;\
	try:\
		cmd = open('/proc/%s/cmdline' % p, 'rb').read().decode('utf-8', 'ignore').replace('\\x00', ' ')\
	except Exception:\
		continue;\
	if 'src.worker.main' in cmd:\
		worker_ok = True;\
		break;\
sys.exit(0 if (api_ok or worker_ok) else 1)"
