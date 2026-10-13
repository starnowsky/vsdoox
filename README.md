# vsdoox

Редактор сетевых схем (уровень L2) с генерацией `.vsdx` (Microsoft Visio).

## Возможности

- Сущности схемы: **сервер**, **межсетевой экран (МЭ)**, **сеть/подсеть**, **территориальный контейнер (ЦОД)**.
- **Автоматический расчёт маршрута**: при указанном сетевом взаимодействии между двумя объектами система строит граф L2-связности и определяет, через какие межсетевые экраны проходит путь.
- Сохранение проектов: у каждого пользователя свой набор схем (изоляция по владельцу).
- Экспорт схемы в `.vsdx`.

## Стек

- Backend: Python 3 + Flask.
- Хранение: SQLAlchemy ORM; по умолчанию SQLite, PostgreSQL — замена URL (`VSDOOX_DB_URL`).
- Frontend: React + React Flow + Vite + TypeScript (canvas-редактор).

## Структура

```
backend/
  app.py         HTTP API
  models.py      SQLAlchemy ORM-модели
  storage.py     слой хранения (SQLAlchemy)
  topology.py    движок топологии (граф + путь через МЭ)
  generator.py   генерация .vsdx
  tests/         тесты
frontend/
  src/           React + React Flow (canvas-редактор)
  package.json, vite.config.ts, tsconfig.json
```

## Установка и запуск

### Backend

```bash
python3 -m venv myenv
source myenv/bin/activate
pip install -r backend/requirements.txt

cd backend
python app.py          # API на http://127.0.0.1:5000
```

Переменная окружения `VSDOOX_DB_URL` задаёт URL БД (по умолчанию SQLite-файл `backend/vsdoox.db`; для PostgreSQL — `postgresql+psycopg://user:pass@host/dbname`).

### Frontend

Требуется Node.js 18+.

```bash
cd frontend
npm install
npm run dev            # dev-сервер Vite (http://localhost:5173), проксирует /api → :5000
```

Сборка для production (Flask раздаёт результат из `frontend/dist`):

```bash
npm run build
```

После сборки откройте http://127.0.0.1:5000 — Flask отдаст собранный фронтенд.

## Тесты

```bash
cd backend
python tests/test_app.py
# или
python -m unittest discover -s tests
```

## Модель данных

| Сущность | `type` | Назначение |
|---|---|---|
| Сервер | `server` | узел с IP/портами |
| Межсетевой экран | `firewall` | разделяет сегменты сети |
| Сеть | `network` | L2/L3-сегмент (VLAN, CIDR) |
| ЦОД | `datacenter` | территориальное размещение |

- `nodes` — узлы: `{id, type, name, parent_id, x, y, attributes}`; `parent_id` задаёт вложенность: сервер → сеть → ЦОД, МСЭ → ЦОД.
- `links` — физические L2-линки: `{id, source_id, target_id, label, attributes}`.
- `connections` — заданные взаимодействия: `{id, source_id, target_id, protocol, port, attributes}`.

## API

| Метод | Путь | Описание |
|---|---|---|
| POST | `/api/projects` | создать проект `{name, owner}` |
| GET | `/api/projects?owner=…` | список проектов пользователя |
| GET | `/api/projects/<id>` | полный проект (nodes/links/connections) |
| PUT | `/api/projects/<id>` | сохранить граф целиком |
| DELETE | `/api/projects/<id>` | удалить проект |
| POST | `/api/path` | расчёт маршрута `{nodes, links, source_id, target_id}` → `{found, path, firewalls, segments}` |
| POST | `/api/export` | экспорт графа `{title, nodes, connections}` в `.vsdx` |
| POST | `/api/preview` | координаты для SVG-предпросмотра (старый флоу) |
| POST | `/api/generate` | скачать `.vsdx` (старый флоу) |


## Docker (запуск на другом сервере)

Образ собирает фронтенд (Node) и backend (Python + gunicorn) в один контейнер. БД хранится в volume `vsdoox-data`.

```bash
cp .env.example .env   # при необходимости отредактируй порт/ключ
docker compose up -d --build
```

Сервис доступен на `http://<server>:5000`. Переменные окружения (см. `.env.example`):

| Переменная | Описание | По умолчанию |
|---|---|---|
| `PORT` | порт сервиса | `5000` |
| `VSDOOX_DB_URL` | URL БД (SQLite/PostgreSQL) | `sqlite:////data/vsdoox.db` |
| `VSDOOX_ADMIN_KEY` | ключ админа (создаётся при первом старте, если пусто) | пусто |
| `GUNICORN_WORKERS` | число worker-процессов | `2` |
| `GUNICORN_THREADS` | число потоков на worker | `4` |

Первый запуск: открой `http://<server>:5000`, войди в **admin** (справа вверху), создай ключ (или задай `VSDOOX_ADMIN_KEY` в `.env`), затем создай локального пользователя и войди под ним.

