"""Catalogue workers always release busy state through queued completion data."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest
import requests
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

    def test_provider_outage_and_auth_rejection_stop_after_account_request(self):
        for failure, cache_available, expected in (
            (requests.Timeout(), False, "Provider is unreachable"),
            (requests.Timeout(), True, "Cached:"),
            (None, False, "Provider rejected the account credentials"),
        ):
            with self.subTest(failure=failure, cache_available=cache_available):
                worker, cache = self.worker()
                worker.force_provider_refresh = True
                outcome, finished, done = Mock(), Mock(), Mock()
                worker.signals.outcome.connect(outcome)
                worker.signals.finished.connect(finished)
                worker.signals.completed.connect(done)
                with patch('iptv_player.provider.workers.path.isfile', return_value=cache_available), patch(
                        'iptv_player.provider.workers.load_catalog_cache', return_value=cache), patch(
                        'iptv_player.provider.workers.XtreamClient') as client, patch(
                        'iptv_player.provider.workers.read_json_mapping', return_value={}), patch(
                        'iptv_player.provider.workers.prepare_catalog_entries'), patch(
                        'iptv_player.provider.workers.write_catalog_cache') as write_cache:
                    request = client.return_value.get_json
                    request.side_effect = failure
                    request.return_value = {'user_info': {'auth': 0}}
                    worker.run()
                    request.assert_called_once_with()
                    write_cache.assert_not_called()
                self.assertIn(expected, outcome.call_args.args[0])
                self.assertEqual(outcome.call_args.args[1], 'warning' if cache_available else 'error')
                self.assertEqual(finished.call_count, int(cache_available))
                done.assert_called_once_with('A', False, 1700000000 if cache_available else 0)

    def test_partial_catalog_reports_cached_and_missing_sections(self):
        worker, cache = self.worker()
        worker.force_provider_refresh = True
        del cache['Series']
        outcome, finished = Mock(), Mock()
        worker.signals.outcome.connect(outcome)
        worker.signals.finished.connect(finished)
        with patch('iptv_player.provider.workers.path.isfile', return_value=True), patch(
                'iptv_player.provider.workers.load_catalog_cache', return_value=cache), patch(
                'iptv_player.provider.workers.XtreamClient') as client, patch(
                'iptv_player.provider.workers.read_json_mapping', return_value={}), patch(
                'iptv_player.provider.workers.prepare_catalog_entries'), patch(
                'iptv_player.provider.workers.write_catalog_cache') as write_cache:
            client.return_value.get_json.side_effect = [
                {'user_info': {'auth': 1}}, [], [], [], [{'name': 'New channel'}],
                requests.Timeout(), requests.Timeout(),
            ]
            worker.run()
            write_cache.assert_not_called()
        self.assertEqual(finished.call_args.args[2]['LIVE'], [{'name': 'New channel'}])
        outcome.assert_called_once_with(
            'Catalog update incomplete. Cached: Movies streams. Missing: Series streams.', 'warning')
