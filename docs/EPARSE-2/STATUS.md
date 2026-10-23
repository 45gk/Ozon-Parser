# EPARSE-2 — статус: веб-приложение Ozon Parse Lab

**Дата:** 2026-10-22  
**Проект:** `/Users/igor/Documents/test_project/ozon-parser`  
**Статус:** MVP готов и проверен end-to-end.  
**Стек:** FastAPI + Jinja2 + SQLAlchemy + PostgreSQL 17 (Docker) + Playwright/CDP.

---

## 1. Задача

Сделать веб-приложение, в котором можно:

- запускать парсер по URL товара;
- смотреть результат текущего парсинга;
- возвращаться к результатам предыдущих парсингов;
- видеть общую историю и статистику по запускам.

PostgreSQL — в Docker. Результат и ход рассуждений — отдельными файлами в `docs/EPARSE-2/`.

---

## 2. Что получилось

### 2.1. Скриншоты

Дашборд: форма запуска, статистика и история.

![Дашборд](assets/dashboard.png)

Детальная страница: карточка, цены, характеристики, галерея и JSON.

![Детальная страница](assets/run-detail.png)

### 2.2. Функции

- [x] Запуск парсинга по URL из веб-формы.
- [x] Выбор источника: `Chrome CDP`, `Playwright`, `Direct API`, `HTML`.
- [x] CDP URL, таймауты, headless — настраиваются в форме.
- [x] Статусы `queued → running → success/failed` с автообновлением страницы.
- [x] История всех запусков.
- [x] Фильтры по статусу и источнику.
- [x] Поиск по URL, названию, SKU и продавцу.
- [x] Пагинация.
- [x] Статистика: всего, успешно, ошибки, уникальные товары, среднее время, success rate.
- [x] Детальная страница: цена/карта/старая цена, рейтинг, отзывы, наличие, продавец, бренд, характеристики, галерея, полный JSON.
- [x] Повторный запуск одной кнопкой.
- [x] JSON API + Swagger (`/docs`).
- [x] `GET /health` с проверкой БД.
- [x] PostgreSQL в Docker + `compose.yaml`.
- [x] Dockerfile для веб-приложения.
- [x] Офлайн-тесты с моком парсера.
- [x] Проверка на реальной карточке Ozon через CDP.

---

## 3. Как запустить

### 3.1. Локально + PostgreSQL в Docker (рекомендуется)

```bash
cd /Users/igor/Documents/test_project/ozon-parser
docker compose up -d db
uv sync --extra browser
uv run uvicorn app.main:app --reload --port 8000
```

Открыть `http://127.0.0.1:8000`.

Перед CDP-парсингом запустить Chrome:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.ozon-chrome"
```

В форме CDP URL уже стоит `http://127.0.0.1:9222`.

### 3.2. Всё в Docker

```bash
docker compose up --build
```

- Web: `http://127.0.0.1:8000`
- PostgreSQL: `localhost:5432`

Ограничение: в контейнере нет Playwright/Chrome, а Chrome на хосте слушает `127.0.0.1`. Поэтому CDP-режим из контейнера не работает. Контейнер годится для истории, API и HTML; для живого Ozon через CDP запускайте приложение локально.

### 3.3. Переменные

| Переменная | По умолчанию |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg://ozon:ozon-dev@localhost:5432/ozon` |
| `CDP_URL` | `http://127.0.0.1:9222` |
| `OZON_COOKIE` | — |
| `PARSE_TIMEOUT` | `45` |
| `CHALLENGE_TIMEOUT` | `120` |
| `DISPLAY_TIMEZONE` | `Europe/Moscow` |
| `PAGE_SIZE` | `20` |
| `POSTGRES_PORT` | `5432` |
| `WEB_PORT` | `8000` |

---

## 4. API

| Метод | Путь | Ответ |
|---|---|---|
| `POST` | `/api/runs` | `202 {"id","status"}` |
| `GET` | `/api/runs` | `{"items","total","limit","offset"}` |
| `GET` | `/api/runs/{id}` | полный результат и `product` |
| `GET` | `/api/stats` | агрегаты |
| `GET` | `/health` | статус приложения и БД |
| `GET` | `/docs` | Swagger UI |

Пример:

```bash
curl -X POST http://127.0.0.1:8000/api/runs \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://www.ozon.ru/product/.../",
    "source": "cdp",
    "timeout": 45,
    "challenge_timeout": 120
  }'
```

---

## 5. Модель данных

Одна таблица `parse_runs`:

- `id` — UUID;
- `product_url`, `source`, `status`;
- `created_at`, `started_at`, `finished_at`, `duration_ms`;
- `product` — полный JSON карточки (`JSONB` в PostgreSQL, `JSON` в SQLite для тестов);
- `options` — параметры запуска (`JSONB`);
- `error` — текст ошибки;
- денормализованные поля для истории: `name`, `sku`, `price`, `currency`, `rating`, `review_count`, `in_stock`, `seller`, `image_url`.

Индексы: `status`, `source`, `sku`, `created_at`.

Схема создаётся через `Base.metadata.create_all` при старте. Alembic пока не подключён — это осознанный MVP-компромисс.

---

## 6. Архитектура

