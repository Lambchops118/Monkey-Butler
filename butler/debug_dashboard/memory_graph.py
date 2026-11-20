"""Bounded diagnostic projection; never create, migrate or write the database."""
import sqlite3
from pathlib import Path

from butler.storage import connect_readonly


def read_memory_graph(path: Path, *, limit: int = 250, archived: bool = False):
    if not 1 <= limit <= 500:
        raise ValueError('node limit must be 1..500')
    empty = dict(nodes=[], edges=[], coverage=None)
    if not path.is_file():
        return dict(ok=False, status='unavailable', error='Database not found; start Butler to initialize LTMS.', **empty)
    connection = None
    try:
        connection = connect_readonly(path)
        connection.execute('BEGIN')  # Counts and graph from one consistent read snapshot.
        condition = '' if archived else 'WHERE archived=0'
        total = connection.execute('SELECT count(*) FROM ltms_memories ' + condition).fetchone()[0]
        rows = connection.execute('''SELECT id,content,source,updated_at,archived,
            (embedding IS NOT NULL) AS embedded FROM ltms_memories ''' + condition +
            ' ORDER BY updated_at DESC,id LIMIT ?', (limit,)).fetchall()
        nodes = [dict(row) for row in rows]
        # Count eligible edges independently of the selected node page.
        edge_filter = '' if archived else 'WHERE s.archived=0 AND t.archived=0'
        total_edges = connection.execute('''SELECT count(*) FROM ltms_edges e
            JOIN ltms_memories s ON s.id=e.source_id JOIN ltms_memories t ON t.id=e.target_id ''' + edge_filter).fetchone()[0]
        edges = []
        if nodes:
            ids = [n['id'] for n in nodes]
            placeholders = ','.join('?' for _ in ids)
            edges = [dict(r) for r in connection.execute(f'''SELECT source_id,target_id,relation
                FROM ltms_edges WHERE source_id IN ({placeholders}) AND target_id IN ({placeholders})
                ORDER BY source_id,target_id,relation LIMIT 2000''', ids + ids)]
        return dict(ok=True, status='available', error=None, nodes=nodes, edges=edges,
                    coverage=dict(total_nodes=total, shown_nodes=len(nodes), omitted_nodes=total-len(nodes),
                                  total_edges=total_edges, shown_edges=len(edges), omitted_edges=total_edges-len(edges)))
    except sqlite3.Error:
        return dict(ok=False, status='unavailable', error='LTMS tables unavailable or database unreadable. No changes were made.', **empty)
    finally:
        if connection is not None:
            connection.close()
