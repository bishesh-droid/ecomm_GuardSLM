# Contributing

## Development setup
```bash
docker compose up --build            # full stack
# or run pieces locally:
cd backend  && pip install -r requirements.txt && uvicorn app.main:app --reload      # uses SQLite unless DATABASE_URL is set
cd frontend && npm install && npm run dev                                             # needs VITE_API_URL if backend is not on :8000
```

## Ground rules
1. **Authorization lives in `backend/app/permissions.py`.** Routes must call a guard; never trust ids or roles from the client.
   New protected endpoints need a backend test showing the ALLOW case *and* the BLOCK case.
2. **State changes that must happen once** (payment, refund, return, stock) use `services.transition()` or conditional
   `UPDATE ... WHERE` - not read-then-write.
3. Every interactive UI control gets a stable `data-testid` and every form field a `<label>`.
4. Keep demo data fictional and external-service free.

## Before opening a PR
```bash
cd backend && python -m pytest app/tests -q
cd frontend && npm run build
docker compose up --build -d && cd tests/playwright && npx playwright test
```
Do not report tests as passing unless you ran them.

## Commit style
Short imperative subject (`Add refund completion guard`), body explaining *why* when non-obvious.
