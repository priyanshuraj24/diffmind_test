import hashlib
import hmac
import json
from unittest.mock import Mock

from fastapi.testclient import TestClient

from diffmind.api import create_app


def request(client, payload, event="pull_request", signature=True):
    raw = json.dumps(payload).encode()
    digest = hmac.new(b"test-secret", raw, hashlib.sha256).hexdigest()
    return client.post("/diffmind/webhook", content=raw, headers={"x-hub-signature-256": "sha256="+digest if signature else "bad",
                       "x-github-delivery": "delivery-1", "x-github-event": event})


def test_auth_scope_and_drafts(settings):
    db, gh = Mock(), Mock()
    db.enqueue.return_value = {"status": "queued"}
    payload = {"repository": {"full_name": "priyanshuraj24/diffmind_test"}, "installation": {"id": 1},
               "action": "synchronize", "number": 1, "pull_request": {"head": {"sha": "a"*40}, "draft": False}}
    with TestClient(create_app(settings, db, gh, Mock())) as client:
        assert request(client, payload, signature=False).status_code == 401
        assert not db.enqueue.called
        assert request(client, payload).json()["status"] == "queued"
        db.enqueue.assert_called_once()
        payload["pull_request"]["draft"] = True
        assert request(client, payload).json()["reason"] == "draft"
        payload["repository"]["full_name"] = "other/private"
        assert request(client, payload).json()["reason"] == "repository_not_allowed"
        assert client.post("/internal/run-once").status_code == 401


def test_command_permissions(settings):
    db, gh = Mock(), Mock()
    gh.can_command.return_value = False
    payload = {"repository": {"full_name": "priyanshuraj24/diffmind_test"}, "installation": {"id": 1},
               "action": "created", "issue": {"number": 1, "pull_request": {}},
               "comment": {"body": "/diffmind pause", "user": {"login": "stranger", "type": "User"}}}
    payload["issue"]["pull_request"] = {"url": "example"}
    with TestClient(create_app(settings, db, gh, Mock())) as client:
        assert request(client, payload, "issue_comment").status_code == 403
        assert not db.set_pause.called
        gh.can_command.return_value = True
        assert request(client, payload, "issue_comment").json()["status"] == "paused"


def test_worker_failure_is_not_successful_http(settings):
    runner = Mock()
    runner.run_once.return_value = {"status": "error", "error_type": "ConnectError"}
    with TestClient(create_app(settings, Mock(), Mock(), runner)) as client:
        response = client.post("/internal/run-once", headers={"Authorization": "Bearer test-internal"})
        assert response.status_code == 502
