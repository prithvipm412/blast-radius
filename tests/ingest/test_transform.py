import base64
from datetime import datetime, timezone

from ingest.load import persist
from ingest.synthetic_data import populate
from ingest.transform import REPO, real


def snapshot():
    return {
        'repo': {'default_branch': 'main'}, 'contributors': [{'login': 'real-author'}],
        'pulls': [{'detail': {'number': 1, 'title': 'Cart change', 'html_url': 'https://example/pr/1',
                              'user': {'login': 'real-author'}, 'merged_at': '2026-01-01T00:00:00Z'},
                   'files': [{'filename': 'src/cartservice/cart.cs', 'additions': 2, 'deletions': 1}]}],
        'commits': [{'detail': {'sha': 'abc', 'html_url': 'https://example/commit/abc',
                               'author': None, 'commit': {'message': 'Change cart\nDetails',
                                                         'author': {'date': '2026-01-01T00:00:00Z'}}},
                     'files': [{'filename': 'src/cartservice/cart.cs'}]}],
        'issues': [{'detail': {'number': 2, 'title': 'cartservice issue', 'state': 'closed',
                               'html_url': 'https://example/issue/2', 'user': {'login': 'reporter'},
                               'labels': [{'name': 'bug'}]},
                    'linked_pulls': [{'number': 1, 'repository': {'nameWithOwner': REPO}}]}],
        'docs': [{'path': 'README.md', 'blob': {'content': base64.b64encode(
            b'# Online Boutique\ncartservice and frontend').decode()}}], 'codeowners': []}


def test_real_mapping_and_provenance():
    records = real(snapshot())
    assert len(records.nodes['Service']) == 12
    assert len(records.edges['DEPENDS_ON', 'Service', 'Service']) == 16
    assert records.nodes['Issue']['issue:2']['labels'] == ['bug']
    assert ('issue:2', 'pr:1') in records.edges['RESOLVED_BY', 'Issue', 'PR']
    assert ('svc:cartservice', 'file:src/cartservice/cart.cs') in records.edges[
        'CONTAINS', 'Service', 'File']
    assert not records.edges.get(('AUTHORED', 'Person', 'Commit'))
    assert all(not n['synthetic'] for group in records.nodes.values() for n in group.values())
    assert all(not e['synthetic'] for group in records.edges.values() for e in group.values())


def test_synthetic_invariants():
    records = real(snapshot())
    now = datetime(2026, 10, 17, tzinfo=timezone.utc)
    populate(records, now)
    assert len(records.nodes['Team']) == 5
    assert len(records.nodes['Incident']) == 18
    assert len(records.nodes['Decision']) == 8
    for key, edges in records.edges.items():
        kind, source, target = key
        for edge in edges.values():
            assert edge['from_id'] in records.nodes[source]
            assert edge['to_id'] in records.nodes[target]
            if source in ('Incident', 'Decision') or kind in ('MEMBER_OF', 'OWNS'):
                assert edge['synthetic'] is True
            if kind == 'MEMBER_OF':
                assert records.nodes['Person'][edge['from_id']]['synthetic'] is True
    affected = {e['to_id'] for e in records.edges['AFFECTED', 'Incident', 'Service'].values()
                if e['from_id'] == 'incident:inc-001'}
    assert affected == {'svc:cartservice', 'svc:checkoutservice', 'svc:frontend', 'svc:loadgenerator'}
    for inc in records.nodes['Incident'].values():
        age = now - datetime.fromisoformat(inc['started_at'].replace('Z', '+00:00'))
        assert 0 < age.days < 366
        assert inc['source_url'] == 'synthetic'
    before = records.counts()
    populate(records, now)
    assert records.counts() == before


def test_writer_batches_and_nodes_before_edges():
    calls = []
    class Writer:
        def ensure_indexes(self):
            calls.append(('indexes',))
        def upsert_nodes(self, label, rows):
            assert len(rows) <= 2
            calls.append(('node', label))
            return {'upserted': len(rows)}
        def upsert_edges(self, kind, source, target, rows):
            assert len(rows) <= 2
            calls.append(('edge', kind))
            return {'upserted': len(rows)}
    records = real(snapshot())
    result = persist(records, Writer(), batch_size=2)
    assert result['nodes_upserted'] == sum(records.counts()['nodes_by_label'].values())
    assert result['edges_upserted'] == sum(records.counts()['edges_by_type'].values())
    kinds = [c[0] for c in calls]
    assert kinds[0] == 'indexes'
    assert kinds.index('edge') > max(i for i, k in enumerate(kinds) if k == 'node')


def test_codeowners_last_match_and_github_team():
    data = snapshot()
    data['codeowners'] = [{'path': '.github/CODEOWNERS', 'blob': {'content': base64.b64encode(
        b'* @general\n/src/cartservice/ @org/cart\n').decode()}}]
    records = real(data)
    assert records.nodes['Team']['team:gh:org/cart']['synthetic'] is False
    edges = records.edges['OWNS', 'Team', 'File']
    assert ('team:gh:org/cart', 'file:src/cartservice/cart.cs') in edges
    assert ('person:general', 'file:src/cartservice/cart.cs') not in records.edges['OWNS', 'Person', 'File']
