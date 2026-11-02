# Changelog

## 1.0.0 - initial release
- Multi-vendor marketplace: customer, seller, warehouse, support and admin interfaces.
- FastAPI + SQLAlchemy + PostgreSQL backend with centralized authorization, audit log and transactional checkout/payment/refund/return flows.
- Simulated payments (card, UPI, COD), deterministic seed data, Docker Compose deployment.
- 65 backend tests and 42 Playwright tests (including the 16 research authorization scenarios).
