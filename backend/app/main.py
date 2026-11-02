from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .database import Base, SessionLocal, engine
from .models import ActivityLog
from .permissions import AuthzDenied
from .routes import (
    admin, audit_logs, auth, cart, orders, payments, products, refunds, returns, reviews, seller, support, warehouse,
)
from .seed import STATIC_DIR, seed, write_images


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
    write_images()
    yield


app = FastAPI(title="GuardSLM Marketplace API", version="1.0.0", lifespan=lifespan,
              description="Multi-vendor e-commerce backend for evaluating SLM authorization decisions. Demo password: GuardSLM2026!")
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static/products", StaticFiles(directory=STATIC_DIR), name="product-images")


@app.exception_handler(AuthzDenied)
async def authz_denied(request: Request, exc: AuthzDenied):
    """Every authorization decision that is not ALLOW lands in the audit log."""
    user = getattr(request.state, "user", None)
    try:
        with SessionLocal() as db:
            db.add(ActivityLog(actor_id=user.id if user else None, actor_role=user.role if user else None,
                               action=f"{exc.detail['decision'].lower()}:{request.method} {request.url.path}"[:80],
                               entity_type="request", decision=exc.detail["decision"], detail=exc.detail["message"]))
            db.commit()
    except Exception:  # never let audit logging mask the 403
        pass
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


for r in (auth.router, products.categories_router, products.router, cart.router, cart.wishlist_router, orders.router,
          payments.router, refunds.router, returns.router, reviews.router, seller.router, warehouse.router,
          support.router, admin.router, audit_logs.router):
    app.include_router(r)
