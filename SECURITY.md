# Security policy

This project is a **research sandbox** for evaluating authorization decisions. It ships with publicly documented demo
credentials (`GuardSLM2026!`), a dev-only database reset endpoint and a default JWT secret. **Do not deploy it to the
public internet as-is.**

Before any shared deployment: set a strong `JWT_SECRET`, set `ENABLE_DEV_RESET=false`, change or remove the demo accounts,
restrict `CORS_ORIGINS`, and do not publish the Postgres port.

## Payments
Payments are simulated. The API rejects card-number-shaped input (HTTP 422) and stores only a token's last four characters.
Never add real payment data to this system.

## Reporting a vulnerability
Open a private security advisory on the repository (or contact the maintainer directly) with reproduction steps.
Authorization bypasses (accessing another user's data, privilege escalation) are the most relevant class for this project.
