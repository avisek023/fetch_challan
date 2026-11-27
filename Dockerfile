# Official Playwright Python image with Chromium & Ubuntu Noble system libraries pre-installed
FROM mcr.microsoft.com/playwright/python:v1.58.0-noble

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HEADLESS_MODE=true \
    PORT=8080

WORKDIR /app

# Install Python dependencies first for optimal Docker layer caching
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# Copy bot source modules
COPY dom_selectors.py /app/dom_selectors.py
COPY browser_manager.py /app/browser_manager.py
COPY bot.py /app/bot.py

# Ensure temporary directory for transient PDF files is writable
RUN chmod 1777 /tmp

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\", \"8080\")}/health', timeout=3)" || exit 1

CMD ["python", "bot.py"]
