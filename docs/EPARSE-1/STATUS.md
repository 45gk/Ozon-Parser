# Статус задачи: Ozon Product Parser

**Дата:** 2026-10-22  
**Проект:** `/Users/igor/Documents/test_project/ozon-parser`  
**Статус:** рабочий MVP. Основной сценарий (живой API через обычный Chrome по CDP) проверен на реальной карточке.  
**Версия пакета:** 0.2.0

---

## 1. Задача

Получать данные публичной карточки товара Ozon из JSON-ответа `entrypoint-api.bx/page/json/v2`, а не только из HTML/JSON-LD. Нужно было:

- разобрать структуру `widgetStates` из сохранённого примера;
- расширить существующий HTML-парсер источником API;
- предусмотреть обход антибот-блокировки легальными средствами (без stealth-патчей);
- оставить офлайн-проверку на сохранённом JSON.

---

## 2. Итог одной таблицей

| Сценарий | Статус | Что именно проверено |
|---|---|---|
| `--json FILE` — разбор сохранённого ответа | ✅ работает | `json_responce.json`, все поля, 18 тестов |
| `--source api` — прямой HTTP к API | ⚠️ код работает, Ozon блокирует | `curl`/`httpx`: `307` → `403`, `incidentId`, `challengeURL` |
| `--source html` — HTML/JSON-LD | ✅ код работает | синтетический HTML, unit-тест |
| `--source browser` — Playwright сам запускает Chrome | ❌ Ozon блокирует | headless и headed: `403` / «Похоже, нет соединения» |
| `--source browser --cdp-url http://127.0.0.1:9222` | ✅ работает | live `200`, карточка разобрана |
| Автотесты | ✅ 18/18 | `python -m unittest discover -s tests` |
| Линтер/форматтер | ✅ чисто | `ruff check`, `ruff format --check` |

---

## 3. Что работает

### 3.1. Разбор сохранённого ответа API

Команда:

```bash
uv run ozon-parse --json json_responce.json \
  'https://www.ozon.ru/product/bity-magnitnye-usilennye-dlya-shurupoverta-2684123133/'
```

Из примера извлекается:

```json
{
  "name": "Биты магнитные, усиленные для шуруповерта",
  "price": "251",
  "card_price": "236",
  "original_price": "999",
  "currency": "RUB",
  "rating": "4.9",
  "review_count": 39852,
  "sku": "2684123133",
  "in_stock": true,
  "seller": "BestPick",
  "image_urls": ["... 6 изображений ..."],
  "characteristics": {
    "Тип": "Бита",
    "Тип биты": "Односторонняя",
    "Тип наконечника": "PH2",
    "Патрон/шпиндель/крепление": "Шестигранник",
    "Размер головки, дюйм": "1/4\""
  }
}
```

`description` и `brand` — `null`, потому что в этом ответе нет виджетов `webDescription` и `webBrand`.

### 3.2. Живой запрос через CDP (главный рабочий сценарий)

Запуск обычного Chrome с отдельным профилем:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.ozon-chrome"
```

Запрос:

```bash
uv run ozon-parse --cdp-url http://127.0.0.1:9222 \
  'https://www.ozon.ru/product/bity-magnitnye-usilennye-dlya-shurupoverta-2684123133/'
