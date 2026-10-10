# Security Policy

## Supported versions

Only the latest release receives security fixes. Please update before reporting.

| Version | Supported | Notes |
|---|---|---|
| 1.1.x (latest) | ✅ | |
| < 1.1 | ❌ | Stored the optional LLM API key in plain text; please upgrade. The key is migrated to the OS credential store automatically. |

## Reporting a vulnerability

**Please do not report security issues in public GitHub issues, discussions or pull requests.**

Report privately through GitHub's private vulnerability reporting:

**➜ [Report a vulnerability](https://github.com/jordanbrais1-hub/mdConverter/security/advisories/new)**
(repository → *Security* tab → *Report a vulnerability*)

Please include:

- the affected version, operating system and how you installed it (installer, portable zip, source)
- a description of the issue and its impact
- steps to reproduce or a proof of concept (a sample file is ideal)
- any suggested fix

### What to expect

| Step | Target time |
|---|---|
| Acknowledgement of your report | within 5 business days |
| Initial assessment and severity rating (CVSS) | within 10 business days |
| Fix released for confirmed critical/high issues | within 30 days |
| Fix released for confirmed medium/low issues | next scheduled release |

We will keep you updated, credit you in the advisory and release notes (unless you prefer to stay anonymous), and coordinate the disclosure date with you. Please give us a reasonable time to release a fix before any public disclosure.

### Safe harbor

We will not pursue or support legal action against good-faith research that follows this policy, avoids privacy violations and data destruction, and does not degrade the service for others.

## Scope

**In scope:** the mdConverter application source code in this repository, the Windows installer and portable builds published on the [Releases](https://github.com/jordanbrais1-hub/mdConverter/releases) page, and the build and release workflows in `.github/workflows`.

**Out of scope:**
- Vulnerabilities in third-party dependencies (e.g. MarkItDown, pdfminer, onnxruntime) that are not exploitable through mdConverter. Report these upstream. We still welcome a heads-up.
- Windows SmartScreen warnings caused by the installer not being code-signed.
- Denial of service from deliberately huge or malformed local files that the user chooses to open.
- Issues that need an already-compromised machine or administrator access.

## Security model

- **Offline by default.** Files are converted locally. Network access happens only when the user enables an optional AI model or online audio transcription in Settings. Inputs are always opened as local files, never fetched as URLs.
- **Secrets.** The optional LLM API key is stored in the operating system's credential vault (Windows Credential Manager, macOS Keychain or Linux Secret Service), never in configuration files or logs. Remote API endpoints must use HTTPS.
- **File system.** Output is confined to the chosen output folder (path traversal is rejected). The app only asks the OS to open folders and `.md` files, never executables.
- **Supply chain.** Dependencies are pinned with SHA-256 hashes, audited with `pip-audit` on every change and weekly, and updated by Dependabot. CI actions are pinned to commit SHAs, and release binaries are built from a clean environment. Each release includes `SHA256SUMS.txt`.
- **Development.** Pre-commit hooks block secrets, private keys and `.env` files. Bandit, CodeQL and gitleaks run in CI.

### Verifying a download

Each release includes `SHA256SUMS.txt`. In PowerShell:

```powershell
Get-FileHash .\mdConverter-Setup-1.1.0.exe -Algorithm SHA256
```

Compare the result with the matching line in `SHA256SUMS.txt`.
