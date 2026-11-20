import json
import tempfile
import unittest
from pathlib import Path

from butler.ltms.store import Store
from butler.ltms.service import Service
from butler.memory.store import MemoryStore


class Model:
    embedding_model = 'fixture-v1'
    def embed(self, content):
        return [1., 0.]
    def extract(self, payload, related, edges):
        return [{'op': 'create_memory', 'content': 'User explicitly prefers warm lights after dark.'}]


class LTMSTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'test.sqlite3'
        self.store = Store(self.path)
    def tearDown(self):
        self.store.close()
        self.temp.cleanup()
    def create(self, content):
        return self.store.apply([dict(op='create_memory', content=content)], 'user explicitly said so')[0]['id']
    def test_atomic_batch_rejects_unknown_fields_and_rolls_back(self):
        with self.assertRaises(ValueError):
            self.store.apply([dict(op='create_memory', content='one'), dict(op='create_memory', content='two', sql='bad')], 'evidence')
        self.assertEqual([], self.store.memories())
    def test_merge_preserves_external_edges_and_hides_archived_inputs(self):
        a,b,c = [self.create(x) for x in ('likes lamps', 'likes warm lamps', 'living room')]
        self.store.apply([dict(op='create_edge', source_id=a,target_id=c,relation='in')], 'evidence')
        merged = self.store.apply([dict(op='merge_memories',ids=[a,b],content='likes warm lamps in living room')], 'evidence')[0]['id']
        edges = self.store.traverse_graph([merged])
        self.assertEqual(c, edges[0]['target_id'])
        self.assertEqual(2,len(self.store.memories()))
        self.assertEqual([], self.store.traverse_graph([a]))
    def test_forget_cascades_edges(self):
        a,b = self.create('one'), self.create('two')
        self.store.apply([dict(op='create_edge',source_id=a,target_id=b,relation='related')], 'evidence')
        self.store.apply([dict(op='forget_memory',id=a)], 'forget')
        self.assertEqual([],self.store.traverse_graph([b]))
        self.assertIsNone(self.store.db.execute('SELECT * FROM ltms_memories WHERE id=?',(a,)).fetchone())
    def test_embedding_version_update_and_stale_write(self):
        a=self.create('warm lights')
        self.store.set_embedding(a,'warm lights',[1.,0.],'v1')
        self.assertEqual(a,self.store.search_memories('unrelated',[1.,0.],'v1')[0]['id'])
        self.assertEqual([],self.store.search_memories('unrelated',[1.,0.],'v2'))
        self.store.apply([dict(op='update_memory',id=a,content='cool lamps')],'changed')
        self.store.set_embedding(a,'warm lights',[1.,0.],'v1')
        self.assertEqual([],self.store.search_memories('unrelated',[1.,0.],'v1'))
    def test_durable_job_reopen_and_atomic_completion(self):
        service=Service(self.store,Model())
        service.submit(dict(user='I prefer warm lights'), 'turn1')
        service.drain()
        self.store.close()
        self.store=Store(self.path)
        service=Service(self.store,Model())
        self.assertTrue(service.process_one())
        self.assertFalse(service.process_one())
        self.assertEqual(1,len(self.store.memories()))
    def test_failed_model_retries_without_memory_write(self):
        class Broken(Model):
            def extract(self,*args):
                raise TimeoutError()
        service=Service(self.store,Broken())
        service.submit(dict(user='something'))
        service.drain(); service.process_one()
        self.assertEqual([],self.store.memories())
        row=self.store.db.execute('SELECT * FROM ltms_jobs').fetchone()
        self.assertEqual(1,row['attempts'])
        self.assertEqual('pending',row['status'])
    def test_lexical_fallback_and_bounded_prompt(self):
        self.create('User likes warm lights')
        class Broken(Model):
            def embed(self,*args):
                raise TimeoutError()
        service=Service(self.store,Broken())
        result=service.recall('warm lights')
        self.assertIn('User likes warm lights',result)
        self.assertIn('lexical_fallback',result)
    def test_history_and_conversation_clear_isolation(self):
        self.create('likes lights')
        history=MemoryStore(self.path)
        try:
            history.record_turn('owner','hello','hi')
            self.assertTrue(history.get_recent_messages('owner'))
            history.clear_session('owner')
            self.assertEqual(1,len(self.store.memories()))
        finally:
            history.close()
    def test_archived_nodes_cannot_be_mutated_or_related(self):
        a=self.create('lamp preference')
        self.store.apply([dict(op='archive_memory',id=a)], 'old')
        with self.assertRaises(ValueError):
            self.store.apply([dict(op='update_memory',id=a,content='changed')], 'evidence')
        self.assertEqual([], self.store.search_memories('lamp'))
    def test_retired_fact_tools_absent_and_history_still_readable(self):
        from unittest.mock import Mock
        from butler.agent import runtime
        client=Mock()
        client.list_tools.return_value=[]
        definitions=runtime._resource_tool_definitions()
        self.assertNotIn('memory_admin', [d.get('name') for d in definitions])
    def test_source_age_changes_do_not_enqueue_duplicate_weather(self):
        from unittest.mock import patch
        service=Service(self.store,Model())
        observation=dict(subject='home',kind='observation',values={'temp':40},age_seconds=1)
        with patch('butler.dis.service.read_devices',return_value={}), patch('butler.wcs.service.read_context',return_value={'observations':[observation]}):
            service.observe_sources()
            observation['age_seconds']=10
            service.observe_sources()
        self.assertEqual(1,service.inbox.qsize())
    def test_dis_cache_is_never_read_and_direct_device_input_rejected(self):
        from unittest.mock import patch
        service=Service(self.store,Model())
        with patch('butler.dis.service.read_devices',side_effect=AssertionError('DIS must not be sampled')), patch('butler.wcs.service.read_context',return_value={}):
            service.observe_sources()
        self.assertFalse(service.submit(dict(source='dis:lamp',data={'power':True})))
        self.assertEqual(0,service.inbox.qsize())
        self.assertTrue(service.submit(dict(source='owner_message',user='I prefer warm lighting')))

    def test_old_device_queue_is_discarded_without_deleting_memories(self):
        memory_id=self.create('existing memory stays')
        with self.store.db:
            self.store.db.executemany('INSERT INTO ltms_jobs(id,payload,status,created_at) VALUES(?,?,?,0)',[
                ('old-dis',json.dumps({'source':'dis:lamp'}),'pending'),
                ('failed-dis',json.dumps({'source':'dis:waterer'}),'failed'),
                ('owner',json.dumps({'source':'owner_message','user':'I prefer lamps'}),'pending')])
        service=Service(self.store,Model())
        service.discard_device_jobs()
        self.assertEqual(['owner'],[r['id'] for r in self.store.db.execute('SELECT id FROM ltms_jobs')])
        self.assertEqual(memory_id,self.store.memories()[0]['id'])

    def test_old_pending_device_job_never_reaches_model(self):
        from unittest.mock import Mock
        model=Mock()
        with self.store.db:
            self.store.db.execute('INSERT INTO ltms_jobs(id,payload,created_at) VALUES(?,?,0)',('old',json.dumps({'source':'dis:lamp'})))
        service=Service(self.store,model)
        self.assertTrue(service.process_one())
        model.extract.assert_not_called()
        self.assertEqual(0,self.store.db.execute('SELECT count(*) FROM ltms_jobs').fetchone()[0])

    def test_queue_full_does_not_wait(self):
        service=Service(self.store,Model())
        for i in range(256):
            self.assertTrue(service.submit(dict(user=str(i))))
        self.assertFalse(service.submit(dict(user='overflow')))
        self.assertEqual(1,service.dropped)


if __name__ == '__main__':
    unittest.main()

