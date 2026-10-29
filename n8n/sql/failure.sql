UPDATE dmn_jobs SET status=CASE WHEN attempts<3 THEN 'queued' ELSE 'failed' END,
 error=$2,ready_at=now()+interval '60 seconds',lease_until=NULL,
 finished_at=CASE WHEN attempts>=3 THEN now() END
 WHERE execution_id=$1 AND status='running' RETURNING id,status;
