FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_ENV=production \
    WHISPER_MODEL_SIZE=base \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

WORKDIR /app

# GigaChat requires the Russian national CA chain. Obtain it from the
# official Gosuslugi distribution URL, as documented by Sber.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl libgomp1 && \
    curl -kfsSL https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt \
      -o /usr/local/share/ca-certificates/russian_trusted_root_ca_pem.crt && \
    curl -kfsSL https://gu-st.ru/content/lending/russian_trusted_sub_ca_pem.crt \
      -o /usr/local/share/ca-certificates/russian_trusted_sub_ca_pem.crt && \
    update-ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 8501

CMD ["python", "-m", "streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", "--server.enableCORS=false"]
