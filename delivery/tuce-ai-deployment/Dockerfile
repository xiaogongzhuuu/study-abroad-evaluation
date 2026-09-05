FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY agent/requirements.txt /app/agent/requirements.txt
RUN pip install --no-cache-dir -r agent/requirements.txt && useradd --uid 10001 --create-home appuser
COPY agent/app /app/agent/app
COPY web/static /app/web/static
RUN mkdir -p /app/data && chown appuser:appuser /app/data
USER appuser
WORKDIR /app/agent
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=172.16.0.0/12"]
