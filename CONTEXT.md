# Diagnostic Service — Контекст разработки

## Что уже сделано (готово к продакшену)

### Инфраструктура
- **FastAPI** сервис, порт 8002, lifespan запускает alembic миграции при старте
- **PostgreSQL** контейнер `algo-postgres-diag`, порт 5433, БД `algo_v1`
- **Redis** контейнер `algo-redis-diag`, порт 6380, TTL сессий 7200с, JSON (без Pickle)
- **Docker Compose** — 3 сервиса: `algo-diagnostic`, `algo-postgres-diag`, `algo-redis-diag`
- **Alembic** миграции 001→002→003 применены, `alembic_version = 003_drop_grade_topic_map`
- Health endpoint `/health` → `{"status":"healthy","database":"ok","redis":"ok"}`

### База данных (7 таблиц)

| Таблица | Записей | Статус |
|---|---|---|
| `knowledge_hierarchy` | **1004** | ✅ заполнена (5 грейдов, L1-L4) |
| `tasks_master` | 0 | ⏳ ждёт AI-оцифровки |
| `skill_prerequisites` | 0 | ⏳ ждёт AI-граф зависимостей |
| `diag_sessions` | 0 | ✅ готова принимать данные |
| `diag_answers` | 0 | ✅ готова принимать данные |
| `diag_reports` | 0 | ✅ готова принимать данные |
| `alembic_version` | 1 | ✅ |

`grade_topic_map` — удалена (была дублем `knowledge_hierarchy`).

### Алгоритм T-Shape Adaptive Diagnostic

**Фазы сессии:**
1. `warmup` — 3 задачи по prior_theta для первичной оценки способностей
2. `navigation` — бинарный поиск по L2→L3→L4 дереву (TopicNavigator→SubtopicNavigator→SkillNavigator)
3. `deep_scan` — обход prerequisite-графа при провале важного навыка (importance ≥ 8)
4. `completed` — персистинг в PostgreSQL, удаление из Redis

**Критерии остановки:**
- SE ≤ 0.30 (достигнута точность измерения)
- items_answered ≥ 25 (лимит задач)
- все L1 секции пройдены

**IRT 3PL модель:**
- EAP на 61-точечной сетке [-4, 4]
- Байесовское обновление theta после каждого ответа
- AlphaTracker — независимый per-topic mastery score

### Оценка ответов (AnswerEvaluator — 5 слоёв)

| Слой | Что делает | Время |
|---|---|---|
| L1 Exact match | case-insensitive сравнение строк | <0.01ms |
| L2 Numeric | `"3,5"→3.5`, `"4 507"→4507`, `"1/2"→0.5`, `"−5"→-5` | <0.1ms |
| L3 SymPy | `"2²"="4"`, `"√9"="3"`, `"2(x+1)"="2x+2"` | 15-50ms |
| L4 Distractor | partial credit 0.5 для известных ошибок (MCQ и open) | <0.01ms |
| L5 IDK | `"не знаю"`, `"skip"`, `"?"`, `""` → 0.0 | <0.01ms |

**SymPy оптимизация:** если обе стороны — простые числа и они разные, Layer 3 пропускается (skip_sympy=True).

### ORM модели

**`KnowledgeHierarchy`** (read-only) — все поля:
```
id, level, parent_id, name, name_ru, description,
class_level_start, class_level_end, importance, sequence_order,
cognitive_type, is_active,
example_task, assessed_ability, difficulty_level, formula  ← добавлены
```

**`TaskMaster`** (read-only) — все поля:
```
id, skill_id, question_text, question_latex,
answer_type, correct_answer, correct_answer_latex, sympy_solution,  ← добавлены
answer_options, difficulty, irt_discrimination, irt_difficulty, irt_guessing,
solution_steps, hints, distractor_meta, is_active
```

### API Endpoints

```
POST   /api/v1/diagnostic/sessions              — создать сессию, вернуть первую задачу
POST   /api/v1/diagnostic/sessions/{id}/answer  — отправить ответ, получить следующую задачу
GET    /api/v1/diagnostic/sessions/{id}/report  — получить финальный отчёт
GET    /health                                  — liveness + DB + Redis check
GET    /docs                                    — Swagger UI (только в development режиме)
```

### Режимы запуска

```env
STANDALONE=true   # (default) — своя БД, запускает миграции 001+002+003
STANDALONE=false  # — читает knowledge из монолита, запускает только 001 (owned tables)
```

---

## Что нужно сделать для полной работы

### 1. AI оцифровка → заполнить `tasks_master` ⚠️ БЛОКИРУЕТ ЗАПУСК

Без задач любой вызов `create_session` → `NoTasksAvailableError`.

**Контракт для каждой задачи:**

```json
{
  "id": "G5_S01_01_T001",
  "skill_id": "G5_S01_01",
  "question_text": "Найди значение выражения: 12 × 25",
  "question_latex": "12 \\times 25",
  "answer_type": "open",
  "correct_answer": "300",
  "correct_answer_latex": "300",
  "sympy_solution": "300",
  "answer_options": null,
  "difficulty": "B",
  "irt_difficulty": 0.0,
  "irt_discrimination": 1.2,
  "irt_guessing": 0.0,
  "hints": ["Разбей 25 = 20 + 5"],
  "distractor_meta": [
    {"value": "312", "misconception": "сложил вместо умножения"},
    {"value": "37", "misconception": "перепутал операцию"}
  ],
  "is_active": true
}
```

