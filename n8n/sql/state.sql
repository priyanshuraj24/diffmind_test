SELECT COALESCE((SELECT paused FROM dmn_prs WHERE repo=$1 AND number=$2),false) AS paused,
 (SELECT last_head FROM dmn_prs WHERE repo=$1 AND number=$2) AS last_head,
 COALESCE((SELECT jsonb_agg(payload) FROM dmn_findings WHERE repo=$1 AND number=$2),'[]'::jsonb) AS findings;
