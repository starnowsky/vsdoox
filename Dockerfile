# --- Сборка фронтенда ---
FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Backend + собранный фронтенд ---
FROM python:3.12-slim AS backend
WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends libxml2-dev libxslt1-dev && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ ./backend/
COPY --from=frontend /app/frontend/dist ./frontend/dist
WORKDIR /app/backend
ENV VSDOOX_DB_URL=sqlite:////data/vsdoox.db
VOLUME /data
EXPOSE 5000
CMD ["sh", "-c", "gunicorn -w ${GUNICORN_WORKERS:-2} --threads ${GUNICORN_THREADS:-4} --timeout 120 -b 0.0.0.0:${PORT:-5000} app:app"]
