WITH current AS (INSERT INTO dmn_generations(repo,head) VALUES($1,$2)
 ON CONFLICT(repo,head) DO UPDATE SET created_at=now() RETURNING head),
recent AS (SELECT head FROM dmn_generations WHERE repo=$1 AND head<>$2 ORDER BY created_at DESC LIMIT 2)
SELECT $1 AS repo,jsonb_agg(head) AS heads FROM (SELECT head FROM current UNION ALL SELECT head FROM recent) AS keep;
