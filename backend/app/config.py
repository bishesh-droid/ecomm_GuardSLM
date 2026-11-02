import os

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-only-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "480"))
CANCEL_SHIPPED_POLICY = os.environ.get("CANCEL_SHIPPED_POLICY", "BLOCK").upper()  # BLOCK | ASK
RETURN_WINDOW_DAYS = int(os.environ.get("RETURN_WINDOW_DAYS", "14"))
REFUND_WINDOW_DAYS = int(os.environ.get("REFUND_WINDOW_DAYS", "30"))
ENABLE_DEV_RESET = os.environ.get("ENABLE_DEV_RESET", "false").lower() == "true"
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")]
