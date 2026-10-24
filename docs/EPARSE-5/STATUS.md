# EPARSE-5 — статус: поиск по названию и автопарсинг карточек

**Дата:** 2026-10-24  
**Проект:** `ozon-parser`  
**Статус:** фича готова и проверена на живой выдаче.  
**Версия:** 0.5.0  
**Окружение:** Python 3.14.6, PostgreSQL 17 (Docker), Chrome 155 по CDP.  
**OpenSpec change:** `search-free-text-product-details`

---

## 1. Задача

Улучшить поиск по выдаче Ozon:

1. разрешить вводить не только ссылку на `/category/...` или `/search/...`,
   но и обычное название товара;
2. внутри одного запуска поиска автоматически разбирать каждую карточку
   товара и сохранять подробности в PostgreSQL;
3. не ломать существующий одиночный парсинг `/runs` и CLI.

Пример входа:

```text
macbook air m5
```

Ожидаемый поисковый URL:

```text
https://www.ozon.ru/search/?text=macbook+air+m5&from_global=true
```

---

## 2. Результат одним взглядом

| Сценарий | Статус | Чем проверено |
|---|---|---|
| Поиск по названию товара | ✅ работает | живой запуск `864ce8d6…`: 3 позиции, `duration_ms=1094` |
| Поиск по ссылке на категорию | ✅ работает | живой запуск `6f8ec2fd…`: 2 позиции, `duration_ms=689` |
| Ссылка на `/product/...` отклоняется | ✅ работает | `test_search_invalid_url_is_rejected` |
| Слишком короткий текст отклоняется | ✅ работает | `test_search_too_short_text_is_rejected` |
| Разбор карточек сохраняется в БД | ✅ работает | живой запуск: `products_count=3`, `products_failed=0` |
| Ошибка карточки не роняет поиск | ✅ работает | `test_search_persists_product_details`: 1 успешная + 1 ошибочная |
| Выключение разбора карточек | ✅ работает | живой запуск: 5 позиций, 0 запросов карточек |
| UI показывает детали карточки | ✅ работает | живой запуск + скриншот 1366×900 |
| Старый одиночный парсинг | ✅ не сломан | 19 тестов парсера, 16 тестов веб-приложения |

Первый живой запуск с разбором карточек получил `HTTP 403` и captcha. После
того как пользователь прошёл проверку в Chrome, повторный запуск разобрал
3 из 3 карточек за 1,1 секунды. Оба состояния сохранены в БД и описаны ниже.

---

## 3. Что работает

### 3.1. Свободный текст

`SearchCreate.url` остался единственным обязательным полем, но теперь принимает
два формата:

- ссылку Ozon на `/category/...` или `/search/...`;
- текст, который нормализуется в `/search/?text=...` через `urlencode`.

Пробелы схлопываются:

```text
"  macbook   air m5  " → "macbook air m5"
```

Живой запуск:

```bash
curl -X POST http://127.0.0.1:8001/api/searches \
  -H 'Content-Type: application/json' \
  -d '{"url":"macbook air m5","source":"cdp","limit":3,
       "parse_products":true,"timeout":45,"challenge_timeout":120}'
```

Результат:

```text
status=success, items=3, products_count=3, products_failed=0, duration_ms=1094
search_url=https://www.ozon.ru/search/?text=macbook+air+m5&from_global=true
```

Сырой ответ: [`assets/live-cards-success.json`](assets/live-cards-success.json).

### 3.2. Ссылка на выдачу по-прежнему работает

Живой запуск по исходному URL категории:

```text
https://www.ozon.ru/category/noutbuki-15692/apple-26303000/?text=macbook+air+m5
```

Результат: `items_count=2`, `duration_ms=689`, URL не изменён.
Сырой ответ: [`assets/live-url-search.json`](assets/live-url-search.json).

### 3.3. Автоматический разбор карточек

При `parse_products=true` (по умолчанию) `fetch_search_browser` после списка
позиций запрашивает `entrypoint-api` для каждой карточки **в той же браузерной
сессии**. Это переиспользует cookies и уже пройденный challenge.

Сохранение:

- `search_item_products` — одна запись на позицию;
- поля: `status`, `name`, `description`, `sku`, `price`, `card_price`,
  `original_price`, `currency`, `in_stock`, `seller`, `brand`, `rating`,
  `review_count`, `image_url`, `characteristics`, `data`, `error`,
  `duration_ms`, `parsed_at`;
- `data` — полный `OzonProduct.to_dict()` в JSONB.

Живой результат:

```text
position=1: seller="AE Dubai Freezone O...", in_stock=true,
            card_price=105639.00, characteristics=5, duration_ms=111
position=2: seller="AE Dubai Freezone O...", in_stock=true,
            card_price=105377.00, characteristics=5, duration_ms=115
position=3: seller="AE Dubai Freezone O...", in_stock=true,
            card_price=123147.00, characteristics=5, duration_ms=75
```

