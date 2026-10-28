import asyncio
import hashlib
import hmac
import json
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request

from .config import Settings
from .engine import Engine
from .github import GitHub
from .store import Store

log = logging.getLogger("diffmind")


def valid_signature(raw, signature, secret):
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature or "", expected)


def create_app(settings=None, store=None, github=None, engine=None):
    s = settings or Settings()
    db = store or Store(s.database_url.get_secret_value())
    gh = github or GitHub(s.github_app_id, s.github_private_key)
    runner = engine or Engine(s, db, gh)
    stopping = threading.Event()

    def work():
        while not stopping.is_set():
            result = runner.run_once()
            if result["status"] not in {"idle", "busy"}:
                log.info("review_job %s", json.dumps({k: result.get(k) for k in ("job_id", "status", "error_type")}))
            stopping.wait(3)

    @asynccontextmanager
    async def lifespan(app):
        thread = None
        if s.worker_enabled:
            thread = threading.Thread(target=work, daemon=True)
            thread.start()
        yield
        stopping.set()
        if thread:
            await asyncio.to_thread(thread.join, 10)
        if store is None:
            db.close()

    app = FastAPI(title="DiffMind", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    def internal(authorization: str = Header(default="")):
        if not hmac.compare_digest(authorization, "Bearer " + s.internal_token.get_secret_value()):
            raise HTTPException(401, "Unauthorized")

    @app.get("/health")
    @app.get("/diffmind/health")
    def health():
        return {"status": "ok", "version": "0.1.0"}

    @app.post("/diffmind/webhook", status_code=202)
    async def webhook(request: Request):
        raw = bytearray()
        async for block in request.stream():
            raw.extend(block)
            if len(raw) > 2_000_000:
                raise HTTPException(413, "Payload too large")
        if not valid_signature(raw, request.headers.get("x-hub-signature-256"), s.webhook_secret.get_secret_value()):
            raise HTTPException(401, "Invalid signature")
        delivery = request.headers.get("x-github-delivery", "")
        if not delivery or len(delivery) > 200:
            raise HTTPException(400, "Missing delivery ID")
        try:
            body = json.loads(raw)
        except ValueError:
            raise HTTPException(400, "Invalid JSON") from None
        event = request.headers.get("x-github-event", "")
        if event == "ping":
            return {"status": "pong"}
        repo = body.get("repository", {}).get("full_name", "")
        if not s.allows(repo):
            return {"status": "ignored", "reason": "repository_not_allowed"}
        installation = body.get("installation", {}).get("id")
        if not installation:
            installation = await asyncio.to_thread(gh.installation_for_repo, repo)
        action = body.get("action")
        if event == "pull_request" and action in {"opened", "reopened", "synchronize", "ready_for_review"}:
            pr = body.get("pull_request", {})
            if pr.get("draft"):
                return {"status": "ignored", "reason": "draft"}
            return db.enqueue(delivery, repo, int(body["number"]), pr["head"]["sha"],
                              {"installation_id": installation}, s.debounce_seconds)
        if event == "issue_comment" and action == "created" and body.get("issue", {}).get("pull_request"):
            comment = body["comment"]
            command = comment.get("body", "").strip().lower()
            if comment.get("user", {}).get("type") == "Bot" or command not in {
                "/diffmind review", "/diffmind full-review", "/diffmind pause", "/diffmind resume"}:
                return {"status": "ignored"}
            if not await asyncio.to_thread(gh.can_command, repo, comment["user"]["login"], installation):
                raise HTTPException(403, "Command requires repository write permission")
            number = int(body["issue"]["number"])
            if command.endswith("pause"):
                db.set_pause(repo, number, True)
                return {"status": "paused"}
            if command.endswith("resume"):
                db.set_pause(repo, number, False)
            pr = await asyncio.to_thread(gh.pr, repo, number, installation)
            return db.enqueue(delivery, repo, number, pr["head"]["sha"], {"installation_id": installation},
                              kind=("full:" if "full-review" in command else "manual:") + delivery)
        return {"status": "ignored", "event": event, "action": action}

    @app.post("/internal/run-once", dependencies=[Depends(internal)])
    def run_once():
        result = runner.run_once()
        # n8n sees an actual failed HTTP node instead of a misleading successful execution.
        if result["status"] == "error":
            raise HTTPException(502, result)
        return result

    @app.get("/internal/jobs", dependencies=[Depends(internal)])
    def jobs():
        with db.connection() as c:
            return c.execute("SELECT id,repo,number,head,status,attempts,created_at,finished_at,error,result "
                             "FROM dm_jobs ORDER BY created_at DESC LIMIT 20").fetchall()

    return app
