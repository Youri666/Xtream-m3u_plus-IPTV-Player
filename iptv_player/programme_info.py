"""Provider-backed programme descriptions shared with the isolated player."""
from collections import OrderedDict
from datetime import datetime
from html import escape
import time
from types import SimpleNamespace

from PyQt5.QtCore import QObject

from iptv_player.provider.epg import apply_epg_offset
from iptv_player.provider.workers import EPGWorker, MovieInfoFetcher, SeriesInfoFetcher


def programme_key(history):
    kind = history.get("type")
    item_id = history.get("series_id") if kind == "Series" else history.get("stream_id")
    if kind not in ("LIVE", "Movies", "Series") or not item_id:
        return None
    return str(history.get("account_id", "")), kind, str(item_id)


def episode_summary(episode):
    """Read an episode synopsis consistently in the main window and player."""
    if not isinstance(episode, dict):
        return ""
    info = episode.get("info")
    if not isinstance(info, dict):
        return ""
    return info.get("plot") or info.get("description") or ""


def programme_payload(kind, data, history, offset=0):
    """Keep descriptions as plain text and distinguish episode and series plots."""
    result = {"kind": kind, "title": history.get("title", ""), "summary": ""}
    if kind == "LIVE":
        result["entries"] = [
            {"title": entry.get("program_name", ""), "summary": entry.get("description", ""),
             "start": entry["start_time"].timestamp(), "end": entry["stop_time"].timestamp()}
            for entry in apply_epg_offset(data, offset)
        ]
    elif kind == "Movies":
        result["summary"] = data.get("description") or data.get("plot") or ""
    else:
        episodes = data.get("episodes", {})
        groups = episodes.values() if isinstance(episodes, dict) else [episodes]
        for group in groups:
            if not isinstance(group, list):
                continue
            for episode in group:
                if not isinstance(episode, dict):
                    continue
                if str(episode.get("id", "")) == str(history.get("stream_id", "")):
                    result["summary"] = episode_summary(episode)
                    break
        if not result["summary"]:
            info = data.get("info") or {}
            result["summary"] = (info.get("plot") or "") if isinstance(info, dict) else ""
            if result["summary"]:
                result["subtitle"] = "Series synopsis (episode summary unavailable)"
    return result


def programme_html(payload, now=None):
    """Select the current EPG programme locally, escaping all provider text."""
    now = time.time() if now is None else now
    title, summary = payload.get("title", ""), payload.get("summary", "")
    subtitle = payload.get("subtitle", "")
    if payload.get("kind") == "LIVE":
        current = next((entry for entry in payload.get("entries", [])
                        if entry["start"] <= now < entry["end"]), None)
        if current:
            title, summary = current["title"], current["summary"]
            subtitle = "{} – {}".format(*(datetime.fromtimestamp(current[key]).strftime("%H:%M")
                                         for key in ("start", "end")))
        else:
            summary = "No EPG information available for the current programme."
    summary = payload.get("message") or summary or "No summary available."
    return (f"<h3>{escape(str(title))}</h3><p>{escape(str(subtitle))}</p>"
            f"<p>{escape(str(summary)).replace(chr(10), '<br>')}</p>")


class ProgrammeInfoService(QObject):
    """Reuse existing workers, coalesce requests and isolate account snapshots."""
    def __init__(self, threadpool, deliver, parent=None):
        super().__init__(parent)
        self.threadpool, self.deliver = threadpool, deliver
        self.accounts, self.cache, self.pending = {}, OrderedDict(), {}

    def register(self, account_id, server, username, password, user_agent, offset=0):
        context = (server, username, password, user_agent, offset)
        previous = self.accounts.get(str(account_id))
        if previous is not None and previous != context:
            for key in list(self.cache):
                if key[0] == str(account_id):
                    self.cache.pop(key)
        self.accounts[str(account_id)] = context

    def seed(self, account_id, kind, item_id, data):
        key = str(account_id), kind, str(item_id)
        self.cache[key] = (time.monotonic(), data)
        self.cache.move_to_end(key)
        while len(self.cache) > 128:
            self.cache.popitem(last=False)

    def _reply(self, request, payload):
        self.deliver({"command": "programme_info", "request_id": request.get("request_id"),
                      "generation": request.get("generation"), "payload": payload})

    def request(self, request):
        history = request.get("history") or {}
        key = programme_key(history)
        context = self.accounts.get(key[0]) if key else None
        if context is None:
            self._reply(request, {"message": "Programme information unavailable."})
            return
        cached = self.cache.get(key)
        if cached and (key[1] != "LIVE" or time.monotonic() - cached[0] < 30):
            self._reply(request, programme_payload(key[1], cached[1], history, context[4]))
            return
        pending_key = key, context
        if pending_key in self.pending:
            self.pending[pending_key].append(request)
            return
        self.pending[pending_key] = [request]
        server, username, password, user_agent, _offset = context
        owner = SimpleNamespace(current_user_agent=user_agent)
        if key[1] == "LIVE":
            worker = EPGWorker(server, username, password, key[2], owner)
            worker.signals.finished.connect(lambda data: self._finished(pending_key, data))
        elif key[1] == "Movies":
            worker = MovieInfoFetcher(server, username, password, key[2], owner)
            worker.signals.finished.connect(lambda info, _data: self._finished(pending_key, info))
        else:
            worker = SeriesInfoFetcher(server, username, password, key[2], False, owner,
                                       hide_error_details=True)
            worker.signals.finished.connect(lambda data, _show: self._finished(pending_key, data))
        worker.signals.error.connect(lambda _error: self._finished(pending_key, None))
        self.threadpool.start(worker)

    def _finished(self, pending_key, data):
        key, context = pending_key
        if data is not None and self.accounts.get(key[0]) == context:
            self.seed(*key, data)
        for request in self.pending.pop(pending_key, []):
            if data is None or self.accounts.get(key[0]) != context:
                self._reply(request, {"message": "Unable to load programme information."})
            else:
                self._reply(request, programme_payload(key[1], data,
                            request.get("history") or {}, context[4]))
