CREATE TABLE IF NOT EXISTS dmn_prs(repo text, number int, paused boolean NOT NULL DEFAULT false,
 last_head text, summary_id bigint, PRIMARY KEY(repo,number));
CREATE TABLE IF NOT EXISTS dmn_deliveries(id text PRIMARY KEY, created_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS dmn_jobs(id uuid PRIMARY KEY, repo text, number int, head text, installation_id bigint,
 kind text, status text DEFAULT 'queued', attempts int DEFAULT 0, execution_id text, lease_until timestamptz,
 ready_at timestamptz DEFAULT now(), created_at timestamptz DEFAULT now(), finished_at timestamptz,
 result jsonb, error text, UNIQUE(repo,number,head,kind));
CREATE TABLE IF NOT EXISTS dmn_findings(repo text, number int, fingerprint text, payload jsonb,
 PRIMARY KEY(repo,number,fingerprint));
CREATE INDEX IF NOT EXISTS dmn_jobs_status ON dmn_jobs(status,ready_at);
CREATE TABLE IF NOT EXISTS dmn_generations(repo text, head text, created_at timestamptz DEFAULT now(), PRIMARY KEY(repo,head));
