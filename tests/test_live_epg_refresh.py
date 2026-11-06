"""Live schedules update locally and share boundary-triggered provider refreshes."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from unittest.mock import Mock, patch
import unittest
from PyQt5.QtWidgets import QApplication, QWidget, QTreeWidget
from iptv_player.programme_info import EpgRefreshState
from iptv_player.ui.info_panels import LiveInfoBox
from iptv_player.ui.live_epg import LiveEpgController


class EpgRefreshPolicyTests(unittest.TestCase):
    def test_valid_epg_has_no_periodic_network_refresh(self):
        state = EpgRefreshState()
        payload = {'entries': [{'end': 200}, {'end': 300}]}
        state.begin(0)
        state.received(payload, 100)
        self.assertFalse(state.due(payload, 150, 10000))
        self.assertTrue(state.due(payload, 200, 10001))
        state.begin(10001)
        self.assertFalse(state.due(payload, 201, 10002))

    def test_empty_or_failed_epg_retries_only_after_a_minute(self):
        for payload in ({'entries': []}, {'message': 'Failed'}):
            with self.subTest(payload=payload):
                state = EpgRefreshState()
                state.begin(0)
                state.received(payload, 100)
                self.assertFalse(state.due(payload, 159, 59))
                self.assertTrue(state.due(payload, 160, 60))

    def test_failed_boundary_request_cannot_loop_each_second(self):
        state = EpgRefreshState()
        payload = {'entries': [{'end': 200}, {'end': 300}]}
        state.received(payload, 100)
        self.assertTrue(state.due(payload, 200, 0))
        state.begin(0)
        state.received({'message': 'Failed'}, 200)
        self.assertFalse(state.due(payload, 201, 1))
        self.assertTrue(state.due(payload, 260, 60))


class LiveEpgControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def window(self):
        window = QWidget()
        window.active_account_id = 'A'
        window._info_request_generation = {'LIVE': 1}
        window._is_current_info_request = lambda kind, generation: generation == window._info_request_generation[kind]
        window.server, window.username, window.password = 'https://a.test', 'user', 'secret'
        window.current_user_agent, window.epg_offset_minutes = 'Agent A', 0
        window.set_progress_bar, window.on_epg_fetch_error = Mock(), Mock()
        service = Mock()
        window._get_programme_service = lambda: service
        window.live_info_box = QWidget(window)
        window.live_info_box.live_EPG_info = QTreeWidget(window.live_info_box)
        window.live_info_box.live_EPG_info.setColumnCount(4)
        window.live_info_box.add_epg_description = lambda item, description: LiveInfoBox.add_epg_description(window.live_info_box, item, description)
        window.show()
        self.app.processEvents()
        controller = LiveEpgController(window)
        controller.timer.stop()
        return window, controller, service

    def payload(self):
        return {'kind': 'LIVE', 'entries': [
            {'start': 50, 'end': 100, 'title': 'First', 'summary': 'First summary'},
            {'start': 100, 'end': 200, 'title': 'Second', 'summary': 'Second summary'}]}

    def test_ended_programme_is_removed_and_refresh_requested_once(self):
        window, controller, service = self.window()
        with patch('iptv_player.ui.live_epg.time.time', return_value=90):
            controller.select('10', 1)
            service.request.call_args.kwargs['callback'](self.payload())
            tree = window.live_info_box.live_EPG_info
            second = tree.topLevelItem(1)
            second.setExpanded(True)
            controller.tick()
            self.assertIs(tree.topLevelItem(1), second)
            self.assertEqual(service.request.call_count, 1)
        with patch('iptv_player.ui.live_epg.time.time', return_value=100):
            controller.tick()
            self.assertEqual(tree.topLevelItemCount(), 1)
            self.assertEqual(tree.topLevelItem(0).text(3), 'Second')
            self.assertTrue(tree.topLevelItem(0).isExpanded())
            self.assertEqual(service.request.call_count, 2)
            controller.tick()
            self.assertEqual(service.request.call_count, 2)
        window.close()

    def test_late_channel_or_account_response_is_ignored(self):
        window, controller, service = self.window()
        controller.select('10', 1)
        old_callback = service.request.call_args.kwargs['callback']
        window._info_request_generation['LIVE'] = 2
        controller.select('20', 2)
        old_callback(self.payload())
        self.assertIsNone(controller.payload)
        callback = service.request.call_args.kwargs['callback']
        window.active_account_id = 'B'
        callback(self.payload())
        self.assertIsNone(controller.payload)
        window.close()

    def test_hidden_epg_does_not_request_updates(self):
        window, controller, service = self.window()
        controller.select('10', 1)
        service.request.call_args.kwargs['callback']({'entries': []})
        service.request.reset_mock()
        window.live_info_box.hide()
        with patch('iptv_player.programme_info.time.monotonic', return_value=10**10):
            controller.tick()
        service.request.assert_not_called()
        window.close()
