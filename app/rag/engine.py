"""
RAG engine for the "Ask AI" assistant.

Pipeline
────────
1. build_documents(db)  — turn every table (items, stock, parties, sales,
   purchases, payments, expenses, returns) PLUS precomputed exact aggregates
   (daily totals, valuations, outstanding, a business snapshot) into short
   descriptive text documents that always carry the *exact* numbers.
2. embeddings           — feature-hashing TF-IDF vectors (pure numpy, no heavy
   ML deps, deterministic). Stored to data/rag_index.pkl.
3. answer(question)     — embed the question, retrieve the most relevant docs
   (cosine), and ask Groq's llama-3.1-8b-instant to answer ONLY from that
   context, so figures come straight from the database.

Rebuild the index any time with:  python embeddings.py
"""
import math
import os
import pickle
import re
from datetime import date, datetime, timedelta
from decimal import Decimal

import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.expense import ExpenseMaster
from app.models.item_master import ItemMaster
from app.models.party_master import PartyMaster
from app.models.payment_mode_master import PaymentModeMaster
from app.models.purchase_master import PurchaseItem, PurchaseMaster
from app.models.purchase_payment import PaymentMaster
from app.models.sales_master import SalesItem, SalesMaster
from app.models.sales_return import SalesReturnMaster
from app.models.stock_master import StockMaster

# ── config ────────────────────────────────────────────────────────────────────
DIM = 1024
TOP_K = 10
_INDEX_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))


def _index_path(pharmacy_id) -> str:
    """Per-pharmacy index file so tenants never share AI context."""
    pid = pharmacy_id if pharmacy_id is not None else "none"
    return os.path.join(_INDEX_DIR, f"rag_index_{pid}.pkl")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")

NEAR_EXPIRY_DAYS = 30
_ZERO = Decimal("0")


# ── small helpers ───────────────────────────────────────────────────────────

def _f(v) -> float:
    return round(float(v), 2) if v is not None else 0.0


def _rs(v) -> str:
    """Format money like ₹1,234.50."""
    return f"₹{_f(v):,.2f}"


def _d(v) -> str:
    if not v:
        return "unknown date"
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str):
    toks = _TOKEN_RE.findall(text.lower())
    # add bigrams for a little phrase sensitivity
    bigrams = [f"{a}_{b}" for a, b in zip(toks, toks[1:])]
    return toks + bigrams


def _hash(tok: str) -> int:
    # md5 → stable across processes (Python's str hash is salted)
    import hashlib
    return int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16) % DIM


# ── document builder ──────────────────────────────────────────────────────────