```

Что делает парсер:

1. подключается к уже запущенному Chrome по CDP;
2. открывает новую вкладку;
3. загружает карточку товара;
4. выполняет `fetch(api_url)` из контекста страницы (`credentials: include`);
5. при challenge ждёт прохождения проверки в видимом окне;
6. парсит JSON;
7. закрывает вкладку, но **не закрывает сам Chrome**.

Живой результат последней проверки:

```json
{
  "name": "Биты магнитные, усиленные для шуруповерта",
  "price": "251",
  "card_price": "236",
  "rating": "4.9",
  "review_count": 39865,
  "sku": "2684123133",
  "seller": "BestPick",
  "in_stock": true,
  "currency": "RUB"
}
```

`review_count` отличается от примера (`39852` → `39865`), потому что данные живые и меняются.

### 3.3. HTML fallback

```bash
uv run ozon-parse --source html 'https://www.ozon.ru/product/.../'
```

Работает через JSON-LD и Open Graph. На реальном Ozon почти наверняка упрётся в антибот, но как офлайн-парсер сохранённых страниц и как резервный источник остаётся.

---

## 4. Что не работает и почему

### 4.1. Прямой HTTP к API

`httpx`/`curl` получают:

```text
HTTP 307 → редирект с __rr=1 и cookie __Secure-ETC
HTTP 403 → {"incidentId": "...", "challengeURL": "https://www.ozon.ru/challenge.html?..."}
```

Причина: Ozon требует полноценный браузерный JS/fingerprint, а не просто заголовки. Подделывать TLS-отпечаток и решать challenge скриптом мы не стали — это обход защиты.

### 4.2. Playwright, который сам запускает Chrome

Проверено:

- headless → `403`;
- headed → страница с заголовком `Antibot Challenge Page`, затем «Похоже, нет соединения».

Причина: автоматизированный Chrome помечен (`navigator.webdriver = true`), Ozon это видит. Ошибка парсера в этом режиме теперь честно сообщает, что дело в антибот-блоке, а не в сети.

### 4.3. CDP-режим требует ручного запуска Chrome

Это не «просто работает из коробки»: пользователь должен запустить Chrome с `--remote-debugging-port` и отдельным `--user-data-dir`. Зато используется настоящий браузер, и Ozon видит `navigator.webdriver = false`.

---

## 5. Проверенные команды

```bash
# установка (API/HTML)
uv sync

# установка браузерного режима
uv sync --extra browser

# офлайн-разбор
uv run ozon-parse --json json_responce.json '<url>'

# живой API через обычный HTTP (ожидаемо 403)
uv run ozon-parse '<url>'

# HTML
uv run ozon-parse --source html '<url>'

# браузер: автозапуск Playwright (ожидаемо блокируется Ozon)
uv run ozon-parse --source browser '<url>'

# браузер: CDP к ручному Chrome (рабочий сценарий)
uv run ozon-parse --cdp-url http://127.0.0.1:9222 '<url>'

# тесты
uv run python -m unittest discover -s tests -v