**Правила IRT параметров:**
```
irt_difficulty (b):   A (Low) = -1.0,  B (Medium) = 0.0,  C (High) = +1.0
irt_discrimination (a): 0.8–1.5 (по умолчанию 1.0 — ок)
irt_guessing (c):     MCQ 4 варианта = 0.25,  open = 0.0
```

**Правила answer_type:**
```
"open"  → ответ одно простое число/выражение (correct_answer + sympy_solution обязательны)
"mcq"   → всё остальное: два корня, пара координат, текст (answer_options обязателен)
```

**Минимально нужно:** ~3–5 задач на каждый L4 навык × 744 навыка = ~2500–4000 задач total (5-9 класс).

---

### 2. AI граф зависимостей → заполнить `skill_prerequisites` ⚠️ БЛОКИРУЕТ DEEP SCAN

Без prerequisite-рёбер deep scan сразу помечает провалившийся навык как gap и идёт дальше. Корневые причины не находятся.

**Контракт:**
```json
{
  "skill_id": "G5_S02_01",
  "prerequisite_id": "G5_S01_01",
  "weight": 1.0,
  "is_hard": true
}
```

```
weight: 1.0 = обязательный пресет, 0.5 = желательный
is_hard: true = hard prerequisite (проверяется в deep scan), false = soft (рекомендован)
```

**Deep scan использует только** `is_hard=true` рёбра (параметр `hard_only=True`).

---

### 3. LLM-методист → выставить `importance` на L2 нодах ⚠️ БЛОКИРУЕТ DEEP SCAN ТРИГГЕР

**Текущее состояние:** все 43 L2 ноды имеют `importance=5`.  
**Порог триггера deep scan:** `importance >= 8` (настройка `deep_scan_importance_threshold`).  
**Результат:** deep scan сейчас никогда не запускается.

**Что нужно:** LLM-методист проходит по L2 топикам и выставляет:
```
8–10 → критически важные темы (дроби, уравнения, координатная плоскость)
5–7  → средней важности
1–4  → второстепенные, пропускаем при провале
```

**Обновление через SQL:**
```sql
UPDATE knowledge_hierarchy SET importance = 9 WHERE id = 'G5_T06'; -- Обыкновенные дроби
UPDATE knowledge_hierarchy SET importance = 8 WHERE id = 'G5_T07'; -- Десятичные дроби
-- ...
```

---

### 4. Phase 2 — DiagReport narrative (не блокирует, можно позже)

`DiagReport.narrative_ru` и `pdf_url` не заполняются. Это Phase 2 — генерация человекочитаемого анализа через Gemini.

Когда делать: после того как накопятся реальные сессии и будет понятен нужный формат отчёта.

---

## Структура файлов сервиса

```
diagnostic-service/
├── src/
│   ├── api/router.py               — 3 HTTP endpoint (тонкий слой)
│   ├── core/
│   │   ├── config.py               — Settings (env vars)
│   │   ├── database.py             — SQLAlchemy engine, get_db()
│   │   ├── redis_client.py         — Redis singleton
│   │   └── exceptions.py           — Exception hierarchy
│   ├── domain/
│   │   ├── session_service.py      — Главный оркестратор (T-Shape алгоритм)
│   │   ├── answer_evaluator.py     — 5-слойный оценщик ответов
│   │   ├── alpha_engine.py         — IRT 3PL + EAP + AlphaTracker
│   │   ├── session_state.py        — SessionState dataclass (JSON-сериализуемый)
│   │   └── navigators/
│   │       ├── topic_navigator.py      — L2 бинарный поиск
│   │       ├── subtopic_navigator.py   — L3 бинарный поиск
│   │       └── skill_navigator.py      — L4 бинарный поиск + DeepScanState
│   ├── models/
│   │   ├── knowledge.py            — Read-only ORM (knowledge_hierarchy, tasks_master, skill_prerequisites)
│   │   └── diag_models.py          — Owned ORM (diag_sessions, diag_answers, diag_reports)
│   ├── repositories/
│   │   ├── knowledge_repo.py       — KnowledgeRepository, TaskRepository, SkillPrerequisiteRepository
│   │   └── diag_repo.py            — DiagSessionRepository, DiagAnswerRepository, DiagReportRepository
│   ├── schemas/diag_schemas.py     — Pydantic v2 request/response схемы
│   ├── state/redis_state.py        — RedisStateManager (save/load/delete)
│   └── main.py                     — FastAPI app, lifespan, CORS, /health
├── alembic/
│   └── versions/
│       ├── 001_create_diag_tables.py   — diag_sessions, diag_answers, diag_reports
│       ├── 002_create_knowledge_tables.py — knowledge_hierarchy seed (1004 нод)
│       └── 003_drop_grade_topic_map.py  — удаление устаревшей таблицы
├── requirements.txt                — включает sympy==1.13.3
├── docker-compose.yml
└── Dockerfile
```

---

## Зависимости между шагами

```
tasks_master заполнен
    → сессии запускаются
    → AnswerEvaluator оценивает ответы (все 5 слоёв)
    → IRT theta обновляется корректно
    → AdaptivSelection подбирает задачи по theta

skill_prerequisites заполнен
    → DeepScan traversal находит корневые пробелы
    → confirmed_gaps содержит реальные дефициты, а не симптомы

importance выставлен на L2
    → deep_scan триггерится только на критических темах
    → алгоритм дифференцирует важные и второстепенные провалы

Всё вместе
    → полный T-Shape diagnostic отчёт с точным профилем пробелов студента
```