def build_documents(db: Session):
    """Return a list of {id, kind, text} covering all business data + aggregates."""
    docs = []
    today = date.today()

    def add(kind, text):
        docs.append({"id": f"{kind}-{len(docs)}", "kind": kind, "text": text.strip()})

    item_name = dict(db.query(ItemMaster.id, ItemMaster.item_name).all())
    party_name = dict(db.query(PartyMaster.id, PartyMaster.party_name).all())

    # —— Items + on-hand stock ——
    stock_by_item = dict(
        db.query(StockMaster.item_id, func.coalesce(func.sum(StockMaster.quantity), 0))
        .group_by(StockMaster.item_id).all()
    )
    for it in db.query(ItemMaster).all():
        qty = _f(stock_by_item.get(it.id, 0))
        add("item",
            f"Item '{it.item_name}' (code {it.item_code}). "
            f"Generic: {it.generic_name or '-'}. Brand: {it.brand_name or '-'}. "
            f"Category: {it.category_name or '-'}. GST {_f(it.gst_percent)}%. "
            f"HSN {it.hsn_code or '-'}. Current stock on hand: {qty} units. "
            f"Reorder level {it.reorder_level or 0}.")

    # —— Stock batches ——
    for s in db.query(StockMaster).all():
        add("stock",
            f"Stock batch of '{item_name.get(s.item_id, s.item_id)}': batch {s.batch_no}, "
            f"quantity {_f(s.quantity)} units, MRP {_rs(s.mrp)}, purchase rate {_rs(s.purchase_rate)}, "
            f"sale rate {_rs(s.sale_rate)}, expiry {_d(s.expiry_date)}.")

    # —— Payments maps for outstanding ——
    purchase_paid = dict(
        db.query(PaymentMaster.reference_id, func.coalesce(func.sum(PaymentMaster.amount), 0))
        .filter(PaymentMaster.reference_type == "purchase", PaymentMaster.txn_type == "PAYMENT")
        .group_by(PaymentMaster.reference_id).all()
    )
    sale_recv = dict(
        db.query(PaymentMaster.reference_id, func.coalesce(func.sum(PaymentMaster.amount), 0))
        .filter(PaymentMaster.reference_type == "sale", PaymentMaster.txn_type == "RECEIPT")
        .group_by(PaymentMaster.reference_id).all()
    )

    # —— Sales ——
    sales = db.query(SalesMaster).all()
    sales_total = sum((s.net_amount or _ZERO) for s in sales)
    for s in sales:
        items = db.query(SalesItem).filter(SalesItem.sales_id == s.id).all()
        lines = "; ".join(
            f"{_f(i.quantity)} x {item_name.get(i.item_id, i.item_id)} @ {_rs(i.sale_rate)} (batch {i.batch_no or '-'})"
            for i in items
        ) or "no line items"
        add("sale",
            f"Sales invoice {s.invoice_no or '#'+str(s.id)} dated {_d(s.invoice_date)} "
            f"to customer {party_name.get(s.customer_id, 'Walk-in')}: net {_rs(s.net_amount)}, "
            f"discount {_rs(s.discount)}, tax {_rs(s.tax_amount)}, payment status {s.payment_status or 'Unpaid'}. "
            f"Items: {lines}.")

    # daily sales totals
    for d_, net, cnt in (
        db.query(SalesMaster.invoice_date,
                 func.coalesce(func.sum(SalesMaster.net_amount), 0),
                 func.count(SalesMaster.id))
        .group_by(SalesMaster.invoice_date).all()
    ):
        add("sales_daily", f"On {_d(d_)}, total sales were {_rs(net)} across {int(cnt or 0)} bills.")

    # today / overall
    today_sales = sum((s.net_amount or _ZERO) for s in sales if s.invoice_date == today)
    add("sales_overall",
        f"All-time total sales are {_rs(sales_total)} across {len(sales)} sales bills. "
        f"Today is {today.isoformat()} and today's sales total {_rs(today_sales)}.")

    # top selling items
    top_sell = (
        db.query(ItemMaster.item_name,
                 func.coalesce(func.sum(SalesItem.quantity), 0),
                 func.coalesce(func.sum(SalesItem.total), 0))
        .join(SalesMaster, SalesItem.sales_id == SalesMaster.id)
        .join(ItemMaster, SalesItem.item_id == ItemMaster.id)
        .group_by(ItemMaster.item_name)
        .order_by(func.sum(SalesItem.total).desc()).limit(10).all()
    )
    if top_sell:
        add("top_sales", "Best-selling items by revenue: " + "; ".join(
            f"{i+1}. {n} — {_rs(rev)} ({_f(q)} units)" for i, (n, q, rev) in enumerate(top_sell)))

    # —— Purchases ——
    purchases = db.query(PurchaseMaster).all()
    purchase_total = sum((p.net_amount or _ZERO) for p in purchases)
    for p in purchases:
        paid = purchase_paid.get(p.id, _ZERO)
        out = max((p.net_amount or _ZERO) - paid, _ZERO)
        add("purchase",
            f"Purchase invoice {p.invoice_no or '#'+str(p.id)} dated {_d(p.invoice_date)} "
            f"from supplier {party_name.get(p.supplier_id, '-')}: net {_rs(p.net_amount)}, "
            f"paid {_rs(paid)}, outstanding {_rs(out)}.")
    add("purchase_overall",
        f"All-time total purchases are {_rs(purchase_total)} across {len(purchases)} purchase bills.")

    # —— Suppliers & customers with outstanding ——
    for sup in db.query(PartyMaster).filter(PartyMaster.party_type == "Distributor").all():
        sps = [p for p in purchases if p.supplier_id == sup.id]
        billed = sum((p.net_amount or _ZERO) for p in sps)
        paid = sum(purchase_paid.get(p.id, _ZERO) for p in sps)
        add("supplier",
            f"Supplier '{sup.party_name}' (mobile {sup.mobile or '-'}, GSTIN {sup.gstin or '-'}): "
            f"{len(sps)} bills, total billed {_rs(billed)}, paid {_rs(paid)}, "
            f"outstanding payable {_rs(max(billed - paid, _ZERO))}.")
    for cus in db.query(PartyMaster).filter(PartyMaster.party_type == "Customer").all():
        css = [s for s in sales if s.customer_id == cus.id]
        billed = sum((s.net_amount or _ZERO) for s in css)
        recv = sum(sale_recv.get(s.id, _ZERO) for s in css)
        add("customer",
            f"Customer '{cus.party_name}' (mobile {cus.mobile or '-'}): {len(css)} bills, "
            f"total billed {_rs(billed)}, received {_rs(recv)}, "
            f"outstanding receivable {_rs(max(billed - recv, _ZERO))}.")

    # —— Payments / collections ——
    mode_name = dict(db.query(PaymentModeMaster.id, PaymentModeMaster.mode_name).all())
    recv_total = sum((p.amount or _ZERO) for p in db.query(PaymentMaster).filter(PaymentMaster.txn_type == "RECEIPT").all())
    pay_total = sum((p.amount or _ZERO) for p in db.query(PaymentMaster).filter(PaymentMaster.txn_type == "PAYMENT").all())
    by_mode = db.query(
        PaymentMaster.payment_mode_id, func.coalesce(func.sum(PaymentMaster.amount), 0)
    ).group_by(PaymentMaster.payment_mode_id).all()
    mode_txt = "; ".join(f"{mode_name.get(mid, 'Unspecified')}: {_rs(amt)}" for mid, amt in by_mode) or "none"
    add("payments",
        f"Payments summary: total received from customers {_rs(recv_total)}; "
        f"total paid to suppliers {_rs(pay_total)}. Amounts by payment mode: {mode_txt}.")

    # —— Expenses ——
    exp_total = sum((e.amount or _ZERO) for e in db.query(ExpenseMaster).all())
    by_cat = db.query(
        func.coalesce(ExpenseMaster.category, "Misc"),
        func.coalesce(func.sum(ExpenseMaster.amount), 0)
    ).group_by(ExpenseMaster.category).all()
    cat_txt = "; ".join(f"{c}: {_rs(a)}" for c, a in by_cat) or "no expenses"
    add("expenses", f"Total business expenses are {_rs(exp_total)}. By category: {cat_txt}.")

    # —— Sales returns ——
    rets = db.query(SalesReturnMaster).all()
    ret_total = sum((r.total_amount or _ZERO) for r in rets)
    refund_total = sum((r.refund_amount or _ZERO) for r in rets)
    add("returns",
        f"Sales returns: {len(rets)} returns totalling {_rs(ret_total)} in goods, "
        f"with {_rs(refund_total)} refunded to customers.")

    # —— Inventory valuation / low stock / expiry ——
    val_cost, val_mrp, total_qty, batch_ct, item_ct = (
        db.query(
            func.coalesce(func.sum(StockMaster.quantity * func.coalesce(StockMaster.purchase_rate, 0)), 0),
            func.coalesce(func.sum(StockMaster.quantity * func.coalesce(StockMaster.mrp, 0)), 0),
            func.coalesce(func.sum(StockMaster.quantity), 0),
            func.count(StockMaster.id),
            func.count(func.distinct(StockMaster.item_id)),
        ).filter(StockMaster.quantity > 0).one()
    )
    near = db.query(func.count(StockMaster.id)).filter(
        StockMaster.quantity > 0, StockMaster.expiry_date >= today,
        StockMaster.expiry_date <= today + timedelta(days=NEAR_EXPIRY_DAYS)).scalar()
    expired = db.query(func.count(StockMaster.id)).filter(
        StockMaster.quantity > 0, StockMaster.expiry_date < today).scalar()
    add("inventory",
        f"Inventory valuation: stock at cost {_rs(val_cost)}, at MRP {_rs(val_mrp)}. "
        f"Total {_f(total_qty)} units across {int(batch_ct or 0)} batches / {int(item_ct or 0)} items. "
        f"{int(near or 0)} batches near expiry (within {NEAR_EXPIRY_DAYS} days), {int(expired or 0)} expired batches.")

    # low stock list
    low = []
    for it in db.query(ItemMaster).all():
        qty = _f(stock_by_item.get(it.id, 0))
        reorder = it.reorder_level or 0
        if (reorder and qty <= reorder) or qty <= 0:
            low.append(f"{it.item_name} ({qty} on hand, reorder {reorder})")
    if low:
        add("low_stock", "Low / out-of-stock items needing reorder: " + "; ".join(low[:40]) + ".")

    # —— Dedicated, unambiguous payable / receivable docs (single number each) ——
    payables = sum(max((p.net_amount or _ZERO) - purchase_paid.get(p.id, _ZERO), _ZERO) for p in purchases)
    receivables = sum(max((s.net_amount or _ZERO) - sale_recv.get(s.id, _ZERO), _ZERO) for s in sales)
    payable_bills = sum(1 for p in purchases if (p.net_amount or _ZERO) - purchase_paid.get(p.id, _ZERO) > 0)
    receivable_bills = sum(1 for s in sales if (s.net_amount or _ZERO) - sale_recv.get(s.id, _ZERO) > 0)
    add("receivables",
        f"Accounts receivable: the total money customers owe the business (outstanding/unpaid sales) "
        f"is {_rs(receivables)} across {receivable_bills} unpaid or partly-paid sales invoices.")
    add("payables",
        f"Accounts payable: the total money the business owes its suppliers (outstanding purchases) "
        f"is {_rs(payables)} across {payable_bills} unpaid or partly-paid purchase bills.")

    # —— Business snapshot (always-useful global doc) ——
    add("snapshot",
        f"BUSINESS SNAPSHOT as of {today.isoformat()}. "
        f"Total sales {_rs(sales_total)} ({len(sales)} bills); today's sales {_rs(today_sales)}. "
        f"Total purchases {_rs(purchase_total)} ({len(purchases)} bills). "
        f"Total expenses {_rs(exp_total)}. "
        f"Accounts payable (we owe suppliers) {_rs(payables)}; "
        f"accounts receivable (customers owe us) {_rs(receivables)}. "
        f"Inventory value at cost {_rs(val_cost)}, at MRP {_rs(val_mrp)}, {_f(total_qty)} units in stock. "
        f"Money received from customers {_rs(recv_total)}; money paid to suppliers {_rs(pay_total)}.")

    return docs


