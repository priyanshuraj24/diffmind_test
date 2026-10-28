from unittest.mock import Mock

import pytest

from diffmind.engine import Engine


def fixture(settings):
    gh, store = Mock(), Mock()
    engine = Engine(settings, store, gh)
    engine.current = Mock(return_value=({}, True))
    gh.own_comment.side_effect = lambda c: c.get('user', {}).get('login') == 'diffmind[bot]'
    gh.request.return_value = {'id': 42}
    job = {'id': 'job1', 'repo': 'org/repo', 'number': 1, 'head': 'a'*40,
           'payload': {'installation_id': 1}}
    finding = {'fingerprint': 'unique', 'path': 'x.py', 'line': 3, 'side': 'RIGHT',
               'title': 'Missing authorization', 'severity': 'P1', 'body': 'Any user can refund.',
               'scenario': 'A different account submits the request.', 'evidence': [], 'suggestion': None}
    result = {'findings': [finding], 'coverage': {'chunks': 5}, 'incremental': False,
              'retrieval': [{}], 'summary': 'One issue.'}
    return engine, gh, store, job, result


def test_publication_reconciles_timeout_without_duplicate_review(settings):
    engine, gh, store, job, result = fixture(settings)
    gh.pages.side_effect = [
        [{'body': '<!-- diffmind:review:job1 -->', 'user': {'login': 'diffmind[bot]'}}],
        [{'id': 12, 'body': '<!-- diffmind:finding:unique -->', 'user': {'login': 'diffmind[bot]'}}],
        [{'id': 40, 'body': '<!-- diffmind:summary:v1 -->', 'user': {'login': 'stranger'}},
         {'id': 41, 'body': '<!-- diffmind:summary:v1 -->', 'user': {'login': 'diffmind[bot]'}}],
    ]
    engine.publish(job, result, [])
    assert gh.request.call_count == 1
    assert gh.request.call_args.args[:2] == ('PATCH', '/repos/org/repo/issues/comments/41')
    assert result['findings'][0]['comment_id'] == 12
    store.published.assert_called_once()


def test_publication_stops_if_head_changed(settings):
    engine, gh, store, job, result = fixture(settings)
    gh.pages.return_value = []
    engine.current.return_value = ({}, False)
    with pytest.raises(RuntimeError, match='Head changed'):
        engine.publish(job, result, [])
    gh.request.assert_not_called()
    store.published.assert_not_called()


def test_inline_review_is_bound_to_commit_and_diff_side(settings):
    engine, gh, store, job, result = fixture(settings)
    gh.pages.return_value = []
    engine.publish(job, result, [])
    review = gh.request.call_args_list[0].kwargs['json']
    assert review['commit_id'] == job['head']
    assert review['comments'][0]['line'] == 3
    assert review['comments'][0]['side'] == 'RIGHT'
