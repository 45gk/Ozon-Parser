# EPARSE-4 — статус: скилл `task-documentation`

**Дата:** 2026-10-23  
**Проект:** `/Users/igor/Documents/test_project/ozon-parser`  
**Статус:** готово, скилл загружается и проверен.  
**Версия:** 1.0.0

---

## 1. Задача

Создать переиспользуемый скилл для оформления документации по задачам в формате,
который уже используется в проекте:

- `STATUS.md` — результат, проверка, ограничения, следующие шаги;
- `REASONING.md` — восстановленный журнал решений, а не сырой chain-of-thought;
- отдельная папка на каждую задачу (`docs/<TASK-ID>/`);
- шаблоны и скрипт для быстрого создания папки.

---

## 2. Итог одной таблицей

| Сценарий | Статус | Что именно проверено |
|---|---|---|
| Скилл найден в каталоге | ✅ работает | `skill("task-documentation")` вернул инструкции |
| Scaffold создаёт папку | ✅ работает | `docs/EPARSE-4/` с двумя файлами и `assets/` |
| Защита от перезаписи | ✅ работает | повторный запуск вернул exit 1 |
| Плейсхолдеры заменяются | ✅ работает | `grep -RE '\{\{(TASK_ID|TITLE|DATE|PROJECT)\}\}'` — пусто |
| Шаблоны и чек-лист на месте | ✅ работает | 5 файлов, checksum одинаковый в двух копиях |

---

## 3. Что сделано

### 3.1. Структура скилла

```text
.dsh/skills/task-documentation/
├── SKILL.md
├── templates/
│   ├── STATUS.md
│   └── REASONING.md
├── scripts/
│   └── scaffold_task_docs.py
└── references/
    └── checklist.md
```

Каноническая копия лежит в проекте: `ozon-parser/.dsh/skills/task-documentation`.
Рабочая копия для текущей сессии — в корне workspace:
`/Users/igor/Documents/test_project/.dsh/skills/task-documentation`.

### 3.2. Что умеет

- `SKILL.md` задаёт правила: evidence-first, redaction, один task — одна папка,
  «не выдавать реконструкцию за chain-of-thought».
- `templates/STATUS.md` — скелет результата: таблица сценариев, запуск,
  проверка, архитектура, ограничения, P0/P1/P2, handoff.
- `templates/REASONING.md` — скелет журнала: факт/гипотеза/решение,
  альтернативы, эксперименты, ошибки, принципы, упражнения.
- `scripts/scaffold_task_docs.py` — создаёт `docs/<ID>/{STATUS,REASONING}.md` и
  `assets/.gitkeep`, подставляет ID задачи, заголовок, дату и путь проекта,
  отказывается перезаписывать существующую папку.
- `references/checklist.md` — короткий pre-delivery чек-лист.

### 3.3. Как использовать

Через скилл-инструмент:

```text
skill("task-documentation")
```

Создать папку под новую задачу:

```bash
python3 /Users/igor/Documents/test_project/.dsh/skills/task-documentation/scripts/scaffold_task_docs.py \
  --root docs \
  --task-id EPARSE-5 \
  --title "Название задачи"
```

---

## 4. Проверка

### 4.1. Загрузка скилла

```text
skill("task-documentation") → <skill_content name="task-documentation">
```

Скилл появился в каталоге доступных скиллов.

### 4.2. Scaffold

```bash
python3 .../scripts/scaffold_task_docs.py \
  --root docs --task-id EPARSE-4 --title "Скилл task-documentation"
```

Результат:

```text
created docs/EPARSE-4/STATUS.md
created docs/EPARSE-4/REASONING.md
created docs/EPARSE-4/assets/
```

Проверки:

- `grep -RE '\{\{(TASK_ID|TITLE|DATE|PROJECT)\}\}' docs/EPARSE-4` — пусто;
- повторный запуск — `error: ... already exists; refusing to overwrite`, exit 1;
- checksum двух копий скилла совпадает.

### 4.3. Что не проверялось

- Скилл не тестировался на задаче другого типа (например, инфраструктурной).
- Глобальная установка в `~/.dsh/skills` заблокирована sandbox-политикой;
  проверена workspace-копия.

---

## 5. Ограничения

1. Скилл документирует, а не выполняет работу; он не заменяет тесты и live-прогон.
2. Шаблоны на русском; для другого языка их нужно адаптировать (SKILL.md это разрешает).
3. Каноническая копия проектная; для глобального использования нужно скопировать
   папку в `~/.dsh/skills` вручную.
4. Две копии (проект + workspace) нужно синхронизировать при изменениях.
5. Скилл не проверяет факты автоматически; дисциплина доказательств остаётся на агенте.

---

## 6. Следующие шаги

### P0

- [ ] Прогнать скилл на следующей реальной задаче.
- [ ] Добавить пример заполненного `STATUS.md`/`REASONING.md` в `references/`.

### P1

- [ ] Добавить проверку ссылок/скриншотов в scaffold-скрипт.
- [ ] Сделать установку в `~/.dsh/skills` отдельной командой/скриптом.
- [ ] Добавить английские шаблоны.

### P2

- [ ] Версионировать скилл и вести changelog.
- [ ] Добавить шаблон для инцидентов/постмортемов.

---

## 7. Handoff-чеклист

1. `skill("task-documentation")` загружается?
2. `scaffold_task_docs.py --help` работает?
3. Повторный scaffold не перезаписывает папку?
4. В шаблонах нет незаменённых `{{...}}`?
5. `docs/EPARSE-4/STATUS.md` и `REASONING.md` на месте?

---

## 8. Определение готовности

- [x] SKILL.md с frontmatter.
- [x] Два шаблона.
- [x] Scaffold-скрипт с защитой от перезаписи.
- [x] Чек-лист.
- [x] Скилл загружается.
- [x] Проверка на реальной папке.
- [x] Документация задачи.
