import json
import uuid
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).parents[1] / 'n8n/sql'


@pytest.mark.integration
def test_native_queue_delivery_dedup_and_publication_intent():
    with psycopg.connect('postgresql://diffmind:local-test-only@127.0.0.1:16433/diffmind_test', autocommit=True, connect_timeout=5) as db:
        db.execute((ROOT / 'schema.sql').read_text())
        event = dict(id=str(uuid.uuid4()), delivery=str(uuid.uuid4()), repo='test/'+uuid.uuid4().hex,
                     number=1, head='a'*40, installation_id=1, kind='review', command=None)
        # n8n uses PostgreSQL $n query placeholders; psycopg uses %s client placeholders.
        enqueue = (ROOT/'enqueue.sql').read_text().replace('$1::jsonb', '%s::jsonb')
        assert db.execute(enqueue, (json.dumps(event),)).fetchone()[0] == 'queued'
        assert db.execute(enqueue, (json.dumps(event),)).fetchone()[0] == 'duplicate_delivery'
        event['delivery'] = str(uuid.uuid4())
        assert db.execute(enqueue, (json.dumps(event),)).fetchone()[0] == 'duplicate_head'
        db.execute("UPDATE dmn_jobs SET ready_at=now() WHERE id=%s", (event['id'],))
        claim = (ROOT/'claim.sql').read_text().replace('$1', '%s')
        row = db.execute(claim, ('native-test',)).fetchone()
        assert str(row[0]) == event['id']
        assert db.execute(claim, ('second',)).fetchone() is None
        result = {'summary': 'No findings', 'findings': []}
        prepare = (ROOT/'prepare.sql').read_text().replace('$1', '%s').replace('$2', '%s').replace('$3', '%s')
        assert db.execute(prepare, (json.dumps(result), event['id'], 'wrong-execution')).fetchone() is None
        assert db.execute(prepare, (json.dumps(result), event['id'], 'native-test')).fetchone()
        db.execute("UPDATE dmn_jobs SET status='done',lease_until=NULL WHERE id=%s", (event['id'],))
