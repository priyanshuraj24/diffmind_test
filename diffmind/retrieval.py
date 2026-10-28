import hashlib
import json
import sqlite3
import uuid
from collections import defaultdict

import numpy as np
from fastembed import SparseTextEmbedding, TextEmbedding
from qdrant_client import QdrantClient
from qdrant_client import models as qm
from tokenizers import Tokenizer

from .code import IDENTIFIER, chunk_file, lexical


def fuse(rankings, limit=12):
    scores, items = defaultdict(float), {}
    for ranking in rankings:
        for rank, item in enumerate(ranking):
            key = (item["path"], item["start"], item["content_id"])
            scores[key] += 1 / (60 + rank + 1)
            items[key] = item
    return [items[k] for k in sorted(scores, key=lambda k: (-scores[k], k))[:limit]]


class Index:
    def __init__(self, settings, store):
        self.s, self.store = settings, store
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.dense = TextEmbedding(settings.embedding_model, cache_dir=str(settings.data_dir / "models"), threads=2)
        self.sparse = SparseTextEmbedding("Qdrant/bm25", cache_dir=str(settings.data_dir / "models"))
        self.tokenizer = Tokenizer.from_str(self.dense.model.tokenizer.to_str())
        self.tokenizer.no_truncation()
        self.tokenizer.no_padding()
        self.client = QdrantClient(url=settings.qdrant_url,
                                   api_key=settings.qdrant_api_key.get_secret_value() or None, timeout=60)
        self.cache = sqlite3.connect(settings.data_dir / "embeddings.sqlite", check_same_thread=False)
        self.cache.execute("CREATE TABLE IF NOT EXISTS embeddings(key TEXT PRIMARY KEY,dense BLOB,sparse TEXT)")
        self.cache.execute("PRAGMA journal_mode=WAL")
        if not self.client.collection_exists(settings.collection):
            self.client.create_collection(settings.collection,
                vectors_config={"dense": qm.VectorParams(size=self.dense.embedding_size, distance=qm.Distance.COSINE, on_disk=True)},
                sparse_vectors_config={"bm25": qm.SparseVectorParams(modifier=qm.Modifier.IDF,
                                                                       index=qm.SparseIndexParams(on_disk=True))},
                on_disk_payload=True)
            for key in ("repo", "head", "path"):
                self.client.create_payload_index(settings.collection, key, field_schema=qm.PayloadSchemaType.KEYWORD)

    def tokens(self, text):
        return len(self.tokenizer.encode(text).ids)

    @staticmethod
    def scope(repo, head):
        return qm.Filter(must=[qm.FieldCondition(key="repo", match=qm.MatchValue(value=repo)),
                               qm.FieldCondition(key="head", match=qm.MatchValue(value=head))])

    def build(self, repo, head, files, skipped):
        chunks, dropped = [], []
        for path, content in files.items():
            rows = chunk_file(path, content, self.tokens)
            if not rows and content.strip():
                dropped.append({"path": path, "reason": "no_safe_chunks"})
            elif rows:
                covered = {line for row in rows for line in range(row.start, row.end + 1)}
                if any(text.strip() and number not in covered
                       for number, text in enumerate(content.splitlines(), 1)):
                    dropped.append({"path": path, "reason": "oversized_lines_not_indexed"})
            if len(chunks) + len(rows) > self.s.max_chunks:
                dropped.append({"path": path, "reason": "chunk_budget"})
                continue
            chunks.extend(rows)
        manifest = hashlib.sha256(json.dumps([
            self.s.embedding_model, [(c.path, c.start, c.end, c.content_id) for c in chunks]
        ], separators=(",", ":")).encode()).hexdigest()
        generation = self.store.generation(repo, head)
        if generation:
            actual = self.client.count(self.s.collection, count_filter=self.scope(repo, head), exact=True).count
            if actual == generation["count"] == len(chunks) and generation["coverage"].get("manifest") == manifest:
                return chunks, generation["coverage"] | {"cache_hit": True}
        # Policies/chunking can change without a new commit. Remove stale points before rebuilding.
        self.client.delete(self.s.collection,
            points_selector=qm.FilterSelector(filter=self.scope(repo, head)), wait=True)
        created, reused = 0, 0
        # An unpublished generation can be safely retried. Its stable point IDs make upserts idempotent.
        for offset in range(0, len(chunks), 24):
            batch, vectors = chunks[offset:offset+24], {}
            missing = []
            for chunk in batch:
                key = hashlib.sha256(f"v1:{self.s.embedding_model}:{chunk.content_id}".encode()).hexdigest()
                row = self.cache.execute("SELECT dense,sparse FROM embeddings WHERE key=?", (key,)).fetchone()
                if row:
                    vectors[chunk.content_id] = (np.frombuffer(row[0], dtype=np.float32).tolist(), json.loads(row[1]))
                    reused += 1
                else:
                    missing.append((key, chunk))
            if missing:
                dense = list(self.dense.embed([c.search_text for _, c in missing], batch_size=24))
                sparse = list(self.sparse.embed([lexical(c.search_text) for _, c in missing]))
                for (key, chunk), d, sp in zip(missing, dense, sparse):
                    sparse_json = {"indices": sp.indices.tolist(), "values": sp.values.tolist()}
                    vectors[chunk.content_id] = (d.tolist(), sparse_json)
                    self.cache.execute("INSERT OR REPLACE INTO embeddings VALUES(?,?,?)",
                                       (key, np.asarray(d, dtype=np.float32).tobytes(), json.dumps(sparse_json)))
                    created += 1
                self.cache.commit()
            points = []
            for chunk in batch:
                d, sp = vectors[chunk.content_id]
                identifier = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{repo}:{head}:{chunk.path}:{chunk.start}:{chunk.content_id}"))
                points.append(qm.PointStruct(id=identifier, vector={"dense": d, "bm25": qm.SparseVector(**sp)},
                                             payload=chunk.payload() | {"repo": repo, "head": head}))
            self.client.upsert(self.s.collection, points=points, wait=True)
        count = self.client.count(self.s.collection, count_filter=self.scope(repo, head), exact=True).count
        if count != len(chunks):
            raise RuntimeError("Index count did not match source generation")
        coverage = {"files": len(files), "chunks": count, "skipped": skipped + dropped, "manifest": manifest,
                    "embedded": created, "reused_embeddings": reused, "cache_hit": False}
        self.store.generation(repo, head, count, coverage)
        return chunks, coverage

    def search(self, repo, head, query, chunks, changed_paths, locations=None):
        # Separate queries make channel failures and candidate counts observable.
        query = self.tokenizer.decode(self.tokenizer.encode(query).ids[:450], skip_special_tokens=True)
        d = next(iter(self.dense.query_embed(query))).tolist()
        sp = next(iter(self.sparse.query_embed(lexical(query))))
        dense = self.client.query_points(self.s.collection, query=d, using="dense",
            query_filter=self.scope(repo, head), limit=30, with_payload=True).points
        sparse = self.client.query_points(self.s.collection,
            query=qm.SparseVector(indices=sp.indices.tolist(), values=sp.values.tolist()), using="bm25",
            query_filter=self.scope(repo, head), limit=30, with_payload=True).points
        terms = set(IDENTIFIER.findall(query))
        exact = sorted(chunks, key=lambda c: (c.symbol in terms, len(terms & set(IDENTIFIER.findall(c.text)))), reverse=True)
        exact = [c.payload() for c in exact if c.symbol in terms or len(terms & set(IDENTIFIER.findall(c.text))) >= 3][:30]
        hits = fuse([exact, [p.payload for p in sparse], [p.payload for p in dense]])
        # Always retain changed code; dependency evidence should survive unrelated high-scoring chunks.
        changed = [c.payload() for c in chunks if c.path in changed_paths and
                   (locations is None or any(c.start <= line <= c.end
                    for line in locations.get(c.path, {}).get("RIGHT", [])))]
        selected, seen, chars = [], set(), 0
        for item in changed[:8] + hits + changed[8:]:
            key = (item["path"], item["start"], item["content_id"])
            if key in seen or chars + len(item["text"]) > 40000:
                continue
            seen.add(key)
            item = item | {"evidence_id": f"E{len(selected)+1}", "head": head}
            selected.append(item)
            chars += len(item["text"])
        trace = {"repo": repo, "head": head, "status": "ok", "exact_candidates": len(exact),
                 "lexical_candidates": len(sparse), "semantic_candidates": len(dense),
                 "selected": [{k: c[k] for k in ("evidence_id", "path", "start", "end", "head")} for c in selected]}
        return selected, trace

    def prune(self, repo, keep_heads):
        with self.store.connection() as c:
            rows = c.execute("SELECT head FROM dm_generations WHERE repo=%s ORDER BY created_at DESC", (repo,)).fetchall()
            protected = set(keep_heads) | {r["head"] for r in rows[:3]}
            for row in rows:
                if row["head"] in protected:
                    continue
                self.client.delete(self.s.collection, points_selector=qm.FilterSelector(filter=self.scope(repo, row["head"])), wait=True)
                c.execute("DELETE FROM dm_generations WHERE repo=%s AND head=%s", (repo, row["head"]))