Офлайн-тест дополнительно проверяет partial success: одна карточка успешна,
вторая — `HTTP 404`; поиск остаётся `success`, `products_failed=1`.

### 3.4. UI

- Поле «Ссылка или название товара» с `type="text"`;
- чекбокс «Разбирать карточки», по умолчанию включён;
- в детальной выдаче — счётчик «Карточек разобрано X из N»;
- у каждой позиции бейдж «Карточка разобрана / не разобрана»;
- раскрывающийся блок с продавцом, брендом, наличием, ценой с картой,
  рейтингом, описанием и характеристиками;
- ошибка карточки раскрывается отдельно;
- кнопка «Повторить» сохраняет режим `parse_products`.

Скриншоты:

![Форма поиска](assets/search-form.png)

![Детали карточки в выдаче](assets/search-detail.png)

### 3.5. Старые сценарии

- `POST /api/runs`, `/runs`, CLI и `parse_runs` не менялись по контракту.
- Общий прогон: 52 теста, все проходят.
- 19 тестов парсера, 17 тестов поиска, 16 тестов веб-приложения.

---

## 4. Что не работает и почему

### 4.1. Первый запрос карточек упёрся в captcha

Симптом первого живого запуска:

```text
position=1 product_status=failed
error=Ozon отклонил запрос карточки (HTTP 403, антибот).
```

Причина: Chrome на `http://127.0.0.1:9222` при открытии `/product/...`
показал `Antibot Captcha` («Сопоставьте пазл»). Это внешняя антибот-защита
Ozon, а не ошибка парсера.

Что сделано:

- ответ с `captchaURL` распознаётся (`_challenge_url`);
- в не-headless режиме парсер открывает проверку и ждёт до
  `challenge_timeout` секунд;
- после прохождения проверки повторяет API-запрос;
- если проверка не пройдена, ошибка сохраняется у карточки, остальные позиции
  не ждут таймаут повторно.

После ручного прохождения captcha пользователем тот же сценарий разобрал
3 из 3 карточек. Ограничение остаётся: captcha нужно проходить вручную.

### 4.2. Нет прогресса по карточкам

Пока идёт разбор N карточек, UI показывает общий статус `running`, но не
количество уже обработанных. Для 100 позиций это заметное ожидание.

### 4.3. Docker

В Docker-образе нет Playwright и Chrome, поэтому `source=cdp/browser` внутри
контейнера не работает. Это ограничение существовало до задачи.

---

## 5. Как запустить

```bash
docker compose up -d db
uv sync --extra browser
uv run uvicorn app.main:app --reload --port 8001
```

Порт 8001 выбран потому, что 8000 занят другим локальным приложением.

Chrome для CDP:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.ozon-chrome"
```

Открыть `http://127.0.0.1:8001/searches`, ввести `macbook air m5`,
оставить «Разбирать карточки» включённым.

Если Ozon покажет captcha — пройти её в открытом окне Chrome. Парсер ждёт
до `challenge_timeout` (по умолчанию 120 секунд).

---

## 6. Проверка

### 6.1. Тесты

```bash
UV_CACHE_DIR=$PWD/.uv-cache uv run python -m unittest discover -s tests -v
```

Результат:

```text
Ran 52 tests in 0.315s
OK
```

По модулям:

| Модуль | Тестов |
|---|---:|
| `tests/test_parser.py` | 19 |
| `tests/test_search_parser.py` | 17 |
| `tests/test_web_app.py` | 16 |

### 6.2. Линтер и формат

```bash
UV_CACHE_DIR=$PWD/.uv-cache uv run ruff check .
UV_CACHE_DIR=$PWD/.uv-cache uv run ruff format --check .
```

Результат:

```text
All checks passed!
38 files already formatted
```

### 6.3. Живые запуски

| Запуск | Вход | Позиции | Карточки | Время |
|---|---|---:|---:|---:|
| `7855ce3d…` | `macbook air m5`, до captcha | 3 | 0 успешных, 3 ошибки | 1116 мс |
| `6f8ec2fd…` | URL категории | 2 | не запрашивались | 689 мс |
| `d4854d2b…` | `macbook air m5`, `parse_products=false` | 5 | не запрашивались | 9557 мс |
| `864ce8d6…` | `macbook air m5`, после captcha | 3 | 3 успешных | 1094 мс |

Сырые ответы:

- [`assets/live-free-text.json`](assets/live-free-text.json) — первый запуск
  с ошибками карточек;
- [`assets/live-cards-success.json`](assets/live-cards-success.json) — успешный
  разбор;
- [`assets/live-no-cards.json`](assets/live-no-cards.json) — без карточек;
- [`assets/live-url-search.json`](assets/live-url-search.json) — по ссылке.

### 6.4. База

```bash
docker compose exec -T db psql -U ozon -d ozon \
  -c '\d search_item_products' \
  -c 'select status, count(*) from search_item_products group by status;'
```

