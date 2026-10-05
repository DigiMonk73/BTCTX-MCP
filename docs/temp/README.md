# docs/temp: checklists for work under way

To-dos and plans are GitHub issues on this repository (`AGENTS.md`,
"Working through GitHub"). This folder holds only what doesn't fit an issue
well: a long checklist for work under way, one file per topic, named for what
it is (`startos-box-test-v1.2.2.md`, not `notes.md`), with its steps as
checkboxes and a link to its issue.

When it's all done, move anything worth keeping somewhere lasting (the code
and CHANGELOG, a doc), close the issue, tick its box in `docs/ROADMAP.md` if
it was on the roadmap, and **delete the file**.

What's next overall is in `docs/ROADMAP.md`. The StartOS package keeps its
own `startos/TODO.md`, Start9's standard file, under Start9's rule: an item is
removed when it's done, not ticked. Checklists stay here, never in `startos/`.

`backend/tests/test_todo_lists.py` checks that every item is a checkbox and
that no separate to-do file comes back.
