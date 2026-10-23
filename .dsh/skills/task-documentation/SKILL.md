---
name: task-documentation
description: Create per-task documentation artifacts — a STATUS/result report and a REASONING decision journal — with evidence, commands, limitations, next steps, and a reusable folder layout.
whenToUse: Use when the user asks for task documentation, a status/result artifact, a decision journal, or a per-task docs folder.
---

# Task documentation artifacts

Create a durable, evidence-backed documentation bundle for a completed or in-progress task. The bundle has two complementary documents:

- `STATUS.md` — the result: what was requested, what works, how to run it, how it was verified, what is limited, and what comes next.
- `REASONING.md` — the decision journal: reconstructed hypotheses, experiments, tradeoffs, mistakes, and principles. It is not a raw chain-of-thought transcript.

Write the documents in the user's language. The templates in `templates/` are Russian because this workspace uses Russian; adapt the language when needed.

## Non-negotiables

1. **Never present reconstructed reasoning as verbatim chain-of-thought.** State that it is a reconstruction. Do not invent private thoughts, timestamps, or certainty you did not have.
2. **Every factual claim needs evidence.** Link to a test, command output, screenshot, schema, log, or file. If something was not verified, say so.
3. **Do not change product code while doing documentation-only work.** If verification requires a code change, do it separately and document it.
4. **One task, one folder.** Do not overwrite an existing task folder. Use the next free task id or the folder the user named.
5. **No secrets.** Remove cookies, tokens, passwords, incident URLs with signatures, personal paths that should not be shared, and private keys. Redact with `[redacted]`.
6. **No marketing language.** Write concrete facts, tradeoffs, and limitations. Avoid "seamless", "revolutionary", "fully tested" unless literally true.
7. **Close the loop.** A status document without verification commands and a handoff checklist is incomplete.

## Folder layout

Prefer this layout under the project's docs root:

```text
docs/<TASK-ID>/
├── STATUS.md
├── REASONING.md
└── assets/
    ├── screenshot-1.png
    └── sample-output.json
```

`<TASK-ID>` should be short and stable, for example `EPARSE-4`, `AUTH-2`, `INFRA-7`. If the user already created a folder, use it exactly.

## Workflow

### 1. Establish the task frame

Collect, without guessing:

- the original request and the actual goal behind it;
- task id and docs root;
- what changed (files, endpoints, tables, UI, commands);
- what was verified and what was not;
- environment facts: OS, runtime, dependency versions, database, ports;
- known limitations and the next useful step.

If a fact is unknown, write `не проверено` / `not verified` rather than inventing it.

### 2. Scaffold the folder

Use the bundled script:

```bash
python3 <skill-base>/scripts/scaffold_task_docs.py \
  --root docs \
  --task-id EPARSE-4 \
  --title "Короткое название задачи"
```

It creates `docs/<TASK-ID>/STATUS.md`, `REASONING.md`, and `assets/.gitkeep`, and refuses to overwrite existing files. If the script is unavailable, copy `templates/STATUS.md` and `templates/REASONING.md` and replace the placeholders manually.

### 3. Write STATUS.md

Use `templates/STATUS.md` and keep these sections:

1. **Header** — date, project path, status, version/environment.
2. **Task** — the concrete request in one short paragraph.
3. **Result at a glance** — a table of scenarios with `works / partial / blocked` and the exact check performed.
4. **What works** — grouped by user-visible capability, with commands and real output.
5. **What does not work** — symptoms, root cause, and whether it is a code bug, environment limit, or external constraint.
6. **How to run** — copy-paste commands, ports, prerequisites.
7. **Verification** — tests with counts, live runs with values, database/schema checks, Docker/API checks.
8. **Architecture / data model** — only what helps the reader operate or extend the result.
9. **Limitations** — explicit, numbered, with impact.
10. **Next steps** — prioritized `P0/P1/P2`, each actionable.
11. **Handoff checklist** — the exact checks the next person should run.
12. **Definition of done** — checked and unchecked items.

