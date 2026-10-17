"""CLI orchestration. All graph writes go through the contracted graph.writer API."""
import argparse
import importlib
import json
import os
from datetime import datetime, timezone

from dotenv import load_dotenv

from ingest.github_loader import CACHE, GitHub
from ingest.synthetic_data import populate
from ingest.transform import real


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def graph():
    from falkordb import FalkorDB
    load_dotenv()
    name = os.environ.get('FALKORDB_GRAPH', 'blast_radius')
    if name != 'blast_radius':
        raise ValueError('This ingestion command only targets graph blast_radius')
    return FalkorDB(host=os.environ.get('FALKORDB_HOST', 'localhost'),
                    port=int(os.environ.get('FALKORDB_PORT', 6379)),
                    username=os.environ.get('FALKORDB_USERNAME') or None,
                    password=os.environ.get('FALKORDB_PASSWORD') or None).select_graph(name)


def writer_module():
    try:
        return importlib.import_module('graph.writer')
    except ModuleNotFoundError as exc:
        if exc.name != 'graph.writer':
            raise
        raise RuntimeError('graph.writer is not present in this checkout. Merge the graph '
                           'owner’s implementation of contracts/schema.md before loading.') from exc


def persist(records, writer, batch_size=250):
    writer.ensure_indexes()
    counts = {'nodes_upserted': 0, 'edges_upserted': 0}
    for label, by_id in records.nodes.items():
        rows = list(by_id.values())
        for offset in range(0, len(rows), batch_size):
            result = writer.upsert_nodes(label, rows[offset:offset + batch_size])
            counts['nodes_upserted'] += result['upserted']
    for (kind, source, target), by_pair in records.edges.items():
        rows = list(by_pair.values())
        for offset in range(0, len(rows), batch_size):
            result = writer.upsert_edges(kind, source, target, rows[offset:offset + batch_size])
            counts['edges_upserted'] += result['upserted']
    return counts


def inspect_graph(g):
    # Read-only Cypher; all graph mutations belong to graph.writer.
    nodes = g.query('MATCH (n) WHERE coalesce(n.operational, false) = false '
                    'RETURN labels(n)[0], count(n)', {}).result_set
    edges = g.query('MATCH ()-[r]->() WHERE coalesce(r.operational, false) = false '
                    'RETURN type(r), count(r)', {}).result_set
    sanity = {
        'cartservice_blast_radius': g.query(
            'MATCH (s:Service {id: $id})<-[:DEPENDS_ON*1..4]-(caller:Service) '
            'RETURN DISTINCT caller.name ORDER BY caller.name', {'id': 'svc:cartservice'}).result_set,
        'checkoutservice_contributors': g.query(
            'MATCH (s:Service {id: $id})-[:CONTAINS]->(f:File)<-[:TOUCHED]-(p:PR)'
            '<-[:AUTHORED]-(a:Person) RETURN a.name, count(DISTINCT p) AS prs '
            'ORDER BY prs DESC LIMIT $limit', {'id': 'svc:checkoutservice', 'limit': 10}).result_set,
        'frontend_incidents': g.query(
            'MATCH (i:Incident)-[:AFFECTED]->(s:Service {id: $id}) '
            'RETURN i.id, i.severity, i.started_at ORDER BY i.started_at DESC',
            {'id': 'svc:frontend'}).result_set,
    }
    return dict(nodes_by_label=dict(nodes), edges_by_type=dict(edges), sanity=sanity)


def save_snapshot(snapshot):
    CACHE.mkdir(exist_ok=True)
    target = CACHE / 'snapshot.json'
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(snapshot, ensure_ascii=False))
    temporary.replace(target)


def merge_updates(snapshot, updates):
    for key in ('pulls', 'issues'):
        records = {r['detail']['number']: r for r in snapshot.get(key, [])}
        records.update({r['detail']['number']: r for r in updates[key]})
        snapshot[key] = list(records.values())


def load_all(reset=False):
    load_dotenv()
    writer = writer_module()  # Fail before fetching or resetting when integration is absent.
    started = utcnow()
    client = GitHub()
    try:
        cached_files = list(CACHE.glob('*.json'))
        since = datetime.fromtimestamp(min((p.stat().st_mtime for p in cached_files),
                                           default=datetime.now().timestamp()), timezone.utc)
        snapshot = client.collect()
        updates = client.updated(since.isoformat(timespec='seconds').replace('+00:00', 'Z'))
        merge_updates(snapshot, updates)
        records = real(snapshot)
        missing = populate(records)
        g = graph()
        if reset:
            # SDK graph deletion, not a bespoke Cypher writer. Only blast_radius is allowed.
            g.delete()
        counts = persist(records, writer)
        report = inspect_graph(g)
        save_snapshot(snapshot)
        writer.set_sync_meta(started,
                             last_synced_commit_sha=snapshot['commits'][0]['detail']['sha'],
                             last_synced_issue_number=max((r['detail']['number'] for r in
                                 snapshot['issues'] + snapshot['pulls']), default=0))
        return dict(status='ok', started_at=started, finished_at=utcnow(), **counts, **report,
                    missing_synthetic_artifacts=missing)
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--all', action='store_true', required=True)
    parser.add_argument('--reset', action='store_true', help='Delete blast_radius before loading')
    args = parser.parse_args()
    print(json.dumps(load_all(reset=args.reset), indent=2))


if __name__ == '__main__':
    main()
