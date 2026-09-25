# Security Policy

## Supported Versions

Security updates are provided for the latest version on the `main` branch.

| Version | Supported          |
| ------- | ------------------ |
| `main`  | :white_check_mark: |
| < 1.0   | :x:                |

---

## Reporting a Vulnerability

We take the security of KoridorTJ seriously. If you discover a security vulnerability:

1. **Do not create a public issue or discussion.**
2. Please privately report the vulnerability to the project maintainers via GitHub Security Advisories (under the "Security" tab of this repository) or email the maintainer directly.
3. Include as much detail as possible:
   - Type of issue (e.g. secret exposure, privilege escalation, injection flaw)
   - Step-by-step reproduction instructions or proof-of-concept
   - Potential impact and mitigation recommendations

You should receive an acknowledgement within 48 hours.

---

## Secrets & Credentials Policy

- Never commit real passwords, Fernet keys, JWT secrets, or tokens to the repository.
- Always use environment variables managed through `.env` (ignored by Git) or secrets managers in production / Coolify.
