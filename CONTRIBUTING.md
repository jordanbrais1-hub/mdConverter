# Contributing to mdConverter

Thanks for helping improve mdConverter! This guide covers the development setup and the security rules every change must follow.

> Found a security vulnerability? **Don't open an issue.** Follow [SECURITY.md](SECURITY.md) instead.

## Development setup

```powershell
git clone https://github.com/jordanbrais1-hub/mdConverter.git
cd mdConverter
python -m venv .venv
.venv\Scripts\activate
pip install --require-hashes -r requirements-dev.txt
pre-commit install          # enables the secret / SAST commit hooks
python -m pytest
```

## Workflow

1. Create a branch from `main` (`feature/…`, `fix/…`).
2. Make focused commits. The pre-commit hooks must pass. Never bypass them with `--no-verify`.
3. Open a pull request and fill in the template, including the security checklist.
4. CI (tests, Bandit, CodeQL, pip-audit, gitleaks, dependency review) must be green before merging.
5. Pull requests are squash- or rebase-merged to keep history linear.

## Secure coding rules

**Secrets**
- Never commit credentials, tokens, `.env` files, private keys or real customer documents. Use `.env.example` for templates.
- Secrets at runtime go through `mdconverter/secret_store.py` (the OS credential vault), never into `settings.json`, logs, exceptions or the UI.
- If a secret is committed by accident, **rotate it immediately**. Deleting the commit is not enough.

**Files and paths**
- Treat every input file as untrusted. Parsing errors must become a `ConversionResult`, never an unhandled exception.
- Compute output paths with `plan_output_paths` and keep the `ensure_within` check. Don't build paths from file contents.
- Only open folders or `.md` files through `utils.open_path` / `reveal_in_file_manager`.

**Processes and network**
- No `shell=True`, `eval`, `exec`, `pickle` or `yaml.load` on untrusted data.
- Run external programs by absolute path with an argument list.
- Keep the app offline by default. New network features must be opt-in, shown in the UI badge, documented in the README *Privacy* section, and use HTTPS (`validate_llm_endpoint`).
- Use `MarkItDown.convert_local`, never `convert`, which can fetch URLs.

**Dependencies**
- Add dependencies to `requirements.in` or `requirements-dev.in` only, then regenerate the hash-pinned lock files:
  ```powershell
  uv pip compile requirements.in --universal --python-version 3.11 --generate-hashes -o requirements.txt
  uv pip compile requirements-dev.in --universal --python-version 3.11 --generate-hashes -o requirements-dev.txt
  pip-audit -r requirements.txt --require-hashes --disable-pip
  ```
- Prefer well-maintained packages. Explain in the PR why a new dependency is needed.

**CI/CD**
- Pin third-party GitHub Actions to a full commit SHA with a version comment.
- Give each workflow and job the minimum `permissions`, and use `persist-credentials: false` on checkout.
- Pass untrusted values (branch or tag names, PR titles) through `env:`, never directly inside `run:` scripts.

**Tests**
- Add a regression test for every bug fix, and a security test (see `tests/test_security.py`) for every security fix.
