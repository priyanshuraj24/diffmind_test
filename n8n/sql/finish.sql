WITH findings AS (INSERT INTO dmn_findings(repo,number,fingerprint,payload)
 SELECT $1,$2,f->>'fingerprint',f FROM jsonb_array_elements($3::jsonb->'findings') AS f
 ON CONFLICT(repo,number,fingerprint) DO UPDATE SET payload=EXCLUDED.payload),
pr AS (UPDATE dmn_prs SET last_head=$4,summary_id=$5 WHERE repo=$1 AND number=$2)
UPDATE dmn_jobs SET status='done',finished_at=now(),lease_until=NULL,error=NULL
 WHERE id=$6::uuid AND execution_id=$7 RETURNING id,status,head,result;
