"""
Ask-AI assistant router (/api/v1/assistant)
───────────────────────────────────────────
  POST /assistant/ask      { question }  → grounded answer + sources
  POST /assistant/reindex                → rebuild embeddings from current data
  GET  /assistant/status                 → is the index built? how many docs?

The AI index is built and cached per-pharmacy, so each tenant's assistant only
ever sees its own data.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, get_current_user, get_tenant_db as get_db
from app.rag import engine

router = APIRouter(prefix="/assistant", tags=["AI Assistant"])


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str
    sources: list = []
    context_used: int = 0
    indexed: bool = True


@router.get("/status")
def assistant_status(user: CurrentUser = Depends(get_current_user)):
    return engine.status(pharmacy_id=user.pharmacy_id)


@router.post("/ask", response_model=AskResponse)
def assistant_ask(
    payload: AskRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    pid = user.pharmacy_id
    q = (payload.question or "").strip()
    if not q:
        return AskResponse(
            answer="Please type a question about your sales, purchases, stock, payments or expenses.",
            indexed=engine.status(pharmacy_id=pid)["indexed"],
        )
    # Build the index on first use if it doesn't exist yet.
    if not engine.status(pharmacy_id=pid)["indexed"]:
        engine.build_index(db, pharmacy_id=pid)
    return AskResponse(**engine.answer(q, pharmacy_id=pid))


@router.post("/reindex")
def assistant_reindex(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    index = engine.build_index(db, pharmacy_id=user.pharmacy_id)
    return {"indexed": True, "documents": len(index["docs"]), "built_at": index.get("built_at")}
