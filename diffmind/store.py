import uuid
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

SCHEMA = """
CREATE TABLE IF NOT EXISTS dm_deliveries(id text PRIMARY KEY, received_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS dm_prs(repo text, number int, paused bool DEFAULT false,
 last_head text, summary_id bigint, PRIMARY KEY(repo,number));
CREATE TABLE IF NOT EXISTS dm_jobs(
 id uuid PRIMARY KEY, delivery text, repo text NOT NULL, number int NOT NULL,
 head text NOT NULL, payload jsonb NOT NULL, kind text NOT NULL DEFAULT 'review',
 status text NOT NULL DEFAULT 'queued', attempts int NOT NULL DEFAULT 0,
 ready_at timestamptz NOT NULL DEFAULT now(), lease_until timestamptz, lease_token uuid,
 created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
 result jsonb, error text, UNIQUE(repo,number,head,kind));
CREATE INDEX IF NOT EXISTS dm_jobs_ready ON dm_jobs(status,ready_at);
CREATE TABLE IF NOT EXISTS dm_findings(repo text, number int, fingerprint text,
 payload jsonb NOT NULL, head text NOT NULL, state text NOT NULL DEFAULT 'open',
 comment_id bigint, PRIMARY KEY(repo,number,fingerprint));
CREATE TABLE IF NOT EXISTS dm_generations(repo text, head text, count int NOT NULL,
 coverage jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(repo,head));
"""


