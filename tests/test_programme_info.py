"""Programme lookups remain account-bound and reuse asynchronous provider workers."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from datetime import datetime, timedelta
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from PyQt5.QtWidgets import QApplication
from iptv_player.programme_info import ProgrammeInfoService, programme_payload, programme_html


class ProgrammeInformationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def service(self):
        pool, deliver = Mock(), Mock()
        service = ProgrammeInfoService(pool, deliver)
        service.register("A", "https://a.test", "user", "password", "Agent A", 60)
        return service, pool, deliver

    def request(self, kind="Movies", item_id="1", episode="11", token="request-1", account="A"):
        return {"request_id": token, "generation": 2, "history": {
            "account_id": account, "type": kind, "stream_id": episode if kind == "Series" else item_id,
            "series_id": item_id, "title": "Current title"}}

    def test_cached_movie_summary_needs_no_new_request(self):
        service, pool, deliver = self.service()
        service.seed("A", "Movies", "1", {"description": "Movie plot"})
        service.request(self.request())
        pool.start.assert_not_called()
        self.assertEqual(deliver.call_args.args[0]["payload"]["summary"], "Movie plot")

    def test_simultaneous_episode_requests_share_one_series_worker(self):
        service, pool, deliver = self.service()
        service.request(self.request("Series"))
        service.request(self.request("Series", episode="12", token="request-2"))
        pool.start.assert_called_once()
        worker = pool.start.call_args.args[0]
        worker.signals.finished.emit({"episodes": {"1": [
            {"id": 11, "info": {"plot": "Episode one"}},
            {"id": 12, "info": {"plot": "Episode two"}}]}}, False)
        self.assertEqual([call.args[0]["payload"]["summary"] for call in deliver.call_args_list],
                         ["Episode one", "Episode two"])

    def test_worker_retains_origin_account_after_another_is_registered(self):
        service, pool, deliver = self.service()
        service.request(self.request())
        worker = pool.start.call_args.args[0]
        service.register("B", "https://b.test", "other", "secret", "Agent B")
        self.assertEqual(worker.server, "https://a.test")
        self.assertEqual(worker.user_agent, "Agent A")
        worker.signals.finished.emit({"description": "Original account"}, {})
        self.assertEqual(deliver.call_args.args[0]["payload"]["summary"], "Original account")

    def test_changed_origin_credentials_invalidate_pending_response(self):
        service, pool, deliver = self.service()
        service.request(self.request())
        worker = pool.start.call_args.args[0]
        service.register("A", "https://new.test", "new", "new", "new")
        worker.signals.finished.emit({"description": "Old result"}, {})
        self.assertIn("message", deliver.call_args.args[0]["payload"])
        self.assertFalse(service.cache)

    def test_provider_failure_returns_a_retryable_message(self):
        service, pool, deliver = self.service()
        service.request(self.request())
        pool.start.call_args.args[0].signals.error.emit("private provider failure")
        response = deliver.call_args.args[0]
        self.assertIn("Unable", response["payload"]["message"])
        self.assertNotIn("private", str(response))
        self.assertFalse(service.pending)

    def test_live_cache_expires_and_offset_is_applied_once(self):
        service, pool, deliver = self.service()
        start = datetime(2026, 1, 1, 12)
        entries = [{"start_time": start, "stop_time": start + timedelta(hours=1),
                    "program_name": "News", "description": "Headlines"}]
        with patch("iptv_player.programme_info.time.monotonic", return_value=100):
            service.seed("A", "LIVE", "1", entries)
            service.request(self.request("LIVE"))
        payload = deliver.call_args.args[0]["payload"]
        self.assertEqual(payload["entries"][0]["start"], (start + timedelta(hours=1)).timestamp())
        with patch("iptv_player.programme_info.time.monotonic", return_value=131):
            service.request(self.request("LIVE"))
        pool.start.assert_called_once()

    def test_programme_boundary_updates_without_a_network_request(self):
        payload = {"kind": "LIVE", "entries": [
            {"start": 0, "end": 10, "title": "First", "summary": "One"},
            {"start": 10, "end": 20, "title": "Second", "summary": "Two"}]}
        self.assertIn("First", programme_html(payload, 9))
        self.assertIn("Second", programme_html(payload, 10))
        self.assertIn("No EPG", programme_html(payload, 20))

    def test_episode_fallback_is_explicit_and_provider_html_is_escaped(self):
        payload = programme_payload("Series", {"info": {"plot": "<script>hello</script>"}},
                                    {"stream_id": "11", "title": "<Episode>"})
        markup = programme_html(payload)
        self.assertIn("Series synopsis", markup)
        self.assertIn("&lt;script&gt;", markup)
        self.assertNotIn("<script>", markup)

    def test_unknown_account_cannot_trigger_provider_request(self):
        service, pool, deliver = self.service()
        service.request(self.request(account="missing"))
        pool.start.assert_not_called()
        self.assertIn("unavailable", deliver.call_args.args[0]["payload"]["message"])
