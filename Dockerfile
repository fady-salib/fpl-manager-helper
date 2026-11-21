# syntax=docker/dockerfile:1
FROM python:3.12-slim
ARG FPL_EXTRAS=""
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 FPL_DATA_DIR=/app/data
WORKDIR /app
RUN --mount=type=secret,id=proxy_ca \
    apt-get -o Acquire::https::CaInfo=/run/secrets/proxy_ca update && \
    apt-get -o Acquire::https::CaInfo=/run/secrets/proxy_ca install -y --no-install-recommends libgomp1 && \
    rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    if [ -n "$FPL_EXTRAS" ]; then pip install ".[${FPL_EXTRAS}]"; else pip install .; fi
RUN useradd --create-home --uid 10001 fpl && mkdir -p data/raw data/processed models && chown -R fpl:fpl /app
COPY --chown=fpl:fpl app ./app
USER fpl
EXPOSE 8501
HEALTHCHECK --interval=30s --start-period=20s CMD python -c "import urllib.request; o=urllib.request.build_opener(urllib.request.ProxyHandler({})); o.open('http://127.0.0.1:8501/_stcore/health', timeout=5)"
CMD ["streamlit", "run", "app/main.py", "--server.address=0.0.0.0", "--server.port=8501", "--browser.gatherUsageStats=false"]
