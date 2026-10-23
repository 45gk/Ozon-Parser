# Ozon Product Parser

CLI, Python-библиотека и локальное веб-приложение для публичных карточек Ozon. Поддерживает три источника данных:

- **`entrypoint-api`** — тот же JSON-запрос, который делает страница товара: `GET /api/entrypoint-api.bx/page/json/v2?url=/product/...`. Основной источник, отдаёт структурированные поля без разбора HTML.
- **Браузер** — Playwright открывает страницу и выполняет запрос к API из контекста браузера. Нужен, когда Ozon отвечает `403` на обычный HTTP.
- **HTML страницы** — JSON-LD и Open Graph метатеги. Резервный вариант и разбор сохранённых страниц.

Неполные карточки возвращают найденные поля, остальные остаются `null`.

## Установка

Требуется Python 3.12+ и `uv`. Для браузерного режима нужен Playwright и установленный Chrome/Edge.

```bash
uv sync --extra browser
```

Если Chrome/Edge нет:

```bash
uv run playwright install chromium
```

## CLI: быстрый старт

```bash
uv run ozon-parse 'https://www.ozon.ru/product/.../'
```

По умолчанию используется API. Результат выводится в JSON:

```json
{
  "source_url": "https://www.ozon.ru/product/bity-magnitnye-usilennye-dlya-shurupoverta-2684123133/",
  "name": "Биты магнитные, усиленные для шуруповерта",
  "description": null,
  "price": "251",
  "currency": "RUB",
  "availability": "https://schema.org/InStock",
  "rating": "4.9",
  "review_count": 39852,
  "sku": "2684123133",
  "image_urls": ["https://ir-20.ozone.ru/s3/multimedia-1-1/15179100805.jpg", "..."],
  "original_price": "999",
  "card_price": "236",
  "in_stock": true,
  "seller": "BestPick",
  "brand": null,
  "characteristics": {
    "Тип": "Бита",
    "Тип наконечника": "PH2"
  }
}
```

`price` — обычная текущая цена, `card_price` — цена с Ozon Картой, `original_price` — цена до скидки (если Ozon её показывает).

## Веб-приложение

FastAPI + Jinja2 + PostgreSQL. Умеет:

- запускать парсинг по URL из браузера;
- показывать статус `queued/running/success/failed` с автообновлением;
- хранить историю, фильтровать по статусу/источнику и искать по URL, названию, SKU, продавцу;
- показывать карточку, характеристики, галерею и полный JSON;
- повторять запуск одной кнопкой;
- собирать топ товаров из поисковой выдачи Ozon (ссылки, цены, рейтинги).

![Дашборд Ozon Parse Lab](docs/EPARSE-2/assets/dashboard.png)

### Локальный запуск (рекомендуется)

PostgreSQL поднимается в Docker, приложение запускается локально — так доступен CDP к вашему Chrome.

```bash
docker compose up -d db
uv sync --extra browser
uv run uvicorn app.main:app --reload --port 8000
```

Открой `http://127.0.0.1:8000`.

Если порт 8000 занят (например, другим локальным приложением), запусти на 8001:

```bash
uv run uvicorn app.main:app --reload --port 8001
```

По умолчанию используется база:

```text
postgresql+psycopg://ozon:ozon-dev@localhost:5432/ozon
```

Перед парсингом через CDP запусти Chrome с remote debugging:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.ozon-chrome"
```

В форме веб-приложения CDP URL уже заполнен как `http://127.0.0.1:9222`.

### Полный запуск в Docker

```bash
docker compose up --build
```

Веб-интерфейс: `http://127.0.0.1:8000`, PostgreSQL: `localhost:5432`.

Важно: в Docker-образе нет Playwright и Chrome, поэтому режимы `Chrome CDP` и `Playwright` внутри контейнера недоступны. Контейнер удобен для истории, API и HTML. Для живого Ozon через CDP запускай приложение локально, оставив PostgreSQL в Docker.

### Переменные окружения

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://ozon:ozon-dev@localhost:5432/ozon` | Подключение к PostgreSQL |
| `CDP_URL` | `http://127.0.0.1:9222` | Адрес Chrome с remote debugging |
| `OZON_COOKIE` | — | Cookie для прямого API-запроса |
| `PARSE_TIMEOUT` | `45` | Таймаут загрузки страницы |
| `CHALLENGE_TIMEOUT` | `120` | Ожидание прохождения challenge |
| `DISPLAY_TIMEZONE` | `Europe/Moscow` | Часовой пояс в интерфейсе |
| `PAGE_SIZE` | `20` | Размер страницы истории |
| `POSTGRES_PORT` | `5432` | Порт PostgreSQL в compose |
| `WEB_PORT` | `8000` | Порт веб-приложения в compose |

### API

