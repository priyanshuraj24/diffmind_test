UPDATE dmn_jobs SET result=$1::jsonb WHERE id=$2::uuid AND execution_id=$3 AND status='running'
 AND lease_until>now() RETURNING id;