# ── embeddings (feature-hashing TF-IDF) ─────────────────────────────────────────

def _doc_term_freq(text: str):
    tf = {}
    for tok in _tokens(text):
        h = _hash(tok)
        tf[h] = tf.get(h, 0) + 1
    return tf


def build_index(db: Session, pharmacy_id=None) -> dict:
    docs = build_documents(db)
    n = len(docs)
    tfs = [_doc_term_freq(d["text"]) for d in docs]

    df = np.zeros(DIM, dtype=np.float64)
    for tf in tfs:
        for h in tf:
            df[h] += 1
    idf = np.log((n + 1) / (df + 1)) + 1.0

    matrix = np.zeros((n, DIM), dtype=np.float32)
    for i, tf in enumerate(tfs):
        row = np.zeros(DIM, dtype=np.float64)
        for h, c in tf.items():
            row[h] = c
        row *= idf
        norm = np.linalg.norm(row)
        if norm > 0:
            row /= norm
        matrix[i] = row.astype(np.float32)

    index = {
        "dim": DIM,
        "idf": idf.astype(np.float32),
        "matrix": matrix,
        "docs": docs,
        "built_at": datetime.utcnow().isoformat() + "Z",
    }
    path = _index_path(pharmacy_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(index, f)
    return index


# ── retrieval ─────────────────────────────────────────────────────────────────

# In-memory cache keyed by pharmacy_id -> {"index", "mtime"}
_CACHE: dict = {}


def load_index(pharmacy_id=None):
    path = _index_path(pharmacy_id)
    if not os.path.exists(path):
        return None
    mtime = os.path.getmtime(path)
    cached = _CACHE.get(pharmacy_id)
    if cached is None or cached["mtime"] != mtime:
        with open(path, "rb") as f:
            cached = {"index": pickle.load(f), "mtime": mtime}
        _CACHE[pharmacy_id] = cached
    return cached["index"]


def _embed_query(text: str, idf: np.ndarray) -> np.ndarray:
    row = np.zeros(DIM, dtype=np.float64)
    for h, c in _doc_term_freq(text).items():
        row[h] = c
    row *= idf
    norm = np.linalg.norm(row)
    if norm > 0:
        row /= norm
    return row.astype(np.float32)


def search(question: str, k: int = TOP_K, pharmacy_id=None):
    index = load_index(pharmacy_id)
    if index is None:
        return []
    q = _embed_query(question, index["idf"])
    scores = index["matrix"] @ q
    order = np.argsort(-scores)[: k]
    out = []
    for i in order:
        out.append({"score": float(scores[i]), **index["docs"][int(i)]})
    # Always include the snapshot doc for global context
    if not any(d["kind"] == "snapshot" for d in out):
        snap = next((d for d in index["docs"] if d["kind"] == "snapshot"), None)
        if snap:
            out.append({"score": 0.0, **snap})
    return out


# ── LLM answer ──────────────────────────────────────────────────────────────────

_SYSTEM = (
    "You are the data assistant for 'Revin Bill', a pharmacy / medical-store billing system. "
    "Answer the user's question ONLY using the CONTEXT below, which is generated directly from "
    "the live database, so every number is exact. Quote money with the rupee sign (e.g. ₹1,234.50). "
    "Be concise and specific. Match the EXACT metric the user asks for — do not confuse 'total sales' "
    "with 'accounts receivable', or 'total purchases' with 'accounts payable'; pick the context line "
    "whose label matches the question. If the answer is not present in the context, say you don't have "
    "that data yet rather than guessing. Do not invent figures."
)


def answer(question: str, k: int = TOP_K, pharmacy_id=None) -> dict:
    index = load_index(pharmacy_id)
    if index is None:
        return {
            "answer": "The AI index hasn't been built yet. Click “Rebuild” (or run `python embeddings.py`) to index your data, then ask again.",
            "sources": [], "context_used": 0, "indexed": False,
        }

    hits = search(question, k, pharmacy_id=pharmacy_id)
    context = "\n".join(f"- {h['text']}" for h in hits)[:7000]

    try:
        from langchain_groq import ChatGroq
        llm = ChatGroq(model=GROQ_MODEL, groq_api_key=GROQ_API_KEY, temperature=0)
        resp = llm.invoke([
            ("system", _SYSTEM),
            ("human", f"CONTEXT:\n{context}\n\nQUESTION: {question}"),
        ])
        text = resp.content if hasattr(resp, "content") else str(resp)
    except Exception as e:  # network / key / model errors
        text = f"Could not reach the AI model ({e}). Here is the most relevant data I found:\n\n{context}"

    return {
        "answer": text,
        "sources": [{"kind": h["kind"], "text": h["text"], "score": round(h["score"], 3)} for h in hits[:6]],
        "context_used": len(hits),
        "indexed": True,
    }


def status(pharmacy_id=None) -> dict:
    index = load_index(pharmacy_id)
    if index is None:
        return {"indexed": False, "documents": 0, "built_at": None}
    return {"indexed": True, "documents": len(index["docs"]), "built_at": index.get("built_at")}
