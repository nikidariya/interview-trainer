FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
COPY requirements/ requirements/
RUN pip install --no-cache-dir -r requirements.txt

# Корневой сертификат НУЦ Минцифры нужен для HTTPS-запросов к GigaChat (по документации Сбера)
RUN curl -k "https://gu-st.ru/content/Other/doc/russian_trusted_root_ca.cer" -w "\n" >> $(python -m certifi)

COPY app/ app/
COPY prompts/ prompts/

EXPOSE 8501
CMD ["python", "-m", "streamlit", "run", "app/ui.py", "--server.address=0.0.0.0", "--server.port=8501"]