Include screenshots or sample outputs in `assets/` and link them with relative paths. Prefer one strong screenshot over many near-duplicates.

### 4. Write REASONING.md

Use `templates/REASONING.md`. It should read like an engineering retrospective, not a diary:

- **Disclaimer** — reconstructed, not raw chain-of-thought.
- **How to read** — fact vs hypothesis vs decision.
- **Request decomposition** — literal ask vs underlying need and constraints.
- **Reconnaissance** — what existed, what was measured, what was surprising.
- **Architecture decisions** — alternatives considered, why one was chosen, what was traded away.
- **Experiments** — a table with hypothesis, experiment, observation, conclusion. Include failed hypotheses.
- **Errors and fixes** — what broke, why, how it was diagnosed, what changed.
- **Principles** — transferable heuristics, not just task-specific steps.
- **What I would do differently** — honest, specific.
- **Checklist and exercises** — for a similar future task.
- **Main takeaway** — one or two sentences.
- **Appendix** — verified facts and evidence links.

Do not claim a linear, flawless thought process. Show the branch points and the cost of the wrong branches.

### 5. Cross-check the documents

Before finishing:

- every command in `STATUS.md` was actually run or is clearly marked as an example;
- test counts match the latest run;
- file paths and links resolve;
- screenshots are current (no stale timestamps or pre-fix UI);
- `REASONING.md` mentions the real mistakes, not decorative ones;
- limitations are consistent with the result table;
- no placeholders like `{{TITLE}}` remain;
- no secrets or personal data;
- old features are explicitly checked if the task added a new one.

### 6. Verify the artifact

Run a lightweight check:

```bash
[ -f docs/<TASK-ID>/STATUS.md ]
[ -f docs/<TASK-ID>/REASONING.md ]
grep -RE "\{\{(TASK_ID|TITLE|DATE|PROJECT)\}\}" docs/<TASK-ID> || true
```

If the task changed code, also run the repository's tests and linter and record the exact commands and counts in `STATUS.md`. If tests were not run, say so in the limitations.

## Evidence rules

Use this hierarchy:

1. **Executed command + output** — strongest.
2. **Test result with count** — strong, but state what was mocked.
3. **Live run with real values** — strong, but note that values change.
4. **Screenshot** — strong for UI, weak for behavior not visible in the image.
5. **Code inspection** — acceptable for static facts, not for runtime behavior.
6. **Assumption** — label it as an assumption.

Prefer exact numbers: `39 tests`, `16 items`, `1842 ms`, `HTTP 403`, `PostgreSQL 17`. Avoid "many", "fast", "works well".

## Redaction

Remove or replace:

- cookies, `Authorization` headers, tokens, session ids;
- signed challenge URLs and incident ids if they contain sensitive parameters;
- absolute home paths when they are not needed for reproduction;
- customer data, personal email addresses, phone numbers;
- database passwords (use `***`).

Keep public URLs, SKU examples, and test fixture values.

## Formatting and linking

- Use Markdown headings, tables, and fenced code blocks with a language tag.
- Link to files with relative paths from the document: `../app/main.py`, `assets/dashboard.png`.
- Put commands in copy-paste blocks, one logical step per block.
- Use the user's language for prose and UI labels; keep code identifiers and file names exact.
- Use dates in ISO-like form (`2026-10-23`) in headers.

## Templates and resources

- `templates/STATUS.md` — result/status skeleton.
- `templates/REASONING.md` — decision-journal skeleton.
- `scripts/scaffold_task_docs.py` — creates the folder and fills placeholders.
- `references/checklist.md` — compact pre-delivery checklist.

Read only the resources you need. Do not enumerate the skill directory.

## What not to do

- Do not call the output "full chain-of-thought"; call it a reconstructed decision journal.
- Do not claim visual verification from HTML alone; render or screenshot when appearance matters.
- Do not copy a previous task's numbers, versions, or limitations without re-checking.
- Do not bury a blocking limitation in a footnote; put it in the result table and limitations.
- Do not use the skill to avoid doing the actual work; it documents work that was done or explicitly marks what remains.
