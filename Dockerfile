# --- build stage: compile mysqlclient into a wheel ----------------------------------
FROM python:3.13-slim AS build
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential pkg-config default-libmysqlclient-dev \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY pyproject.toml README.md ./
RUN pip wheel --no-cache-dir --wheel-dir /wheels "mysqlclient>=2.2.1" "gunicorn>=23" \
 && pip wheel --no-cache-dir --wheel-dir /wheels "Django>=6.0,<6.2" "djangorestframework>=3.16" "defusedxml>=0.7"

# --- runtime stage: no compilers, non-root user --------------------------------------
FROM python:3.13-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends libmariadb3 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 1000 app
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels
WORKDIR /app
COPY --chown=app:app . .
USER app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/')"
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --access-logfile -"]