# линтер
ruff check ozon_parser tests
ruff format --check ozon_parser tests
```

---

## 6. Тесты и качество

- **18 тестов**, все проходят.
- Покрыто:
  - разбор `json_responce.json` (цены, рейтинг, отзывы, SKU, изображения, характеристики, продавец);
  - альтернативные формы `widgetStates` (dict вместо JSON-строк);
  - `webDescription`/`webBrand`/`OutOfStock` на синтетическом payload;
  - fallback валюты по домену (`.kz` → `KZT`);
  - ошибки: `incidentId`, отсутствие `widgetStates`, битый JSON;
  - сборка URL API;
  - HTML/JSON-LD;
  - CLI `--json`;
  - CLI-опции браузерного режима.
- `ruff check` — чисто, `ruff format --check` — чисто.

Отдельно проверено, что `import ozon_parser` работает **без установленного Playwright**: браузерный модуль поднимается лениво и при вызове даёт понятную ошибку с командой установки.

---

## 7. Архитектура

| Файл | Роль |
|---|---|
| `ozon_parser/parser.py` | dataclass `OzonProduct`, HTML/JSON-LD парсер |
| `ozon_parser/api.py` | сборка URL `entrypoint-api`, разбор `widgetStates`, прямой HTTP-запрос |
| `ozon_parser/browser.py` | Playwright: автозапуск Chrome и CDP-подключение, challenge-wait |
| `ozon_parser/fetch.py` | HTML-загрузчик и `OzonFetchError` |
| `ozon_parser/urls.py` | проверка доменов Ozon (`ru/kz/by/uz/com`) |
| `ozon_parser/cli.py` | CLI: `--json`, `--source`, `--cdp-url`, `--cookie`, таймауты |
| `tests/test_parser.py` | офлайн-тесты |
| `README.md` | пользовательская документация |
| `docs/STATUS.md` | этот файл |
| `docs/REASONING.md` | журнал решений и экспериментов |

Ключевые поля `OzonProduct`:

```text
source_url, name, description, price, currency, availability,
rating, review_count, sku, image_urls,
original_price, card_price, in_stock, seller, brand, characteristics
```

Семантика цен:

- `price` — обычная текущая цена (`webPrice.price`);
- `card_price` — цена с Ozon Картой (`webPrice.cardPrice`);
- `original_price` — цена до скидки (`webPrice.originalPrice`).

---

## 8. Окружение

| Компонент | Версия/значение |
|---|---|
| Python | 3.14.6 (в `.venv`) |
| httpx | 0.28.1 |
| Playwright | 1.64.1 |
| Chrome | 155.0.8059.85 |
| uv | 0.13.3 |
| ОС | macOS |

Особенности:

- `.venv/` и `.uv-cache/` в `.gitignore`.
- `uv.lock` зафиксирован.
- В песочнице этого окружения Chrome при ручном запуске потребовал `--no-sandbox`; в обычном терминале пользователя это не нужно и не рекомендуется.
- `~/.ozon-chrome` — отдельный профиль для CDP; в нём лежат cookie, его нельзя коммитить и не стоит делать общим.

---

## 9. Риски

1. **Правила Ozon.** Автоматизация публичных страниц может нарушать ToS; challenge-защита существует не просто так. Нужны умеренные запросы и уважение к ограничениям.
2. **Нестабильность API.** Ozon может менять `widgetStates`, названия виджетов, структуру цен. Парсер ищет по префиксам и не падает на отсутствующих полях, но 100% гарантии нет.
3. **Зависимость от браузера.** CDP-режим требует запущенного Chrome с remote debugging. В headless-сервере он не заработает без графической сессии.
4. **Cookie/профиль.** Профиль `~/.ozon-chrome` содержит сессионные данные. Не публиковать, не коммитить, не передавать.
5. **Цена и наличие.** Зависят от региона, аккаунта, Ozon Карты и момента времени. `price` — обычная цена, не «минимальная любой ценой».
6. **Антибот может измениться.** Если Ozon начнёт блокировать и CDP, останется только сохранённый JSON/ручной экспорт.

---

## 10. Следующие шаги

### P0 — перед активным использованием

- [ ] Добавить ограничение частоты запросов (rate limit) и ретраи с backoff.
- [ ] Добавить `--dry-run`/`--api-url` для отладки без запуска браузера.
- [ ] Проверить CDP-режим на 3–5 разных карточках (акции, нет в наличии, без отзывов).

### P1 — удобство

- [ ] Импорт HAR-файла из DevTools (чтобы не вырезать ответ руками).
- [ ] Сохранение профиля CDP по умолчанию в `~/.ozon-chrome`.
- [ ] Команда `ozon-parse doctor` — проверяет CDP, Playwright, доступность API.
- [ ] Нормализация изображений (размеры, `ir-20` vs `ir.ozone.ru`).

### P2 — качество данных

- [ ] Категория/бренд из breadcrumbs и полных характеристик.
- [ ] Описание из `webDescription`, если Ozon его отдаёт.
- [ ] Типизированные модели характеристик (dict → структура).
- [ ] Асинхронный вариант для пакетной обработки.

### P3 — инфраструктура

- [ ] CI с тестами и `ruff`.
- [ ] Публикация пакета/релиза.
- [ ] Docker-образ без браузера (только `--json`/HTML).

---

## 11. Handoff: что проверить при возврате к задаче

1. `uv run python -m unittest discover -s tests -v` — 18 тестов зелёные?
2. `ruff check ozon_parser tests` — чисто?
3. `uv run ozon-parse --json json_responce.json '<url>'` — поля на месте?
4. Chrome запущен с `--remote-debugging-port=9222`?
5. `curl http://127.0.0.1:9222/json/version` отвечает?
6. `uv run ozon-parse --cdp-url http://127.0.0.1:9222 '<url>'` — живой ответ?
7. Если 403 — сначала смотреть `challengeURL`/заголовок страницы, а не менять заголовки наугад.

---

## 12. Определение готовности (для этой итерации)

- [x] API-ответ разбирается офлайн.
- [x] CLI умеет `--json`, `--source api/html/browser`, `--cdp-url`.
- [x] Живой запрос через CDP проверен.
- [x] Ошибки антибота объясняются человеку.
- [x] Тесты и линтер зелёные.
- [x] README описывает рабочий и резервные сценарии.
- [ ] Массовая обработка и rate limit — следующая итерация.