| Слой | Файлы |
|---|---|
| FastAPI app | `app/main.py` |
| Роуты страниц | `app/api/pages.py` |
| JSON API | `app/api/runs.py`, `app/api/health.py` |
| Схемы Pydantic | `app/schemas.py` |
| Репозиторий | `app/repositories/runs.py` |
| Фоновый runner | `app/services/runner.py` |
| Модели/сессии | `app/db/` |
| Шаблоны | `app/templates/` |
| CSS/JS | `app/static/` |
| Docker | `Dockerfile`, `compose.yaml`, `.dockerignore` |
| Тесты | `tests/test_web_app.py` |

Поток запуска:

```text
POST /api/runs
  → RunRepository.create(status=queued)
  → BackgroundTasks.add_task(run_parse)
  → runner: status=running
  → fetch_product_api / fetch_product_browser / fetch_product
  → product.to_dict()
  → update parse_runs + status=success/failed
  → UI polling GET /api/runs/{id} → reload
```

Парсинги сериализуются `threading.Lock`, приложение рассчитано на один worker.

---

## 7. Проверка

### 7.1. Тесты

```bash
uv run python -m unittest discover -s tests -v
```

- **25 тестов**, все проходят.
- `tests/test_parser.py` — 18 тестов парсера/CLI.
- `tests/test_web_app.py` — 7 тестов: health, создание запуска, успешный результат, failed-результат, валидация URL, 404, поиск/фильтры, form-submit.
- Внешний Ozon замокан, тесты не ходят в сеть.
- `ruff check` и `ruff format --check` — чисто.

### 7.2. PostgreSQL

```bash
docker compose up -d db
docker compose exec db psql -U ozon -d ozon -c '\d parse_runs'
```

Проверено: таблица создаётся, `product` имеет тип `jsonb`, индексы на месте.

### 7.3. Docker-образ

```bash
docker compose build web
docker compose up -d web
curl http://127.0.0.1:8000/health
```

Проверено: образ собирается, контейнер стартует, `/health` возвращает `{"status":"ok","database":"ok","version":"0.3.0"}`, история из PostgreSQL видна.

### 7.4. Живой парсинг через веб-приложение

Через API веб-приложения создан реальный запуск:

- источник `cdp`;
- статус `success`;
- длительность ~700 мс;
- извлечены: название, `251 ₽`, `card_price 236 ₽`, `original_price 999 ₽`, рейтинг `4.9`, отзывы, SKU, продавец, 6 изображений.

Через браузер (Playwright) проверен пользовательский сценарий: заполнение формы → POST → переход на `/runs/{id}` → polling → появление статуса «Успех».

---

## 8. Ограничения

1. **Нет авторизации.** Приложение локальное; не выставлять в интернет без auth/reverse proxy.
2. **Один worker.** Фоновые задачи в процессе; при нескольких worker нужна внешняя очередь (RQ/Celery).
3. **Рестарт сервера.** Незавершённые `queued/running` помечаются `failed` при старте.
4. **Docker ≠ CDP.** Контейнер не видит Chrome на хосте; для CDP запускать приложение локально.
5. **Нет Alembic.** Изменения схемы пока через `create_all`; для эволюции схемы нужен Alembic.
6. **Нет загрузки сохранённого JSON в UI.** `--json` остаётся CLI-сценарием.
7. **Нет агрегации по товару.** История — список запусков; сравнение одного SKU во времени пока не сделано.
8. **Ozon.** Антибот никуда не делся; CDP помогает, но не даёт гарантий.

---

## 9. Следующие шаги

### P0

- [ ] Alembic + первая миграция.
- [ ] Ограничение одновременных запусков на уровне очереди и rate limit.
- [ ] Загрузка сохранённого JSON в UI (drag-and-drop / textarea).
- [ ] Проверить на 5–10 разных карточках (нет в наличии, без отзывов, акции).

### P1

- [ ] Агрегация по SKU: последняя цена, история изменений, сравнение запусков.
- [ ] Экспорт истории в CSV/JSON.
- [ ] Удаление/очистка истории.
- [ ] Auth (хотя бы basic) для доступа не с localhost.
- [ ] Health/метрики для очереди.

### P2

- [ ] RQ/Celery + Redis вместо BackgroundTasks.
- [ ] Alembic-миграции в CI.
- [ ] Docker-образ с Playwright/Chromium (если нужен browser-режим в контейнере).
- [ ] Тёмная/светлая тема, настройки.

---

## 10. Handoff-чеклист

1. `docker compose up -d db` — контейнер `healthy`?
2. `uv sync --extra browser` — зависимости стоят?
3. `uv run python -m unittest discover -s tests` — 25 тестов зелёные?
4. `uv run uvicorn app.main:app --port 8000` — `/health` отвечает?
5. Chrome запущен с `--remote-debugging-port=9222`?
6. Форма с `source=cdp` создаёт запуск и доходит до `success`?
7. История, фильтры и поиск показывают созданные запуски?
8. `docker compose build web` — образ собирается?

---

## 11. Определение готовности (для этой итерации)

- [x] Веб-форма запускает парсер.
- [x] Результат сохраняется в PostgreSQL.
- [x] История, фильтры, поиск, пагинация.
- [x] Детальная страница с карточкой и JSON.
- [x] Статусы и polling.
- [x] PostgreSQL в Docker.
- [x] Dockerfile/compose.
- [x] Тесты и линтер.
- [x] Живой CDP-парсинг проверен.
- [x] Скриншоты и документация.
