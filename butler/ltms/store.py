"""Bounded graph operations on the shared application database."""
import json
import math
import re
import threading
import time
import uuid

from butler.storage import connect_database


def text(value, maximum=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError('invalid text')
    return value.strip()


def vector(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 4096:
        raise ValueError('invalid embedding dimensions')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in value):
        raise ValueError('invalid embedding')
    return value


class Store:
    def __init__(self, path=None):
        self.db = connect_database(path)
        self.lock = threading.RLock()

    def close(self):
        self.db.close()

    def memories(self):
        # v1 hard corpus bound; never silently search a truncated corpus.
        with self.lock:
            return [dict(r) for r in self.db.execute('SELECT * FROM ltms_memories WHERE archived=0')]

    def search_memories(self, query, embedding=None, model='', limit=8):
        text(query, 8000)
        if not 1 <= limit <= 16:
            raise ValueError('invalid limit')
        tokens = set(re.findall(r'\w+', query.lower()))
        ranked = []
        for row in self.memories():
            words = set(re.findall(r'\w+', row['content'].lower()))
            lexical = len(tokens & words) / max(1, len(tokens))
            semantic = 0.0
            saved = json.loads(row['embedding']) if row['embedding'] else None
            if embedding and saved and row['embedding_model'] == model and len(saved) == len(embedding):
                norm = math.sqrt(sum(v*v for v in saved) * sum(v*v for v in embedding))
                semantic = sum(a*b for a, b in zip(saved, embedding)) / norm if norm else 0
            score = max(lexical, semantic)
            if score > 0.15:
                ranked.append(dict(id=row['id'], content=row['content'], score=score,
                                   source=row['source'], updated_at=row['updated_at']))
        return sorted(ranked, key=lambda r: (-r['score'], r['id']))[:limit]

    def traverse_graph(self, ids, limit=16):
        if not isinstance(ids, list) or len(ids) > 16 or not 1 <= limit <= 32:
            raise ValueError('invalid traversal')
        with self.lock:
            result = []
            for key in ids:
                for row in self.db.execute('''SELECT e.*, m.content FROM ltms_edges e
                    JOIN ltms_memories m ON m.id=CASE WHEN e.source_id=? THEN e.target_id ELSE e.source_id END
                    JOIN ltms_memories s ON s.id=e.source_id JOIN ltms_memories t ON t.id=e.target_id
                    WHERE (e.source_id=? OR e.target_id=?) AND s.archived=0 AND t.archived=0 LIMIT ?''',
                    (key, key, key, limit)):
                    item = dict(row)
                    if item not in result:
                        result.append(item)
            return result[:limit]

    def apply(self, operations, evidence, job_id=None):
        """One atomic validated batch. Model never supplies SQL or executable code."""
        if not isinstance(operations, list) or len(operations) > 16:
            raise ValueError('invalid batch')
        source = text(evidence, 16000)
        results = []
        with self.lock, self.db:
            for operation in operations:
                if not isinstance(operation, dict):
                    raise ValueError('invalid operation')
                op = operation.get('op')
                fields = {'create_memory': {'content'}, 'update_memory': {'id', 'content'},
                          'archive_memory': {'id'}, 'forget_memory': {'id'},
                          'merge_memories': {'ids', 'content'},
                          'create_edge': {'source_id', 'target_id', 'relation'},
                          'remove_edge': {'source_id', 'target_id', 'relation'}}
                if op not in fields or set(operation) != fields[op] | {'op'}:
                    raise ValueError('invalid operation fields')
                keys = operation.get('ids', [operation['id']] if 'id' in operation else [])
                if op in ('create_edge', 'remove_edge'):
                    keys = [operation['source_id'], operation['target_id']]
                if not isinstance(keys, list) or len(keys) > 16 or (op == 'merge_memories' and len(set(keys)) < 2):
                    raise ValueError('invalid ids')
                for key in keys:
                    text(key, 64)
                    if not self.db.execute('SELECT 1 FROM ltms_memories WHERE id=? AND archived=0', (key,)).fetchone():
                        raise ValueError('memory not found or archived')
                now = time.time()
                key = operation.get('id')
                if op in ('create_memory', 'merge_memories'):
                    if self.db.execute('SELECT count(*) FROM ltms_memories').fetchone()[0] >= 4096:
                        raise ValueError('memory capacity reached')
                    key = uuid.uuid4().hex
                    self.db.execute('INSERT INTO ltms_memories(id,content,source,updated_at) VALUES(?,?,?,?)',
                                    (key, text(operation['content']), source, now))
                    if op == 'merge_memories':
                        # Preserve connections, then archive the summarized inputs.
                        for old in keys:
                            for edge in self.db.execute('SELECT * FROM ltms_edges WHERE source_id=? OR target_id=?', (old, old)).fetchall():
                                a = key if edge['source_id'] in keys else edge['source_id']
                                b = key if edge['target_id'] in keys else edge['target_id']
                                if a != b:
                                    self.db.execute('INSERT OR IGNORE INTO ltms_edges VALUES(?,?,?)', (a,b,edge['relation']))
                            self.db.execute('UPDATE ltms_memories SET archived=1 WHERE id=?', (old,))
                elif op == 'update_memory':
                    self.db.execute('UPDATE ltms_memories SET content=?, source=?, updated_at=?, embedding=NULL, embedding_model=NULL WHERE id=?',
                                    (text(operation['content']), source, now, key))
                elif op == 'archive_memory':
                    self.db.execute('UPDATE ltms_memories SET archived=1 WHERE id=?', (key,))
                elif op == 'forget_memory':
                    self.db.execute('DELETE FROM ltms_memories WHERE id=?', (key,))
                else:
                    args = (operation['source_id'], operation['target_id'], text(operation['relation'], 80))
                    if args[0] == args[1]:
                        raise ValueError('self edge')
                    if op == 'create_edge':
                        if self.db.execute('SELECT count(*) FROM ltms_edges').fetchone()[0] >= 16384:
                            raise ValueError('edge capacity reached')
                        self.db.execute('INSERT OR IGNORE INTO ltms_edges VALUES(?,?,?)', args)
                    else:
                        self.db.execute('DELETE FROM ltms_edges WHERE source_id=? AND target_id=? AND relation=?', args)
                results.append(dict(op=op, id=key, status='completed'))
            if job_id is not None:
                self.db.execute("DELETE FROM ltms_jobs WHERE id=?", (job_id,))
        return results

    def set_embedding(self, key, content, embedding, model):
        vector(embedding)
        with self.lock, self.db:
            self.db.execute('UPDATE ltms_memories SET embedding=?, embedding_model=? WHERE id=? AND content=? AND archived=0',
                            (json.dumps(embedding), model, key, content))
