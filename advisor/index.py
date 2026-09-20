from pathlib import Path
import chromadb
import ollama

BASE = Path(__file__).parent
client = chromadb.PersistentClient(path=str(BASE.parent / "chroma_courses"))
EMBED_MODEL = "nomic-embed-text"


def course_level(code):
    return (ord(code[3]) - ord("A") + 1) * 100  # A=100, B=200, C=300, D=400


def course_doc(c):
    parts = [f'{c["code"]} — {c["title"]} ({c["section"]}). {c["description"]}']
    if c.get("prereq_text"):
        parts.append(f'Prerequisites: {c["prereq_text"]}.')
    if c.get("exclusions"):
        parts.append(f'Exclusions: {", ".join(c["exclusions"])}.')
    if c.get("breadth"):
        parts.append(f'Breadth: {c["breadth"]}.')
    return " ".join(parts)


def embed(texts, batch=32, progress=False):
    out = []
    for i in range(0, len(texts), batch):
        out += ollama.embed(model=EMBED_MODEL, input=texts[i:i + batch])["embeddings"]
        if progress:
            print(f"  embedded {min(i + batch, len(texts))}/{len(texts)}", end="\r")
    if progress:
        print()
    return out


def chunk_policy(path, size=800, overlap=150):
    text = open(path, encoding="utf-8").read()
    return [text[i:i + size] for i in range(0, len(text), size - overlap)]


def add_batched(col, ids, docs, embs, metas, step=500):
    for i in range(0, len(ids), step):
        col.add(ids=ids[i:i + step], documents=docs[i:i + step],
                embeddings=embs[i:i + step], metadatas=metas[i:i + step])


def build_index(courses, policy_chunks):
    for name in ("courses", "policies"):
        try:
            client.delete_collection(name)
        except Exception:
            pass

    print("Embedding courses...")
    docs = [course_doc(c) for c in courses]
    col = client.create_collection("courses", metadata={"hnsw:space": "cosine"})
    add_batched(
        col,
        [c["code"] for c in courses],
        docs,
        embed(docs, progress=True),
        [{"code": c["code"], "dept": c["code"][:3], "level": course_level(c["code"]),
          "section": c["section"]} for c in courses],
    )

    if policy_chunks:
        print("Embedding programs and policies...")
        texts = [p["text"] for p in policy_chunks]
        pol = client.create_collection("policies", metadata={"hnsw:space": "cosine"})
        add_batched(
            pol,
            [p["id"] for p in policy_chunks],
            texts,
            embed(texts, progress=True),
            [{"source": p["source"], "url": p.get("url", "")} for p in policy_chunks],
        )


def search(query, kind, k=5, where=None):
    col = client.get_collection(kind)
    res = col.query(query_embeddings=embed([query]), n_results=k, where=where)
    return [
        {"text": d, "meta": m, "dist": dist}
        for d, m, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0])
    ]