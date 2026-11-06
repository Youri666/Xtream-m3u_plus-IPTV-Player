"""Catalogue workers always release busy state through queued completion data."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest
from PyQt5.QtCore import QObject, QThread, QThreadPool, pyqtSlot
from PyQt5.QtWidgets import QApplication
from iptv_player.provider.workers import FetchDataWorker


class Receiver(QObject):
    def __init__(self):
        super().__init__()
        self.results = []

    @pyqtSlot(str, bool, object)
    def completed(self, account, success, fetched_at):
        self.results.append((account, success, fetched_at, QThread.currentThread()))


class CatalogCompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def worker(self):
        parent = SimpleNamespace(current_user_agent='Agent', cache_file='cache.json',
            legacy_cache_file='legacy.json', active_account_id='A', favorites_file='favorites.json')
        worker = FetchDataWorker('https://example.test', 'user', 'secret', 'live', 'movie', 'series', parent)
        cache = {'_metadata': {'account_key': worker._cache_account_key(), 'fetched_at': 1700000000}}
        for kind in ('LIVE', 'Movies', 'Series'):
            cache[kind], cache[kind+' categories'] = [], []
        return worker, cache

    def test_completion_reaches_gui_thread_with_original_cache_timestamp(self):
        worker, cache = self.worker()
        receiver = Receiver()
        worker.signals.completed.connect(receiver.completed)
        pool = QThreadPool()
        with patch('iptv_player.provider.workers.path.isfile', return_value=True), patch(
                'iptv_player.provider.workers.load_catalog_cache', return_value=cache), patch(
                'iptv_player.provider.workers.catalog_cache_is_fresh', return_value=True), patch(
                'iptv_player.provider.workers.read_json_mapping', return_value={}), patch(
                'iptv_player.provider.workers.prepare_catalog_entries'):
            pool.start(worker)
            self.assertTrue(pool.waitForDone(3000))
            self.app.processEvents()
        self.assertEqual(receiver.results, [('A', True, 1700000000, self.app.thread())])

    def test_preparation_failure_still_emits_one_completion(self):
        worker, cache = self.worker()
        done, failed = Mock(), Mock()
        worker.signals.completed.connect(done)
        worker.signals.error.connect(failed)
        with patch('iptv_player.provider.workers.path.isfile', return_value=True), patch(
                'iptv_player.provider.workers.load_catalog_cache', return_value=cache), patch(
                'iptv_player.provider.workers.catalog_cache_is_fresh', return_value=True), patch(
                'iptv_player.provider.workers.read_json_mapping', return_value={}), patch(
                'iptv_player.provider.workers.prepare_catalog_entries', side_effect=ValueError('test failure')):
            worker.run()
        failed.assert_called_once()
        done.assert_called_once_with('A', False, 1700000000)