| Метод | Путь | Назначение |
|---|---|---|
| `POST` | `/api/runs` | Создать парсинг, вернуть `202` и `id` |
| `GET` | `/api/runs` | История с фильтрами `status`, `source`, `q`, `limit`, `offset` |
| `GET` | `/api/runs/{id}` | Статус и результат |
| `GET` | `/api/stats` | Общая статистика |
| `GET` | `/health` | Проверка приложения и БД |
| `POST` | `/api/searches` | Создать сбор топа выдачи, вернуть `202` и `id` |
| `GET` | `/api/searches` | История поисков с фильтрами |
| `GET` | `/api/searches/{id}` | Статус и товары выдачи |
| `GET` | `/api/searches/stats` | Статистика поисков |
| `GET` | `/docs` | Swagger UI |

Пример:

```bash
curl -X POST http://127.0.0.1:8000/api/runs \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://www.ozon.ru/product/...",
    "source": "cdp",
    "timeout": 45,
    "challenge_timeout": 120
  }'
```

## Поиск по выдаче

Отдельный режим: вставь ссылку на `/category/...` или `/search/...` — парсер заберёт
первые N товаров из выдачи Ozon, сохранит ссылки, цены, скидки и рейтинги.

![Поиск по выдаче](docs/EPARSE-3/assets/search-dashboard.png)

- до 100 товаров за запуск (по умолчанию 20);
- учитывается порядок выдачи Ozon, дубликаты по SKU убираются;
- поддерживается пагинация выдачи через `infiniteVirtualPaginator.nextPage`;
- результаты лежат в `search_runs` и `search_items`, не пересекаясь с `parse_runs`.

```bash
curl -X POST http://127.0.0.1:8000/api/searches \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://www.ozon.ru/category/noutbuki-15692/apple-26303000/?text=macbook+air+m5",
    "source": "cdp",
    "limit": 20,
    "timeout": 45,
    "challenge_timeout": 120
  }'
```

Страница интерфейса: `http://127.0.0.1:8000/searches`.

## Живой запрос через браузер (CDP)

Самый надёжный способ, если прямой API отвечает `403` с `incidentId`. Парсер подключается к **обычному Chrome**, который вы запустили сами, и выполняет `fetch` из уже открытой страницы Ozon. Ozon видит обычный браузер, а не автоматизированный.

1. Установите браузерную зависимость:

```bash
uv sync --extra browser
```

2. Запустите Chrome с отдельным профилем и remote debugging:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.ozon-chrome"
```

Для Linux: `google-chrome --remote-debugging-port=9222 --user-data-dir="$HOME/.ozon-chrome"`.
Для Windows: `"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%USERPROFILE%\.ozon-chrome"`.

3. Запустите парсер:

```bash
uv run ozon-parse --source browser --cdp-url http://127.0.0.1:9222 \
  'https://www.ozon.ru/product/.../'
```

`--cdp-url` уже подразумевает `--source browser`, но явный флаг понятнее. Парсер откроет новую вкладку, загрузит карточку, выполнит запрос к API и закроет вкладку. Сам браузер останется запущенным. Профиль `~/.ozon-chrome` сохраняет cookie и пройденную проверку между запусками. Если Ozon покажет challenge, его можно пройти в открытом окне; время ожидания задаётся `--challenge-timeout`.

## Автозапуск браузера Playwright

```bash
uv run ozon-parse --source browser 'https://www.ozon.ru/product/.../'
```

Playwright сам запустит установленный Chrome/Edge (или Chromium). Это обычный браузер без stealth-патчей, но он помечен как автоматизированный, поэтому Ozon чаще показывает `403` / «Похоже, нет соединения». В этом случае используйте CDP-режим.

```bash
uv run ozon-parse --source browser --headless 'https://www.ozon.ru/product/.../'
uv run ozon-parse --source browser --user-data-dir ~/.ozon-playwright 'https://www.ozon.ru/product/.../'
```

## Разбор сохранённого ответа API

Если браузерный режим недоступен, можно разобрать ответ, сохранённый из DevTools:

1. Откройте карточку в браузере, DevTools → Network.
2. Найдите запрос `entrypoint-api.bx/page/json/v2`.
3. Скопируйте или сохраните его Response в файл (например, `response.json`).
4. Запустите:

```bash
uv run ozon-parse --json response.json 'https://www.ozon.ru/product/.../'
```

Ссылка не обязательна, но по ней заполняется `source_url`. Можно читать из stdin:

```bash
cat response.json | uv run ozon-parse --json -
```

## Другие режимы CLI

```bash
# Разобрать HTML страницы (JSON-LD + Open Graph)
uv run ozon-parse --source html 'https://www.ozon.ru/product/.../'

