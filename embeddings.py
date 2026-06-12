"""
embeddings.py — build the RAG index for the "Ask AI" assistant.

Reads every business table (items, stock, parties, sales, purchases, payments,
expenses, returns), turns the rows + exact aggregates into text documents,
creates feature-hashing TF-IDF embeddings and saves them to data/rag_index.pkl.

Run whenever data changes:

    python embeddings.py
"""
from app.database import SessionLocal
from app.rag.engine import INDEX_PATH, build_index


def main():
    db = SessionLocal()
    try:
        index = build_index(db)
    finally:
        db.close()
    docs = index["docs"]
    kinds = {}
    for d in docs:
        kinds[d["kind"]] = kinds.get(d["kind"], 0) + 1
    print(f"[OK] Built RAG index: {len(docs)} documents, dim={index['dim']}")
    print(f"     saved to: {INDEX_PATH}")
    print("     breakdown: " + ", ".join(f"{k}={v}" for k, v in sorted(kinds.items())))


if __name__ == "__main__":
    main()
