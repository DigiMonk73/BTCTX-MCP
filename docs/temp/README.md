# docs/temp: work in progress

Everything here is checkboxes: tick a box when the thing is done.

- **`TODO.md`**: specific to-dos, one line each (`- [ ] …`). Tick `[x]` when
  done. At each release, remove the ticked items: the CHANGELOG has them then.
- **Plans and checklists**: one file per topic, named for what it is
  (`startos-box-test-v1.2.2.md`, not `notes.md`), with its steps as
  checkboxes. When it's all done, move anything worth keeping somewhere
  lasting (the code and CHANGELOG, a doc), tick its box in
  `docs/ROADMAP.md` if it was on the roadmap, and **delete the file**.
- **What's next overall** (features, larger work) is in `docs/ROADMAP.md`,
  also checkboxes, ticked when done and cleared at the release that ships
  them.

The StartOS package keeps its own `startos/TODO.md`: Start9's standard file,
copied to the repository Start9 forks, for package-only items under the same
rules. Plans stay here, never in `startos/`.

`backend/tests/test_todo_lists.py` fails if a TODO file is missing or an
item isn't a checkbox.
