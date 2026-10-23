# Pre-delivery checklist

## STATUS.md

- [ ] Header has date, project path, status, version/environment.
- [ ] Task is one short paragraph with the concrete success criterion.
- [ ] Result table uses `works / partial / blocked` and names the exact check.
- [ ] Every "works" claim has a command, test, live value, or screenshot.
- [ ] "Does not work" explains symptom → cause → classification.
- [ ] Run instructions are copy-paste and include ports/prerequisites.
- [ ] Test count matches the latest run; mocks are disclosed.
- [ ] Live values are dated or marked as variable.
- [ ] Database/schema/API checks are included when relevant.
- [ ] Limitations are numbered and have impact.
- [ ] Next steps are prioritized and actionable.
- [ ] Handoff checklist can be executed by someone else.
- [ ] Definition of done distinguishes checked and unchecked.
- [ ] Assets are linked with relative paths and are current.

## REASONING.md

- [ ] Disclaimer says it is reconstructed, not raw chain-of-thought.
- [ ] Fact / hypothesis / decision are separated.
- [ ] Request decomposition names constraints and success criteria.
- [ ] Architecture alternatives and tradeoffs are shown.
- [ ] Experiments include failed hypotheses.
- [ ] Errors include diagnosis and fix, not just the final state.
- [ ] Principles are transferable, not a task log.
- [ ] "What I would do differently" is specific.
- [ ] Checklist and exercises are usable.
- [ ] Main takeaway is one or two sentences.
- [ ] Appendix facts match STATUS.md.

## Safety and hygiene

- [ ] No cookies, tokens, passwords, session ids, signed URLs, or private keys.
- [ ] No unnecessary absolute home paths.
- [ ] No personal/customer data.
- [ ] No placeholder `{{...}}` left.
- [ ] No stale screenshot from before a fix.
- [ ] No claim of visual verification when only HTML was checked.
- [ ] Old features explicitly checked if the task added a new one.

## Files and links

```bash
[ -f docs/<TASK-ID>/STATUS.md ]
[ -f docs/<TASK-ID>/REASONING.md ]
grep -RE "\{\{(TASK_ID|TITLE|DATE|PROJECT)\}\}" docs/<TASK-ID> || true
```
