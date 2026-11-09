# Python 3.13 matches the version the service already runs on Render (PYTHON_VERSION=3.13.5)
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# psycopg2-binary ships its own libpq, so no system packages / build tools are needed.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home --uid 1000 appuser && chown -R appuser /app
USER appuser

EXPOSE 10000

# Free plan has no pre-deploy command, so run migrations at container start.
CMD ["sh", "-c", "flask --app run db upgrade && gunicorn run:app --bind 0.0.0.0:${PORT:-10000} --workers 2 --timeout 60"]
