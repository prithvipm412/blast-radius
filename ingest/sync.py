"""Incremental GitHub sync, callable by the API via sync() -> dict."""
import json
from datetime import datetime, timedelta

from dotenv import load_dotenv

from ingest.github_loader import CACHE, GitHub
from ingest.load import (graph, inspect_graph, load_all, merge_updates, persist,
                         save_snapshot, utcnow, writer_module)
from ingest.synthetic_data import populate
from ingest.transform import real


def sync() -> dict:
    load_dotenv()
    writer = writer_module()
    g = graph()
    rows = g.query('MATCH (m:SyncMeta {id: $id}) RETURN m.last_synced_at',
                   {'id': 'meta:sync'}).result_set
    snapshot_file = CACHE / 'snapshot.json'
    if not rows or not rows[0][0] or not snapshot_file.exists():
        return load_all()
    started = utcnow()
    # Overlap protects timestamp granularity and items changing during a previous fetch.
    since = (datetime.fromisoformat(rows[0][0].replace('Z', '+00:00')) - timedelta(minutes=5))
    client = GitHub()
    try:
        changes = client.updated(since.isoformat(timespec='seconds').replace('+00:00', 'Z'))
        snapshot = json.loads(snapshot_file.read_text())
        merge_updates(snapshot, changes)
        records = real(snapshot)
        missing = populate(records)
        counts = persist(records, writer)
        report = inspect_graph(g)
        save_snapshot(snapshot)
        # Advance only after successful writes and checks; start time avoids skipping races.
        writer.set_sync_meta(started, last_synced_issue_number=max(
            (r['detail']['number'] for r in snapshot['issues'] + snapshot['pulls']), default=0))
        return dict(status='ok', started_at=started, finished_at=utcnow(),
                    prs_fetched=len(changes['pulls']), issues_fetched=len(changes['issues']),
                    **counts, **report, missing_synthetic_artifacts=missing)
    finally:
        client.close()


if __name__ == '__main__':
    print(json.dumps(sync(), indent=2))