# Передать cookie браузера обычному API-запросу (может не помочь)
OZON_COOKIE='__Secure-ETC=...; abt_data=...' uv run ozon-parse 'https://www.ozon.ru/product/.../'
uv run ozon-parse --cookie '...' 'https://www.ozon.ru/product/.../'

# Изменить таймаут
uv run ozon-parse --timeout 40 'https://www.ozon.ru/product/.../'
```

Cookie также можно задать переменной `OZON_COOKIE`. Пользовательский User-Agent — переменной `OZON_USER_AGENT`.

## Библиотека

```python
from ozon_parser import (
    fetch_product_api,
    fetch_product_browser,
    parse_product_json,
    parse_product_html,
)

# Живой запрос к entrypoint-api
product = fetch_product_api("https://www.ozon.ru/product/.../")

# Через уже запущенный Chrome с remote debugging
product = fetch_product_browser(
    "https://www.ozon.ru/product/.../",
    cdp_url="http://127.0.0.1:9222",
)

# Сохранённый JSON (dict, str или bytes)
product = parse_product_json(json_text, source_url="https://www.ozon.ru/product/.../")

# HTML
product = parse_product_html(html, source_url="https://www.ozon.ru/product/.../")

print(product.to_dict())
```

Полезные функции: `build_api_url(product_url)` собирает URL запроса к API, `fetch_product()` — HTML-загрузчик, `OzonFetchError` и `OzonProductParseError` — ошибки загрузки и разбора.

## Архитектура

| Компонент | Файлы |
|---|---|
| Парсер и модели | `ozon_parser/`, в т.ч. `ozon_parser/search.py` |
| FastAPI-приложение | `app/main.py`, `app/api/` |
| База данных | `app/db/` |
| Репозиторий истории | `app/repositories/runs.py`, `app/repositories/searches.py` |
| Фоновый запуск парсинга | `app/services/runner.py`, `app/services/search_runner.py` |
| Шаблоны и статика | `app/templates/`, `app/static/` |
| Docker | `Dockerfile`, `compose.yaml` |

Схема БД создаётся автоматически при старте (`Base.metadata.create_all`). Таблица `parse_runs` хранит URL, источник, статус, тайминги, денормализованные поля карточки и полный JSON в `JSONB`. Для следующих изменений схемы стоит добавить Alembic.

Фоновые задачи выполняются внутри процесса приложения, а парсинги сериализуются блокировкой. Запускайте приложение с одним worker (значение по умолчанию); несколько worker потребуют отдельной очереди задач.

## Тесты

```bash
uv run python -m unittest discover -s tests -v
```

- `tests/test_parser.py` — парсер, CLI, фикстура.
- `tests/test_search_parser.py` — разбор поисковой выдачи и URL API.
- `tests/test_web_app.py` — API, история, фильтры, шаблоны, фоновые runner'ы (SQLite + мок парсера).

Тесты офлайн: не ходят в Ozon и не требуют Chrome.

## Документация

- [EPARSE-1: статус парсера](docs/EPARSE-1/STATUS.md)
- [EPARSE-1: журнал решений](docs/EPARSE-1/REASONING.md)
- [EPARSE-2: статус веб-приложения](docs/EPARSE-2/STATUS.md)
- [EPARSE-2: журнал решений](docs/EPARSE-2/REASONING.md)
- [EPARSE-3: статус поиска по выдаче](docs/EPARSE-3/STATUS.md)
- [EPARSE-3: журнал решений](docs/EPARSE-3/REASONING.md)

## Ограничения

- Ozon активно защищается от автоматизации: прямой HTTP-запрос к API обычно получает `403` с `incidentId`, а Playwright-браузер может получить страницу «Похоже, нет соединения». Парсер не применяет stealth-патчи и не обходит защиту. Рабочий вариант — CDP к запущенному вручную Chrome, сохранённый ответ (`--json`) или ваши cookie.
- Для CDP-режима Chrome должен быть запущен с `--remote-debugging-port` и отдельным `--user-data-dir`; нельзя использовать уже запущенный экземпляр с тем же профилем.
- CDP из Docker-контейнера к Chrome на хосте обычно недоступен: Chrome слушает `127.0.0.1`. Запускайте приложение локально.
- Веб-приложение не имеет авторизации и рассчитано на локальный запуск. Не выставляйте его в интернет без аутентификации и reverse proxy.
- Структура `widgetStates` и состав виджетов могут меняться. Парсер ищет виджеты по префиксам (`webPrice`, `webGallery`, ...) и не падает, если части полей нет.
- Цена и наличие зависят от региона, аккаунта и Ozon Карты; `price` — обычная цена, `card_price` — цена с картой.
- Описание (`webDescription`) приходит не во всех ответах; тогда `description` остаётся `null`.
- Уважайте правила Ozon и не создавайте высокую нагрузку на сайт.
