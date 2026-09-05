# Team Workflow & Contribution Rules

This document is the single source of truth for how our team of 4 works on this
repo simultaneously without stepping on each other. Read this before writing
any code.

## 1. Branch Structure

- `main` — protected. Always working, always demo-able. No one pushes here directly.
- `dev` — integration branch. Feature branches merge here first.
- `feature/<module>-<short-desc>` — where all actual work happens.

Examples:
- `feature/ppe-yolov11n-training`
- `feature/zone-intrusion-bytetrack`
- `feature/bandit-decision-layer`
- `feature/backend-fastapi-routes`

## 2. Before You Start Coding

1. Pull latest `dev`: `git checkout dev && git pull`
2. Create your feature branch off `dev`: `git checkout -b feature/your-module`
3. Check `INTERFACES.md` — do not change the shared event schema without
   telling the other 3 people first. If you need a new field, open a PR to
   `INTERFACES.md` alone and get a thumbs-up in the group chat before building
   against it.

## 3. While Working

- Commit small, commit often. One logical change per commit.
- Commit message format: `[module] short description`
  - Example: `[ppe] add confidence threshold config`
- Never commit: model weights (`.pt`, `.pth`, `.onnx`), datasets, `.env` files,
  `__pycache__/`, `venv/`. These are in `.gitignore` — check it's actually
  ignoring them before your first commit.
- Push your feature branch to GitHub daily minimum, even if incomplete. A
  branch only on your laptop can't be reviewed and can't be recovered if your
  machine has issues.

## 4. Testing Before Integration (mandatory, not optional)

Every module must have its own test file under `tests/` that runs
independently of the other three modules, using mocked/fake data matching
`INTERFACES.md` — not real detector output, not real video.

- PPE module: test on a handful of known images with known expected labels.
- Zone intrusion: test the polygon-check + debounce logic with synthetic
  coordinate sequences (no real video needed).
- Bandit: test on a fixed fake batch of (context, action, reward) tuples —
  verify it updates and doesn't crash on edge cases (empty batch, all-negative
  rewards, etc.).
- Backend: test each FastAPI route with a mock request/response, no live DB
  needed.

**Rule: a PR cannot be merged into `dev` unless its tests pass.** If you don't
have tests yet, the PR stays in draft.

## 5. Pull Request Process

1. Open PR from your `feature/*` branch into `dev` (never straight to `main`).
2. Fill out the PR template (auto-loads — see
   `.github/pull_request_template.md`).
3. At least **one other teammate reviews and approves** before merge — no
   self-merging, even if it "should be fine."
4. CI must pass (see `.github/workflows/ci.yml`) before merge is allowed.
5. Squash-merge into `dev` once approved, delete the feature branch after.

## 6. Merging `dev` into `main`

- Only done together, at agreed checkpoints (e.g., before each review
  milestone), not continuously.
- Before merging to `main`: run the full test suite, and do a quick live
  smoke-test if possible (run the actual pipeline end-to-end on sample data).
- Tag the release: `git tag review2-checkpoint` (or similar) so you can always
  come back to exactly what was demoed.

## 7. Keeping a Record of Decisions

Design decisions (e.g., "we chose contextual bandit over DQN because...")
should not just live in chat — write them into `docs/decisions.md` as short
dated entries. This becomes directly useful for your report/viva later, and
prevents the team from re-litigating a decision that was already made for a
reason someone forgot.

Format:
```
## 2026-09-05 — Bandit over DQN for decision layer
Decided: contextual bandit instead of DQN.
Why: alert decisions are single-step, not sequential; bandit is more
sample-efficient with sparse operator feedback and cheaper to update
incrementally.
```

## 8. Weekly Sync (minimum viable coordination)

- Short check-in, even 15 minutes: what did you finish, what are you touching
  next, does it touch `INTERFACES.md` or anyone else's module.
- Update `docs/decisions.md` and `README.md`'s "Current Status" section if
  anything material changed.

## 9. Conflict Resolution

- If two people need to touch the same file, whoever starts first posts in
  the group chat. The second person waits or coordinates a merge plan before
  starting, rather than discovering a conflict at PR time.
- Merge conflicts get resolved by the two people involved, together — not by
  whoever hits it first guessing what the other person meant.
