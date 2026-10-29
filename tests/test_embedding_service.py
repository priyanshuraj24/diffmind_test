import importlib
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient
from tokenizers import Tokenizer, models, pre_tokenizers


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setenv('EMBEDDING_DATA', str(tmp_path))
    monkeypatch.setenv('EMBEDDING_TOKEN', 'test-only')
    module = importlib.import_module('embedding_service.app')
    monkeypatch.setattr(module, 'root', tmp_path)
    tokenizer = Tokenizer(models.WordLevel({'word': 0}, unk_token='word'))
    tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()

    class Dense:
        model = SimpleNamespace(tokenizer=tokenizer)
        calls = 0

        def embed(self, texts, batch_size=24):
            self.calls += 1
            return iter(np.ones(384, dtype=np.float32) for _ in texts)

        def query_embed(self, texts):
            return self.embed(texts)

    fake = Dense()
    monkeypatch.setattr(module, 'models', {'dense': fake})
    return TestClient(module.app), fake


def test_inference_requires_private_token(service):
    client, model = service
    assert client.post('/dense', json={'input': ['word']}).status_code == 401
    assert model.calls == 0


def test_embeddings_are_batched_and_cached(service):
    client, model = service
    headers = {'Authorization': 'Bearer test-only'}
    first = client.post('/dense', headers=headers, json={'input': ['word', 'word word']})
    assert first.status_code == 200
    assert len(first.json()['vectors']) == 2
    assert model.calls == 1
    second = client.post('/dense', headers=headers, json={'input': ['word', 'word word']})
    assert second.json()['cached'] == 2
    assert model.calls == 1


def test_oversized_token_sequences_are_not_silently_truncated(service):
    client, model = service
    response = client.post('/dense', headers={'Authorization': 'Bearer test-only'},
                           json={'input': ['word '*501]})
    assert response.status_code == 422
    assert model.calls == 0