Проверено:

- таблица создана автоматически;
- уникальный индекс по `search_item_id`;
- FK на `search_items.id` с `ON DELETE CASCADE`;
- 3 строки `success` и 3 строки `failed` от живых запусков;
- у успешных строк заполнены `characteristics`, `data`, `seller`,
  `card_price`, `parsed_at`.

### 6.5. UI

- 1366×900, headless Chromium;
- форма и детальная страница отрисованы;
- детали карточки раскрываются;
- изображения и CSS загружаются;
- тест `test_search_persists_product_details` проверяет HTML-текст.

---

## 7. Архитектура и данные

```text
input (URL или текст)
  → SearchCreate.validate_url()
  → /search/?text=... при тексте
  → fetch_search_browser(include_products=...)
  → tileGridDesktop.items + pagination
  → для каждой позиции: entrypoint-api карточки в той же сессии
  → SearchRun + SearchItem + SearchItemProduct
  → /searches/{id}
```

Новая таблица:

```text
search_runs 1──N search_items 1──1 search_item_products
```

`parse_runs` не участвует: это отдельная история одиночных парсингов.
Подробности карточки — снимок внутри конкретной выдачи.

Ключевые файлы:

- [`ozon_parser/search.py`](../../ozon_parser/search.py) — URL из текста,
  `include_products`, разбор карточек;
- [`app/search_schemas.py`](../../app/search_schemas.py) — вход и выход API;
- [`app/db/models.py`](../../app/db/models.py) — `SearchItemProduct`;
- [`app/services/search_runner.py`](../../app/services/search_runner.py) —
  сохранение;
- [`app/templates/search_detail.html`](../../app/templates/search_detail.html) —
  детали;
- [`app/static/search.css`](../../app/static/search.css) — стили.

---

## 8. Ограничения

1. **Captcha на карточках.** Ozon чаще проверяет `/product/...`, чем выдачу.
   Проверку нужно проходить вручную; без неё карточки сохраняются как `failed`.
2. **Нет headless-обхода.** В headless captcha не проходится; это осознанно.
3. **Нет прогресса по карточкам.** Статус общий, счётчик появляется только
   после завершения.
4. **Последовательные запросы.** 100 карточек = 100 запросов; параллельность
   не добавлена, чтобы не усиливать антибот-риск.
5. **Нет retry.** Ошибка карточки не повторяется автоматически.
6. **Только Ozon.** Другие площадки не поддерживаются и не планировались.
7. **Нет Alembic.** Новая таблица создаётся `create_all`; для изменения
   существующих колонок миграция всё ещё нужна.
8. **Не все поля заполнены.** В живом ответе `brand` и `description` были
   `null`/пустыми: Ozon не отдал их в `entrypoint-api` для этих карточек.
   Парсер не выдумывает значения.

---

## 9. Следующие шаги

### P0

- Повторить живой запуск на 100 позициях и замерить время; проверить, что
  последовательный разбор не упирается в таймауты.

### P1

- Добавить прогресс: `products_done / products_total` в `SearchRun.options` или
  отдельное поле, обновляемое после каждой карточки.
- Добавить один retry для `HTTP 429`/сетевой ошибки с паузой.
- Показывать в UI время начала и текущую карточку.

### P2

- Добавить Alembic и миграцию для будущих изменений схемы.
- Сделать общий каталог товаров по SKU, если понадобится история между
  выдачами.
- Добавить экспорт выдачи с карточками в CSV/JSON.

---

## 10. Чек-лист передачи

- [ ] `docker compose up -d db` — PostgreSQL healthy.
- [ ] `uv run uvicorn app.main:app --port 8001` — `/health` возвращает `0.5.0`.
- [ ] `uv run python -m unittest discover -s tests` — 52 теста, OK.
- [ ] `uv run ruff check .` — без ошибок.
- [ ] `uv run ruff format --check .` — без изменений.
- [ ] Chrome на 9222 открывает Ozon.
- [ ] Поиск `macbook air m5` создаёт запись в `/searches`.
- [ ] При `parse_products=true` в `search_item_products` появляются строки.
- [ ] Ошибка одной карточки не меняет `search_runs.status` на `failed`.
- [ ] Старый `/runs` по-прежнему создаёт `parse_runs`.

---

## 11. Definition of done

- [x] Свободный текст превращается в поисковый URL.
- [x] Ссылка на выдачу поддерживается.
- [x] Ссылка на карточку отклоняется.
- [x] `parse_products` управляет разбором.
- [x] Карточки сохраняются в новую таблицу.
- [x] Ошибка карточки не роняет поиск.
- [x] UI показывает детали и ошибки.
- [x] Живой успешный разбор карточек подтверждён: 3 из 3.
- [x] 52 теста проходят.
- [x] `ruff check` и `ruff format --check` чистые.
- [x] README и OpenSpec обновлены.
