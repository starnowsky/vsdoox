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
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ ./backend/
COPY --from=frontend /app/frontend/dist ./frontend/dist
WORKDIR /app/backend
ENV VSDOOX_DB_URL=sqlite:////data/vsdoox.db
VOLUME /data
EXPOSE 5000
CMD ["python", "-c", "from app import app; app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)"]
