# CONTRIBUTING.md — Development Rules & Workflow

## Branching & Commit Conventions
- Main development branch is `dev`. Protected branch is `main`.
- All feature work must happen on dedicated topic branches named `feature/<feature-name>`.
- Commit messages must be concise and prefixed by module context:
  - `[backend]` for FastAPI backend changes
  - `[federated]` for Flower FL layer changes
  - `[dashboard]` for UI changes
  - `[docs]` for documentation changes

## Testing & Quality Assurance
- All pull requests must pass the automated pytest test suite (`pytest -v tests/`).
- Zero real network calls or hardware dependencies permitted in CI tests.

## Pull Request Policy
- Submit PRs targeting `dev`.
- Requires complete PR template checklist verification.
- Do NOT self-merge PRs.
