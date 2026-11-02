FROM node:20-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt \
        --extra-index-url https://download.pytorch.org/whl/cpu

COPY . .
COPY --from=web /web/dist /app/web/dist

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8080

RUN python -c "from baseline.evaluate import engine_cache_dir, load_or_build_engine; load_or_build_engine(12.0, engine_cache_dir(12.0))"

EXPOSE 8080
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
