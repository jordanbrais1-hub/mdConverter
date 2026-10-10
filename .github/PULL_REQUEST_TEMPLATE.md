## Summary

<!-- What does this change do and why? Link related issues (e.g. Closes #12). -->

## How was it tested?

<!-- Tests added or updated, manual steps, screenshots for UI changes. -->

## Security checklist

<!-- See CONTRIBUTING.md → "Secure coding rules". Tick each box or explain why it doesn't apply. -->

- [ ] No secrets, tokens, `.env` files, private keys or real user documents are included
- [ ] Pre-commit hooks ran and passed (no `--no-verify`)
- [ ] Untrusted input (files, paths, settings, URLs) is validated; parser errors are handled
- [ ] No `shell=True`, `eval`/`exec`, unsafe deserialisation, or executables started by bare name
- [ ] No new network access, **or** it is opt-in, HTTPS-only and documented in the README *Privacy* section
- [ ] New or updated dependencies were added to `requirements*.in`, locked with hashes, and pass `pip-audit`
- [ ] Workflow changes pin actions to commit SHAs and use least-privilege `permissions`
- [ ] Security-relevant changes have tests in `tests/test_security.py`
