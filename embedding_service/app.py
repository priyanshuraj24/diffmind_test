"""Model inference only. Review orchestration belongs entirely to n8n."""
import hashlib
import hmac
import json
import os
import sqlite3
import threading
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastembed import SparseTextEmbedding, TextEmbedding
from pydantic import BaseModel, Field
from tokenizers import Tokenizer

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
root = Path(os.environ.get('EMBEDDING_DATA', '/data'))
root.mkdir(parents=True, exist_ok=True)
lock = threading.Lock()
models = {}


def auth(authorization: str = Header(default='')):
    if not hmac.compare_digest(authorization, 'Bearer ' + os.environ['EMBEDDING_TOKEN']):
        raise HTTPException(401, 'Unauthorized')


class Input(BaseModel):
    input: list[str] = Field(min_length=1, max_length=32)
    query: bool = False


@app.get('/health')
def health():
    return {'status': 'ok', 'role': 'embedding-inference-only'}


def encode(body, kind):
    if any(len(s) > 16000 for s in body.input):
        raise HTTPException(413, 'Input too large')
    with lock:
        if kind not in models:
            models[kind] = (TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir=str(root/'models'), threads=2)
                            if kind == 'dense' else SparseTextEmbedding('Qdrant/bm25', cache_dir=str(root/'models')))
        model = models[kind]
        if kind == 'dense':
            tokenizer = Tokenizer.from_str(model.model.tokenizer.to_str())
            tokenizer.no_truncation()
            tokenizer.no_padding()
            if any(len(tokenizer.encode(text).ids) > 500 for text in body.input):
                raise HTTPException(422, 'Chunk exceeds embedding token limit; reduce the n8n chunk window')
        with sqlite3.connect(root/'native-embeddings.sqlite') as db:
            db.execute('CREATE TABLE IF NOT EXISTS vectors(key TEXT PRIMARY KEY,value TEXT)')
            result, cached, missing = [None] * len(body.input), 0, []
            for index, text in enumerate(body.input):
                key = hashlib.sha256(f'{kind}:{body.query}:{text}'.encode()).hexdigest()
                row = db.execute('SELECT value FROM vectors WHERE key=?', (key,)).fetchone()
                if row:
                    result[index] = json.loads(row[0])
                    cached += 1
                else:
                    missing.append((index, key, text))
            if missing:
                texts = [text for _, _, text in missing]
                vectors = model.query_embed(texts) if body.query else model.embed(texts, batch_size=24)
                for (index, key, _), vector in zip(missing, vectors, strict=True):
                    vector = vector.tolist() if kind == 'dense' else {'indices': vector.indices.tolist(), 'values': vector.values.tolist()}
                    db.execute('INSERT OR REPLACE INTO vectors VALUES(?,?)', (key, json.dumps(vector)))
                    result[index] = vector
            db.execute('DELETE FROM vectors WHERE rowid IN (SELECT rowid FROM vectors ORDER BY rowid DESC LIMIT -1 OFFSET 100000)')
        return {'vectors': result, 'cached': cached, 'model': 'BAAI/bge-small-en-v1.5' if kind == 'dense' else 'Qdrant/bm25'}


@app.post('/dense', dependencies=[Depends(auth)])
def dense(body: Input):
    return encode(body, 'dense')


@app.post('/sparse', dependencies=[Depends(auth)])
def sparse(body: Input):
    return encode(body, 'sparse')
