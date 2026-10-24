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
| `REPORT_NARRATIVE_ENABLED` | `true` | Аварийный выключатель платных вызовов нарратива отчёта (`false`/`0`/`no` — 0 платных вызовов, отчёт детерминированный) | `false` |
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

### Защита входа по коду приглашения от перебора (ROADMAP #77)

Публичные входы по коду — `POST /diagnostic/sessions`, `GET /diagnostic/sessions/active`, `GET /diagnostic/sessions/by-invite` — по-разному отвечают на
неизвестный и известный код, поэтому auth-service не может ограничить перебор по IP ученика (мы вызываем его сервер-к-серверу). Лимит здесь:

- IP клиента — только `X-Real-IP` (его ставит nginx; `X-Forwarded-For` не доверяем), IPv6 считается по /64. Счётчики — Redis, без Redis — память процесса с одним предупреждением в лог.
- Строго считаются **неудачные** поиски (код не найден / известный код с чужим учеником или классом): 100 в минуту и 600 в час на IP. Удачные открытия кодов не считаются неудачами,
  класс из 30 человек за одним NAT проходит целиком; для них только защита от флуда: 300 в минуту и 3000 в час на IP.
- 100 обращений в час на один существующий код: счётчик заводится только после проверки, что код существует (перебор неизвестных кодов не плодит ключи), а читается до запроса к auth-service.
  Код хранится только хешем и в логи не попадает.
- Ответ при превышении: `429`, `Retry-After` (максимум по всем превышенным окнам), `{"code": "TOO_MANY_ATTEMPTS", "message": "Слишком много попыток. Подождите минуту и попробуйте снова.", "action": "retry"}`.
  Отказ для адреса пишется в лог один раз за окно, а не на каждый запрос.
