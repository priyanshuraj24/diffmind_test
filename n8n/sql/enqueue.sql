WITH input AS (SELECT $1::jsonb AS j),
delivery AS (INSERT INTO dmn_deliveries(id) SELECT j->>'delivery' FROM input ON CONFLICT DO NOTHING RETURNING id),
pr AS (INSERT INTO dmn_prs(repo,number,paused)
 SELECT j->>'repo',(j->>'number')::int,COALESCE(j->>'command'='/diffmind pause',false) FROM input,delivery
 ON CONFLICT(repo,number) DO UPDATE SET paused=CASE
 WHEN (SELECT j->>'command' FROM input)='/diffmind pause' THEN true
 WHEN (SELECT j->>'command' FROM input)='/diffmind resume' THEN false ELSE dmn_prs.paused END
 RETURNING paused),
supersede AS (UPDATE dmn_jobs SET status='superseded',finished_at=now() FROM input,delivery
 WHERE repo=j->>'repo' AND number=(j->>'number')::int AND status='queued'
 AND (head<>j->>'head' OR j->>'command'='/diffmind pause')),
queued AS (INSERT INTO dmn_jobs(id,repo,number,head,installation_id,kind,ready_at)
 SELECT (j->>'id')::uuid,j->>'repo',(j->>'number')::int,j->>'head',(j->>'installation_id')::bigint,j->>'kind',now()+interval '15 seconds'
 FROM input,pr WHERE NOT COALESCE(pr.paused,false) AND COALESCE(j->>'command','')<>'/diffmind pause'
 ON CONFLICT(repo,number,head,kind) DO NOTHING RETURNING id)
SELECT CASE WHEN EXISTS(SELECT 1 FROM queued) THEN 'queued'
 WHEN NOT EXISTS(SELECT 1 FROM delivery) THEN 'duplicate_delivery'
 WHEN EXISTS(SELECT 1 FROM pr WHERE paused) THEN 'paused' ELSE 'duplicate_head' END AS status;
