# diagnostic-service

Сервис CAT-диагностики (Computerized Adaptive Testing). Проводит персонализированный тест, выявляет пробелы в знаниях и формирует карту навыков студента.

- **Port**: 8002
- **DB**: `algo_diagnostic` (PostgreSQL 15)
- **Cache**: Redis (CAT-сессии, TTL 2ч)
- **Framework**: FastAPI + SQLAlchemy ORM + Alembic
- **Main file**: `src/main.py`

## Как работает CAT

1. Получает навыки и задания от **content-service** (HTTP)
2. Адаптивно выбирает следующий вопрос на основе θ (IRT)
3. Хранит состояние сессии в Redis (JSON, не pickle)
4. По завершении сохраняет результат в PostgreSQL
5. Уведомляет auth-service о завершении

## Переменные окружения

| Переменная | Обязательная | Описание | Пример |
|---|---|---|---|
| `DATABASE_URL` | ✅ | PostgreSQL DSN | `postgresql://algo:pass@algo-postgres-diag:5432/algo_diagnostic` |
| `REDIS_URL` | ✅ | Redis DSN | `redis://redis:6379` |
| `APP_ENV` | — | `production` / `development` | `production` |
| `CONTENT_SERVICE_URL` | — | URL content-service | `http://content-api:8004` |
| `AUTH_SERVICE_URL` | — | URL auth-service для колбэков | `http://algo-auth:8000` |
| `GEMINI_API_KEY` | — | Google Gemini (AI-отчёты) | — |
| `CORS_ORIGINS` | — | JSON-массив origins | `["https://algolab.me"]` |
| `STANDALONE` | — | `true` = собственная БД | `true` |
| `REDIS_SESSION_TTL` | — | TTL CAT-сессии (сек) | `7200` |

## Алгоритм параметры

| Параметр | По умолчанию | Описание |
|---|---|---|
| `WARMUP_ITEMS` | 5 | Вводных вопросов, по разным L1-разделам |
| `MIN_ITEMS` | 12 | Минимум измерительных вопросов до остановки по точности |
| `MAX_ITEMS` | 42 | Жёсткий максимум вопросов на сессию |
| `SE_THRESHOLD` | 0.30 | Стандартная ошибка для остановки |
| `MIN_SECTION_COVERAGE` | 5 | Максимум обязательных L1-разделов для точной остановки |
| `MASTERY_THRESHOLD` | 0.6 | Минимум правильных для "освоен" |

## Как запустить

```bash
cp .env.example .env
docker compose up -d --build

# Миграции
docker exec algo-diagnostic alembic upgrade head

# Prod
docker compose -f docker-compose.prod.yml up -d
```

## API

| Метод | Путь | Описание |
|---|---|---|
| POST | `/api/v1/diagnostic/sessions` | Начать диагностику |
| POST | `/api/v1/diagnostic/sessions/{id}/answer` | Ответить на вопрос |
| GET | `/api/v1/diagnostic/sessions/{id}` | Статус сессии |
| GET | `/api/v1/diagnostic/sessions/{id}/report` | Итоговый отчёт |
| GET | `/health/live` | Liveness probe |
| GET | `/health/ready` | Readiness probe (DB + Redis) |
| GET | `/metrics` | Prometheus метрики |

Swagger UI (только `development`): http://localhost:8002/docs
