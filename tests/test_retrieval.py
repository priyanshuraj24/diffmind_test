import uuid
from pathlib import Path

import pytest

from diffmind.retrieval import Index
from diffmind.store import Store


@pytest.mark.integration
def test_real_hybrid_search_is_revision_and_repo_scoped(settings):
    settings.data_dir = Path(".local/retrieval-test")
    settings.collection = "test_" + uuid.uuid4().hex
    db = Store(settings.database_url.get_secret_value())
    index = Index(settings, db)
    try:
        files = {"policy.py": "def require_owner(actor, owner):\n    if actor != owner:\n        raise PermissionError('owner only')\n",
                 "refund.py": "def refund(payment, actor, amount):\n    require_owner(actor, payment.owner)\n    return amount\n"}
        chunks, coverage = index.build("org/a", "a"*40, files, [])
        index.build("org/b", "a"*40, {"policy.py": "def require_owner(actor, owner):\n    return True\n"}, [])
        evidence, trace = index.search("org/a", "a"*40, "require_owner refund actor authorization", chunks, ["refund.py"])
        assert trace["lexical_candidates"] and trace["semantic_candidates"]
        assert any(e["path"] == "policy.py" and "PermissionError" in e["text"] for e in evidence)
        assert all("return True" not in e["text"] for e in evidence)
        newer = files | {"policy.py": "def require_owner(actor, owner):\n    raise PermissionError('disabled')\n"}
        chunks2, coverage2 = index.build("org/a", "b"*40, newer, [])
        assert coverage2["reused_embeddings"] > 0
        evidence2, _ = index.search("org/a", "b"*40, "require_owner", chunks2, [])
        assert not any("owner only" in e["text"] for e in evidence2)
        assert coverage["chunks"] > 0
        # A changed exclude policy can replace files while keeping the same point count.
        replacement = {"new.py": "def current_only():\n    return 7\n"}
        index.build("org/a", "a"*40, replacement, [])
        points, _ = index.client.scroll(settings.collection, scroll_filter=index.scope("org/a", "a"*40), limit=100)
        assert {p.payload["path"] for p in points} == {"new.py"}
    finally:
        index.client.delete_collection(settings.collection)
        db.close()
