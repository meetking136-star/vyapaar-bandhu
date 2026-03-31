"""
VyapaarBandhu — API v1 Router
Aggregates all sub-routers under /api/v1.
"""

from fastapi import APIRouter

from app.api.v1.ca_auth import router as ca_auth_router
from app.api.v1.clients import router as clients_router
from app.api.v1.webhooks import router as webhooks_router
from app.api.v1.ca_dashboard import router as ca_dashboard_router
from app.api.v1.invoices import router as invoices_router
from app.api.v1.exports import router as exports_router
from app.api.v1.whatsapp import router as whatsapp_router

api_v1_router = APIRouter()

# ── Auth ───────────────────────────────────────────────────────────────
api_v1_router.include_router(ca_auth_router, prefix="/auth", tags=["Auth"])

# ── Clients ────────────────────────────────────────────────────────────
api_v1_router.include_router(clients_router, prefix="/clients", tags=["Clients"])

# ── WhatsApp Webhooks ──────────────────────────────────────────────────
api_v1_router.include_router(webhooks_router, prefix="/webhooks", tags=["WhatsApp"])

# ── Dashboard ──────────────────────────────────────────────────────────
api_v1_router.include_router(ca_dashboard_router, prefix="/dashboard", tags=["Dashboard"])

# ── Invoices ───────────────────────────────────────────────────────────
api_v1_router.include_router(invoices_router, prefix="/invoices", tags=["Invoices"])

# ── Exports ────────────────────────────────────────────────────────────
api_v1_router.include_router(exports_router, prefix="/exports", tags=["Exports"])

# ── WhatsApp (Phase 4) ────────────────────────────────────────────────
api_v1_router.include_router(whatsapp_router, prefix="/whatsapp", tags=["WhatsApp"])


@api_v1_router.get("/", tags=["Health"])
async def api_root():
    return {"service": "VyapaarBandhu", "version": "v1", "status": "operational"}