class Store:
    def __init__(self, dsn):
        self.pool = ConnectionPool(dsn, min_size=1, max_size=4, open=True, kwargs={"row_factory": dict_row})
        with self.pool.connection() as conn:
            conn.execute(SCHEMA)

    def close(self):
        self.pool.close()

    @contextmanager
    def connection(self):
        with self.pool.connection() as conn:
            yield conn

    def enqueue(self, delivery, repo, number, head, payload, delay=0, kind="review"):
        with self.connection() as c:
            if not c.execute("INSERT INTO dm_deliveries(id) VALUES(%s) ON CONFLICT DO NOTHING RETURNING id",
                             (delivery,)).fetchone():
                return {"status": "duplicate_delivery"}
            c.execute("INSERT INTO dm_prs(repo,number) VALUES(%s,%s) ON CONFLICT DO NOTHING", (repo, number))
            paused = c.execute("SELECT paused FROM dm_prs WHERE repo=%s AND number=%s", (repo, number)).fetchone()
            if paused["paused"] and kind == "review":
                return {"status": "paused"}
            c.execute("UPDATE dm_jobs SET status='superseded',finished_at=now() WHERE repo=%s AND number=%s "
                      "AND head<>%s AND status='queued'", (repo, number, head))
            job_id = uuid.uuid4()
            row = c.execute("INSERT INTO dm_jobs(id,delivery,repo,number,head,payload,kind,ready_at) "
                            "VALUES(%s,%s,%s,%s,%s,%s,%s,now()+%s*interval '1 second') "
                            "ON CONFLICT(repo,number,head,kind) DO NOTHING RETURNING id",
                            (job_id, delivery, repo, number, head, Jsonb(payload), kind, delay)).fetchone()
            return {"status": "queued" if row else "duplicate_head", "job_id": str(row["id"]) if row else None}

    def claim(self, lease_seconds):
        with self.connection() as c:
            # A process-wide advisory lock makes indexing single-writer across service replicas.
            if not c.execute("SELECT pg_try_advisory_xact_lock(891721) AS locked").fetchone()["locked"]:
                return None
            c.execute("UPDATE dm_jobs SET status=CASE WHEN attempts>=3 THEN 'failed' ELSE 'queued' END,"
                      "lease_token=NULL,error='Worker lease expired',"
                      "finished_at=CASE WHEN attempts>=3 THEN now() END "
                      "WHERE status='running' AND lease_until<now()")
            if c.execute("SELECT 1 FROM dm_jobs WHERE status='running' LIMIT 1").fetchone():
                return None
            row = c.execute("SELECT * FROM dm_jobs WHERE status='queued' AND ready_at<=now() AND attempts<3 "
                            "ORDER BY ready_at FOR UPDATE SKIP LOCKED LIMIT 1").fetchone()
            if not row:
                return None
            token = uuid.uuid4()
            c.execute("UPDATE dm_jobs SET status='running',attempts=attempts+1,lease_token=%s,"
                      "lease_until=now()+%s*interval '1 second' WHERE id=%s", (token, lease_seconds, row["id"]))
            return row | {"lease_token": token, "attempts": row["attempts"] + 1}

    def heartbeat(self, job, seconds):
        with self.connection() as c:
            return c.execute("UPDATE dm_jobs SET lease_until=now()+%s*interval '1 second' "
                             "WHERE id=%s AND lease_token=%s AND status='running' RETURNING id",
                             (seconds, job["id"], job["lease_token"])).fetchone() is not None

    def finish(self, job, result, status="done"):
        with self.connection() as c:
            c.execute("UPDATE dm_jobs SET status=%s,result=%s,finished_at=now(),lease_token=NULL "
                      "WHERE id=%s AND lease_token=%s", (status, Jsonb(result), job["id"], job["lease_token"]))

    def prepare(self, job, result):
        with self.connection() as c:
            return c.execute("UPDATE dm_jobs SET result=%s WHERE id=%s AND lease_token=%s "
                             "AND status='running' RETURNING id",
                             (Jsonb(result), job["id"], job["lease_token"])).fetchone() is not None

    def fail(self, job, error):
        status = "queued" if job["attempts"] < 3 else "failed"
        with self.connection() as c:
            c.execute("UPDATE dm_jobs SET status=%s,error=%s,lease_token=NULL,"
                      "ready_at=now()+interval '60 seconds',finished_at=CASE WHEN %s='failed' THEN now() END "
                      "WHERE id=%s AND lease_token=%s", (status, error[:1000], status, job["id"], job["lease_token"]))

    def pr_state(self, repo, number):
        with self.connection() as c:
            return c.execute("SELECT * FROM dm_prs WHERE repo=%s AND number=%s", (repo, number)).fetchone() or {}

    def set_pause(self, repo, number, value):
        with self.connection() as c:
            c.execute("INSERT INTO dm_prs(repo,number,paused) VALUES(%s,%s,%s) "
                      "ON CONFLICT(repo,number) DO UPDATE SET paused=EXCLUDED.paused", (repo, number, value))
            if value:
                c.execute("UPDATE dm_jobs SET status='superseded' WHERE repo=%s AND number=%s AND status='queued'",
                          (repo, number))

    def findings(self, repo, number):
        with self.connection() as c:
            return c.execute("SELECT * FROM dm_findings WHERE repo=%s AND number=%s AND state='open'",
                             (repo, number)).fetchall()

    def published(self, job, findings, summary_id):
        with self.connection() as c:
            for finding in findings:
                c.execute("INSERT INTO dm_findings(repo,number,fingerprint,payload,head,comment_id) "
                          "VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(repo,number,fingerprint) DO UPDATE "
                          "SET payload=EXCLUDED.payload,head=EXCLUDED.head,comment_id=EXCLUDED.comment_id,state='open'",
                          (job["repo"], job["number"], finding["fingerprint"], Jsonb(finding), job["head"],
                           finding.get("comment_id")))
            c.execute("UPDATE dm_prs SET last_head=%s,summary_id=%s WHERE repo=%s AND number=%s",
                      (job["head"], summary_id, job["repo"], job["number"]))

    def generation(self, repo, head, count=None, coverage=None):
        with self.connection() as c:
            if count is not None:
                c.execute("INSERT INTO dm_generations(repo,head,count,coverage) VALUES(%s,%s,%s,%s) "
                          "ON CONFLICT(repo,head) DO UPDATE SET count=EXCLUDED.count,coverage=EXCLUDED.coverage",
                          (repo, head, count, Jsonb(coverage)))
            return c.execute("SELECT * FROM dm_generations WHERE repo=%s AND head=%s", (repo, head)).fetchone()
