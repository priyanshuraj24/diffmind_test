WITH lock AS (SELECT pg_try_advisory_xact_lock(891722) AS acquired),
exhausted AS (UPDATE dmn_jobs SET status='failed',finished_at=now(),error='Lease expired after three attempts'
 WHERE status='running' AND lease_until<now() AND attempts>=3),
candidate AS (SELECT id FROM dmn_jobs,lock WHERE lock.acquired AND attempts<3
 AND ((status='queued' AND ready_at<=now()) OR (status='running' AND lease_until<now()))
 AND NOT EXISTS(SELECT 1 FROM dmn_jobs WHERE status='running' AND lease_until>=now())
 ORDER BY ready_at FOR UPDATE OF dmn_jobs SKIP LOCKED LIMIT 1)
UPDATE dmn_jobs SET status='running',attempts=attempts+1,execution_id=$1,
 lease_until=now()+interval '60 minutes' WHERE id IN (SELECT id FROM candidate) RETURNING *;
