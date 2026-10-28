import uuid

import pytest

from diffmind.store import Store


@pytest.mark.integration
def test_deduplication_supersession_and_lease(settings):
    db = Store(settings.database_url.get_secret_value())
    repo = "test/" + uuid.uuid4().hex
    first = db.enqueue(uuid.uuid4().hex, repo, 1, "a"*40, {"installation_id": 1})
    duplicate = db.enqueue(uuid.uuid4().hex, repo, 1, "a"*40, {"installation_id": 1})
    assert first["status"] == "queued" and duplicate["status"] == "duplicate_head"
    db.enqueue(uuid.uuid4().hex, repo, 1, "b"*40, {"installation_id": 1})
    job = db.claim(30)
    assert job["head"] == "b"*40
    assert db.claim(30) is None
    forged = job | {"lease_token": uuid.uuid4()}
    assert not db.heartbeat(forged, 30)
    db.finish(forged, {"bad": True})
    with db.connection() as c:
        assert c.execute("SELECT status FROM dm_jobs WHERE id=%s", (job["id"],)).fetchone()["status"] == "running"
    db.finish(job, {"tested": True})
    exhausted = db.enqueue(uuid.uuid4().hex, repo, 2, "c"*40, {"installation_id": 1})
    exhausted_job = db.claim(30)
    assert db.prepare(exhausted_job, {"findings": [], "status": "done"})
    assert not db.prepare(exhausted_job | {"lease_token": uuid.uuid4()}, {"bad": True})
    with db.connection() as c:
        c.execute("UPDATE dm_jobs SET attempts=3,lease_until=now()-interval '1 second' WHERE id=%s",
                  (exhausted["job_id"],))
    assert db.claim(30) is None
    with db.connection() as c:
        terminal = c.execute("SELECT status,result FROM dm_jobs WHERE id=%s", (exhausted["job_id"],)).fetchone()
        assert terminal["status"] == "failed"
        assert terminal["result"]["status"] == "done"
    db.close()
