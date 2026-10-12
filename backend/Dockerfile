FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock .
RUN --mount=type=secret,id=cloud-ca if [ -f /run/secrets/cloud-ca ]; then export PIP_CERT=/run/secrets/cloud-ca; fi; pip install --no-cache-dir --require-hashes -r requirements.lock && useradd --create-home app
COPY --chown=app:app . .
USER app
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--proxy-headers","--forwarded-allow-ips","*"]
