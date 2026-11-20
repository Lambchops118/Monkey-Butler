import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from butler.debug_dashboard.memory_graph import read_memory_graph
from butler.debug_dashboard.server import DebugHTTPServer, DebugSnapshotService
from butler.storage import connect_database


class MemoryGraphTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'fixture.sqlite3'
        self.db = connect_database(self.path)
        with self.db:
            for key, content, archived, updated in [('a','Warm lighting',0,3),('b','Arriving home',0,2),('c','Old preference',1,1),('d','Unconnected memory',0,0)]:
                self.db.execute('INSERT INTO ltms_memories(id,content,source,archived,updated_at) VALUES(?,?,?,?,?)',
                                (key,content,'{"user":"fixture evidence"}',archived,updated))
            self.db.executemany('INSERT INTO ltms_edges VALUES(?,?,?)', [('a','b','applies_when'),('a','c','supersedes')])

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_nodes_edges_archives_and_isolates(self):
        result=read_memory_graph(self.path)
        self.assertTrue(result['ok'])
        self.assertEqual({'a','b','d'}, {n['id'] for n in result['nodes']})
        self.assertEqual([dict(source_id='a',target_id='b',relation='applies_when')],result['edges'])
        self.assertEqual(4,len(read_memory_graph(self.path,archived=True)['nodes']))
        self.assertNotIn('embedding_model',result['nodes'][0])

    def test_bounded_graph_reports_omission_without_dangling_edges(self):
        result=read_memory_graph(self.path,limit=1)
        self.assertEqual(1,len(result['nodes']))
        self.assertEqual([],result['edges'])
        self.assertEqual(2,result['coverage']['omitted_nodes'])
        self.assertEqual(1,result['coverage']['omitted_edges'])
        with self.assertRaises(ValueError):
            read_memory_graph(self.path,limit=501)

    def test_projection_does_not_write_and_handles_empty_and_deleted(self):
        before=self.db.total_changes
        read_memory_graph(self.path)
        self.assertEqual(before,self.db.total_changes)
        with self.db:
            self.db.execute("DELETE FROM ltms_memories WHERE id='a'")
        self.assertEqual([],read_memory_graph(self.path)['edges'])
        with self.db:
            self.db.execute('DELETE FROM ltms_memories')
        self.assertEqual(0,read_memory_graph(self.path)['coverage']['total_nodes'])

    def test_missing_database_is_not_created_and_old_schema_not_migrated(self):
        missing=Path(self.temp.name)/'missing.sqlite3'
        self.assertFalse(read_memory_graph(missing)['ok'])
        self.assertFalse(missing.exists())
        import sqlite3
        old=Path(self.temp.name)/'old.sqlite3'
        connection=sqlite3.connect(old)
        connection.close()
        self.assertFalse(read_memory_graph(old)['ok'])
        connection=sqlite3.connect(old)
        try:
            self.assertEqual([],connection.execute('SELECT name FROM sqlite_master').fetchall())
        finally:
            connection.close()

    def test_http_routes_static_assets_and_capped_limit(self):
        service=DebugSnapshotService(memory_db=self.path)
        server=DebugHTTPServer(('127.0.0.1',0),service)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            base=f'http://127.0.0.1:{server.server_port}'
            for route, content_type in [('/memory','text/html'),('/memory.js','application/javascript'),('/memory.css','text/css')]:
                with urllib.request.urlopen(base+route,timeout=3) as response:
                    self.assertIn(content_type,response.headers['Content-Type'])
                    self.assertIn("default-src 'self'",response.headers['Content-Security-Policy'])
            with urllib.request.urlopen(base+'/api/ltms-graph?archived=1&limit=999999',timeout=3) as response:
                result=json.load(response)
            self.assertEqual(4,len(result['nodes']))
            self.assertEqual(2,len(result['edges']))
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)


if __name__ == '__main__':
    unittest.main()
