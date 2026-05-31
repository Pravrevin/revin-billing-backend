import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.routers import item_master, party_master, payment_mode_master, stock_master, purchase, sales
from app.routers import purchase_payment, party_credit_config
from app.routers import category_master, packaging_master, brand_master, unit_master
from app.routers import reports, accounts, expense, sales_return, held_bill, sales_summary

app = FastAPI(
    title="Billing Software API",
    description="Backend API for Billing Software — Item Master, Stock Master, Party Master and beyond.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(category_master.router,     prefix="/api/v1")
app.include_router(packaging_master.router,    prefix="/api/v1")
app.include_router(brand_master.router,        prefix="/api/v1")
app.include_router(unit_master.router,         prefix="/api/v1")
app.include_router(item_master.router,         prefix="/api/v1")
app.include_router(party_master.router,        prefix="/api/v1")
app.include_router(payment_mode_master.router, prefix="/api/v1")
app.include_router(stock_master.router,        prefix="/api/v1")
# Payments router first: its static paths (/purchases/outstanding, /sales/outstanding,
# /distributors/{id}/ledger) must be registered before the catch-all /purchases/{id}
# and /sales/{id} routes below, otherwise "outstanding" is parsed as an id.
app.include_router(purchase_payment.router,    prefix="/api/v1")
app.include_router(purchase.router,             prefix="/api/v1")
app.include_router(sales.router,               prefix="/api/v1")
app.include_router(sales_return.router,        prefix="/api/v1")
app.include_router(held_bill.router,           prefix="/api/v1")
app.include_router(sales_summary.router,       prefix="/api/v1")
app.include_router(party_credit_config.router, prefix="/api/v1")
app.include_router(reports.router,             prefix="/api/v1")
app.include_router(accounts.router,            prefix="/api/v1")
app.include_router(expense.router,             prefix="/api/v1")

# Serve uploaded payment receipts read-only at /media/payment-receipts/<file>
_RECEIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "payment_receipts")
os.makedirs(_RECEIPTS_DIR, exist_ok=True)
app.mount("/media/payment-receipts", StaticFiles(directory=_RECEIPTS_DIR), name="payment-receipts")


@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "message": "Billing Software API is running."}


@app.get("/health", tags=["Health"])
def health():
    return {"status": "healthy"}
