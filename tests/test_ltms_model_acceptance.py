"""Opt-in local-model acceptance; temporary DB, no device or control calls."""
import os
import tempfile
import time
import unittest
from pathlib import Path

import requests

from butler.ltms import local_server
from butler.ltms.service import LocalModel, Service
from butler.ltms.store import Store


@unittest.skipUnless(os.getenv('BUTLER_LTMS_LIVE_MODEL_TEST') == '1', 'opt-in local model test')
class LocalAcceptance(unittest.TestCase):
    def test_learn_recall_change_and_forget(self):
        model = LocalModel()
        server = local_server.start(model.url)
        store = None
        temporary = tempfile.TemporaryDirectory()
        try:
            for _ in range(60):
                try:
                    requests.get(model.url + '/api/tags', timeout=1).raise_for_status()
                    break
                except requests.RequestException:
                    time.sleep(.5)
            if True:
                store = Store(Path(temporary.name) / 'acceptance.sqlite3')
                service = Service(store, model)
                service.submit(dict(source='owner_message', user='I prefer warm living room lights when I get home after dark.'))
                service.drain()
                service.process_one()
                self.assertTrue(store.memories(), service.error)
                service.embed_pending()
                self.assertIsNotNone(store.memories()[0]['embedding'], service.error)
                self.assertIn('warm', service.recall('How do I like the lighting when arriving home?').lower())
                service.submit(dict(source='owner_message', user='My preference has changed: I now prefer cool living room lights when arriving home after dark. Replace the old preference.'))
                service.drain(); service.process_one()
                self.assertIsNone(service.error)
                self.assertIn('cool', ' '.join(r['content'] for r in store.memories()).lower())
                service.submit(dict(source='owner_message', user='Forget all my lighting preferences. Delete those memories now.'))
                service.drain(); service.process_one()
                self.assertIsNone(service.error)
                self.assertFalse(store.memories())
                store.close(); store = None
        finally:
            if store is not None:
                store.close()
            temporary.cleanup()
            if server is not None:
                server.terminate()
                server.wait(timeout=10)


if __name__ == '__main__':
    unittest.main()
