#!/usr/bin/env python3
"""
Merged Chat relay — one process does all the network I/O, every open page is a
thin client.

Why this exists: running the overlay as both an OBS Browser source and an OBS
custom browser dock used to mean two independent pages, each polling YouTube
(double quota) and each trying to claim the same Twitch EventSub subscriptions
(the second one gets a 409). An in-browser localStorage bus was tried first, but
OBS does not propagate storage writes between a Browser source and a dock while
both are running, so neither page could see the other.

So the fan-out moves out of the browser. This process:

  * holds ONE anonymous Twitch IRC connection (all channels, one socket)
  * polls each YouTube live chat ONCE, with API-key failover on quota
  * holds ONE Twitch EventSub session for alerts / channel point redeems
  * re-broadcasts everything to every connected page over a local WebSocket

Pages stay dumb: they receive the same raw payloads they would have fetched
themselves and render them with their existing code, so every view shows
byte-identical chat.

  Setup:   pip install websockets
           copy app.properties.example -> app.properties and fill it in
  Run:     python relay.py
  Then:    set RELAY_URL in merged-chat.html's CONFIG (default already matches)

Nothing is exposed off this machine: the listener binds 127.0.0.1 by default.
"""

import asyncio
import calendar
import json
import random
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from contextlib import AsyncExitStack
from pathlib import Path

try:
    import websockets
except ImportError:
    sys.exit("Missing dependency. Run:  pip install websockets")

# websockets renamed the client/server entry points in v10+; support both so a
# system-packaged older version still works.
try:
    from websockets.asyncio.client import connect as ws_connect
    from websockets.asyncio.server import serve as ws_serve
except ImportError:                                   # pragma: no cover
    from websockets import connect as ws_connect      # type: ignore
    from websockets import serve as ws_serve          # type: ignore


# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent
# Optional argument: an alternate properties file (handy for a second channel
# setup, or for testing without touching the real one).
PROPS = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else HERE / "app.properties"
EXAMPLE = HERE / "app.properties.example"


def load_properties(path):
    """Minimal java.util.Properties reader: key=value, # or ! comments."""
    if not path.exists():
        sys.exit(
            "Missing {}\n"
            "Copy {} to app.properties and fill in your values.".format(
                path.name, EXAMPLE.name))
    out = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line[0] in "#!":
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


class Config:
    def __init__(self, p):
        self.p = p

    def get(self, key, default=""):
        return self.p.get(key, default)

    def list(self, key):
        """Comma-separated value -> list, blanks dropped, de-duplicated."""
        seen, out = set(), []
        for part in self.get(key).split(","):
            part = part.strip()
            if part and part.lower() not in seen:
                seen.add(part.lower())
                out.append(part)
        return out

    def int(self, key, default):
        try:
            return int(self.get(key) or default)
        except ValueError:
            return default

    def bool(self, key, default=True):
        v = self.get(key).strip().lower()
        if not v:
            return default
        return v in ("1", "true", "yes", "on")


CFG = Config(load_properties(PROPS))

TWITCH_CHANNELS = CFG.list("twitch.channels")
YT_VIDEO_IDS = CFG.list("youtube.video.ids")
# Channels to watch for a live broadcast, so the video ID doesn't have to be
# pasted in before every stream. Accepts @handle, UC… id, or a channel URL.
YT_CHANNEL_IDS = CFG.list("youtube.channel.ids")
# How often to re-check an idle channel. Each scan costs 2 units.
YT_SCAN_MS = CFG.int("youtube.scan.ms", 30000)
YT_KEYS = CFG.list("youtube.api.keys")
YT_MIN_POLL_MS = CFG.int("youtube.min.poll.ms", 15000)
YT_MAX_RETRIES = CFG.int("youtube.max.retries", 6)
YT_BACKOFF_MAX_MS = CFG.int("youtube.backoff.max.ms", 300000)

TW_CLIENT_ID = CFG.get("twitch.client.id")
TW_SECRET = CFG.get("twitch.client.secret")
TW_REFRESH = CFG.get("twitch.refresh.token")
SHOW_REDEEMS = CFG.bool("alerts.redeems", True)
ALERT_FLAGS = {
    "follows": CFG.bool("alerts.follows", True),
    "subs": CFG.bool("alerts.subs", True),
    "giftSubs": CFG.bool("alerts.gift.subs", True),
    "cheers": CFG.bool("alerts.cheers", True),
    "raids": CFG.bool("alerts.raids", True),
    "hypeTrain": CFG.bool("alerts.hype.train", True),
}

HOST = CFG.get("relay.host", "127.0.0.1") or "127.0.0.1"
PORT = CFG.int("relay.port", 8777)
# If relay.port is taken, try this many consecutive ports upward.
PORT_ATTEMPTS = CFG.int("relay.port.attempts", 10)
HISTORY_MAX = CFG.int("relay.history", 400)
DEMO_MODE = CFG.bool("relay.demo", False)
# The overlay file served over plain HTTP on the same port.
PAGE_FILE = CFG.get("relay.page", "merged-chat.html") or "merged-chat.html"

# --------------------------------------------------------------------------
# appearance — sent to every page so look-and-feel lives in ONE file
# --------------------------------------------------------------------------
# These map onto the CONFIG keys in the overlay HTML. A page applies whatever
# arrives and leaves the rest at its built-in defaults, so an app.properties
# missing some keys still works.

def yt_emote_map():
    """youtube.emotes as  :code:=url, :code2:=url2  -> {code: url}."""
    out = {}
    for part in CFG.get("youtube.emotes").split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        code, url = part.split("=", 1)
        code, url = code.strip(), url.strip()
        if code and url:
            out[code] = url
    return out


def appearance():
    return {
        "HEAD_MODS": CFG.list("twitch.head.mods"),
        "MAX_MESSAGES": CFG.int("style.max.messages", 80),
        "DOCK_RETAIN_ALL": CFG.bool("style.dock.retain.all", True),
        "DOCK_MAX_MESSAGES": CFG.int("style.dock.max.messages", 400),
        "SHOW_BACKLOG": CFG.bool("style.show.backlog", True),
        "SHOW_STATUS": CFG.bool("style.show.status", True),
        "STATUS_HIDE_SEC": CFG.int("style.status.hide.sec", 4),
        "FONT_SIZE_PX": CFG.int("style.font.size.px", 24),
        "FADE_OUT": CFG.bool("style.fade.out", False),
        "MESSAGE_LIFE_SEC": CFG.int("style.message.life.sec", 60),
        "FADE_DURATION_SEC": CFG.int("style.fade.duration.sec", 1),
        "DARK_BG_COLOR": CFG.get("style.dark.bg.color", "#2a2a2e") or "#2a2a2e",
        "YT_EMOTES": yt_emote_map(),
    }


YT_QUOTA_REASONS = {"quotaExceeded", "dailyLimitExceeded"}
YT_FATAL_REASONS = {
    "forbidden", "liveChatEnded", "liveChatNotFound", "liveChatDisabled",
    "videoNotFound", "keyInvalid", "keyExpired", "accessNotConfigured",
    "ipRefererBlocked",
}


def log(*a):
    print(time.strftime("[%H:%M:%S]"), *a, flush=True)


# --------------------------------------------------------------------------
# client fan-out
# --------------------------------------------------------------------------

CLIENTS = set()
# Recent events, replayed to a page that connects late (a dock opened
# mid-stream) so it has scroll-back instead of an empty feed.
HISTORY = deque(maxlen=max(HISTORY_MAX, 1))
# Latest status text per key, so a new page immediately shows the true state
# instead of "connecting…" until something changes.
STATUS = {}


async def broadcast(payload, remember=True):
    if remember:
        HISTORY.append(payload)
    if not CLIENTS:
        return
    msg = json.dumps(payload)
    dead = []
    for ws in list(CLIENTS):
        try:
            await ws.send(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        CLIENTS.discard(ws)


async def push_status(key, msg):
    """Relay-side status line, mirrored into every page's status box."""
    if STATUS.get(key) == msg:
        return
    STATUS[key] = msg
    log(key + ":", msg)
    # Status is not part of the replayable chat history.
    await broadcast({"t": "status", "key": key, "msg": msg}, remember=False)


# --------------------------------------------------------------------------
# plain HTTP on the same port — serves the overlay to other devices
# --------------------------------------------------------------------------

def lan_ip():
    """This machine's address on the local network. The UDP 'connect' sends
    nothing; it just asks the OS which interface would be used to get out."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return ""
    finally:
        s.close()


def _page_bytes():
    """The overlay HTML. Prefers the real file, falls back to the example so a
    fresh clone still serves something."""
    for name in (PAGE_FILE, "merged-chat.html", "merged-chat-example.html"):
        f = HERE / name
        if f.exists():
            return f.read_bytes()
    return None


def http_response(status, body, ctype="text/html; charset=utf-8"):
    from websockets.datastructures import Headers
    from websockets.http11 import Response
    if not isinstance(body, bytes):
        body = body.encode("utf-8")
    h = Headers()
    h["Content-Type"] = ctype
    h["Content-Length"] = str(len(body))
    h["Cache-Control"] = "no-store"          # always hand out the current file
    return Response(status, "OK" if status == 200 else "Error", h, body)


def process_request(connection, request):
    """Answer ordinary browser requests; let WebSocket handshakes through.

    Serving the page from the same port is what makes another device work: it
    can load the overlay AND reach the relay over one address, with no file
    copying and no second server."""
    try:
        if "websocket" in request.headers.get("Upgrade", "").lower():
            return None                       # a real client — hand off to WS

        path = urllib.parse.urlparse(request.path).path
        if path in ("/", "/index.html", "/" + PAGE_FILE, "/merged-chat.html",
                    "/merged-chat-example.html"):
            body = _page_bytes()
            if body is None:
                return http_response(404, "Overlay HTML not found next to relay.py")
            return http_response(200, body)
        if path == "/favicon.ico":
            return http_response(404, "")
        return http_response(404, "Not found. The overlay is at /")
    except Exception as e:                    # never let a bad request kill the server
        log("http error:", e)
        return None


def client_path(ws, args):
    """Request path, across websockets versions: modern asyncio servers expose
    it on ws.request, older ones set ws.path or pass it as a second argument."""
    req = getattr(ws, "request", None)
    if req is not None and getattr(req, "path", None):
        return req.path
    if getattr(ws, "path", None):
        return ws.path
    return args[0] if args else ""


async def handle_client(ws, *args):
    """One connected page. Replays history on request, then just listens."""
    CLIENTS.add(ws)
    try:
        path = client_path(ws, args) or ""
        want = 0
        m = re.search(r"[?&]history=(\d+)", path)
        if m:
            want = min(int(m.group(1)), HISTORY_MAX)

        backlog = list(HISTORY)[-want:] if want else []
        await ws.send(json.dumps({
            "t": "hello",
            "config": appearance(),      # read fresh, so a restart is all it takes
            "history": backlog,
            "status": STATUS,
        }))
        log("page connected ({} total), replayed {} rows".format(len(CLIENTS), len(backlog)))

        # Pages don't send anything; this just parks until they disconnect.
        async for _ in ws:
            pass
    except Exception:
        pass
    finally:
        CLIENTS.discard(ws)
        log("page disconnected ({} left)".format(len(CLIENTS)))


# --------------------------------------------------------------------------
# HTTP helper (stdlib, run off the event loop)
# --------------------------------------------------------------------------

def _http(method, url, headers=None, body=None, form=None):
    data = None
    headers = dict(headers or {})
    # Some APIs (ivr.fi, used for demo emotes) 403 urllib's default agent.
    headers.setdefault("User-Agent", "merged-chat-relay/1.0")
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"__error__": str(e)}


async def http(method, url, **kw):
    return await asyncio.to_thread(_http, method, url, **kw)


# --------------------------------------------------------------------------
# Twitch IRC — one anonymous socket, all channels
# --------------------------------------------------------------------------

async def twitch_irc_task():
    if not TWITCH_CHANNELS:
        await push_status("twitch", "Twitch: no channel set")
        return

    label = " ".join("#" + c for c in TWITCH_CHANNELS)
    while True:
        try:
            await push_status("twitch", "Twitch: connecting to " + label + "…")
            async with ws_connect("wss://irc-ws.chat.twitch.tv:443") as ws:
                await ws.send("CAP REQ :twitch.tv/tags twitch.tv/commands")
                await ws.send("NICK justinfan%d" % random.randint(0, 99999))
                for c in TWITCH_CHANNELS:
                    await ws.send("JOIN #" + c)
                await push_status("twitch", "Twitch: connected to " + label)

                async for raw in ws:
                    for line in str(raw).split("\r\n"):
                        if not line:
                            continue
                        if line.startswith("PING"):
                            await ws.send("PONG :tmi.twitch.tv")
                            continue
                        # Only chat messages are worth forwarding; the pages
                        # parse the raw line exactly as if they'd read it off
                        # their own socket.
                        if " PRIVMSG " in line:
                            await broadcast({"t": "irc", "line": line})
        except Exception as e:
            log("twitch irc error:", e)
        await push_status("twitch", "Twitch: disconnected, reconnecting in 3s…")
        await asyncio.sleep(3)


# --------------------------------------------------------------------------
# YouTube — poll each chat once, fail over between API keys on quota
# --------------------------------------------------------------------------

# Anything already in chat when the relay booted is backlog and gets skipped;
# anything posted after is live and must be delivered. Using a wall-clock cutoff
# rather than a "first poll" flag matters because the poll loop is re-entered on
# every reconnect (stream not live yet, or a give-up/retry cycle) — a per-connect
# flag silently ate a whole batch of *live* messages each time.
# The 1s margin keeps a message posted in the same second the relay booted on
# the live side of the line: showing a second of backlog is harmless, losing a
# real message is the whole bug.
YT_START = time.time() - 1.0

# Guards the one path that deliberately re-requests a page it already fetched:
# a key rotation re-polls the SAME pageToken, which would otherwise double-post.
YT_SEEN = deque(maxlen=4000)
YT_SEEN_SET = set()


def yt_published_ts(item):
    """snippet.publishedAt -> epoch seconds, or None when it can't be read.

    None means 'deliver anyway' — dropping a message we merely failed to parse
    is the exact failure this cutoff exists to prevent.
    """
    raw = ((item.get("snippet") or {}).get("publishedAt") or "").strip()
    m = re.match(r"^(\d{4}-\d{2}-\d{2})[Tt](\d{2}:\d{2}:\d{2})(?:\.(\d+))?", raw)
    if not m:
        return None
    try:
        base = calendar.timegm(
            time.strptime(m.group(1) + " " + m.group(2), "%Y-%m-%d %H:%M:%S"))
    except ValueError:
        return None
    return base + (float("0." + m.group(3)) if m.group(3) else 0.0)


def yt_is_new(item):
    """False for a message we've already broadcast. Unidentifiable = let it through."""
    mid = item.get("id")
    if not mid:
        return True
    if mid in YT_SEEN_SET:
        return False
    if len(YT_SEEN) == YT_SEEN.maxlen:      # deque is about to evict its oldest
        YT_SEEN_SET.discard(YT_SEEN[0])
    YT_SEEN.append(mid)
    YT_SEEN_SET.add(mid)
    return True


class YouTube:
    def __init__(self):
        self.key_index = 0
        self.exhausted = False

    def key(self):
        return YT_KEYS[self.key_index] if self.key_index < len(YT_KEYS) else ""

    async def rotate(self, status_key):
        """Next key after the current one drains. False = nothing left."""
        if self.key_index + 1 >= len(YT_KEYS):
            return False
        self.key_index += 1
        await push_status(status_key, "YouTube: quota used up — switched to backup key %d/%d"
                          % (self.key_index, len(YT_KEYS) - 1))
        return True

    async def is_fatal(self, err, status_key):
        reason = ""
        errors = err.get("errors") or []
        if errors:
            reason = errors[0].get("reason", "")
        reason = reason or str(err.get("status", ""))

        if reason in YT_QUOTA_REASONS:
            if await self.rotate(status_key):
                return False
            self.exhausted = True
            await push_status(status_key, "YouTube: all %d API keys out of quota — resets at midnight US Pacific"
                              % len(YT_KEYS) if len(YT_KEYS) > 1 else
                              "YouTube: daily quota used up — resets at midnight US Pacific")
            return True
        if reason in YT_FATAL_REASONS:
            await push_status(status_key, "YouTube stopped: " + (err.get("message") or reason))
            return True
        return False

    def backoff_ms(self, tries):
        base = max(YT_MIN_POLL_MS, 5000)
        cap = max(YT_BACKOFF_MAX_MS, base)
        wait = min(base * (2 ** (tries - 1)), cap)
        return wait * (0.8 + random.random() * 0.4)


YT = YouTube()


class YTFatal(Exception):
    """A YouTube error this task can't recover from — unwind and stop."""


def yt_url(path, **params):
    params["key"] = YT.key()
    return "https://www.googleapis.com/youtube/v3/%s?%s" % (
        path, urllib.parse.urlencode(params))


async def yt_get(url, status_key):
    """GET with the shared quota/rotation handling.

    Returns the parsed body, or None when the caller should just try again
    (network blip, or we rolled onto a backup key). Raises YTFatal when there's
    no point retrying at all.
    """
    _, d = await http("GET", url)
    if "__error__" in d:
        return None
    if "error" in d:
        if await YT.is_fatal(d["error"], status_key):
            raise YTFatal()
        return None
    return d


def yt_channel_ref(raw):
    """Normalise a configured channel to ('id'|'handle', value).

    Accepts a bare UC… id, an @handle, or a full youtube.com URL of either.
    """
    s = (raw or "").strip()
    if not s:
        return None
    # Scheme optional — a pasted "youtube.com/@name" is just as likely as a full URL.
    s = re.sub(r"^(https?://)?(www\.)?youtube\.com/", "", s, flags=re.I).strip("/")
    if s.lower().startswith("channel/"):
        s = s[len("channel/"):]
    s = s.split("/")[0].split("?")[0]
    if not s:
        return None
    if s.startswith("@"):
        return ("handle", s[1:])
    if re.fullmatch(r"UC[\w-]{22}", s):
        return ("id", s)
    return ("handle", s)


async def yt_resolve_channel(ref, status_key):
    """@handle -> UC… channel id. Returns None to retry. Costs 1 unit, once."""
    kind, val = ref
    params = {"part": "id", "id" if kind == "id" else "forHandle": val}
    d = await yt_get(yt_url("channels", **params), status_key)
    if d is None:
        return None
    items = d.get("items") or []
    if not items:
        await push_status(status_key, "YouTube: no such channel (%s)" % val)
        raise YTFatal()
    return items[0]["id"]


async def yt_find_live(channel_id, status_key):
    """The channel's current live stream, or None.

    Costs 2 units: the uploads playlist id is derived from the channel id
    (UC… -> UU…) instead of looked up, and a broadcast appears at the top of
    that playlist as soon as it goes live — verified against a live channel.
    The official alternative, search.list?eventType=live, costs 100.
    """
    d = await yt_get(yt_url("playlistItems", part="contentDetails",
                            playlistId="UU" + channel_id[2:], maxResults=5),
                     status_key)
    if d is None:
        return None
    vids = [(i.get("contentDetails") or {}).get("videoId") for i in d.get("items") or []]
    vids = [v for v in vids if v]
    if not vids:
        return None

    d = await yt_get(yt_url("videos", part="snippet,liveStreamingDetails",
                            id=",".join(vids)), status_key)
    if d is None:
        return None

    by_id = {it.get("id"): it for it in d.get("items") or []}
    for vid in vids:                     # newest first, as the playlist ordered them
        it = by_id.get(vid)
        if not it:
            continue
        chat_id = (it.get("liveStreamingDetails") or {}).get("activeLiveChatId")
        if chat_id:
            return vid, chat_id, (it.get("snippet") or {}).get("channelTitle", "channel")
    return None


async def youtube_channel_task(raw, status_key):
    """Watch a channel: scan until it's live, poll its chat, then scan again."""
    if not YT_KEYS:
        await push_status(status_key, "YouTube: no API key set (Twitch only)")
        return

    ref = yt_channel_ref(raw)
    if ref is None:
        return
    label = "@" + ref[1] if ref[0] == "handle" else ref[1]

    channel_id = None
    waiting = False
    fails = 0

    try:
        while not YT.exhausted:
            if channel_id is None:
                channel_id = await yt_resolve_channel(ref, status_key)
                if channel_id is None:
                    fails += 1
                    if 0 < YT_MAX_RETRIES < fails:
                        await push_status(status_key, "YouTube: gave up resolving " + label)
                        return
                    await asyncio.sleep(YT.backoff_ms(fails) / 1000.0)
                    continue
                fails = 0

            found = await yt_find_live(channel_id, status_key)
            if found is None:
                if not waiting:
                    await push_status(status_key,
                                      "YouTube: %s isn't live yet — watching" % label)
                    waiting = True
                await asyncio.sleep(max(YT_SCAN_MS, 5000) / 1000.0)
                continue

            video_id, chat_id, title = found
            waiting = False
            await push_status(status_key, "YouTube: connected to " + title)
            # The scan already handed us the chat id, so skip yt_connect entirely.
            await yt_poll_loop(chat_id, video_id, status_key)
            if YT.exhausted:
                return
            await asyncio.sleep(5)       # stream ended (or dropped) — rescan
    except YTFatal:
        return


async def youtube_task(video_id, status_key):
    if not YT_KEYS:
        await push_status(status_key, "YouTube: no API key set (Twitch only)")
        return

    while True:
        if YT.exhausted:
            return
        chat_id = await yt_connect(video_id, status_key)
        if chat_id is None:
            return                       # fatal, already reported
        if chat_id == "":
            await asyncio.sleep(30)      # not live yet — look again shortly
            continue
        await yt_poll_loop(chat_id, video_id, status_key)
        if YT.exhausted:
            return
        await asyncio.sleep(10)


async def yt_connect(video_id, status_key):
    """Resolve a video ID to its active live chat id. '' = not live, None = stop."""
    while True:
        url = ("https://www.googleapis.com/youtube/v3/videos"
               "?part=snippet,liveStreamingDetails&id=%s&key=%s" % (video_id, YT.key()))
        _, d = await http("GET", url)
        if "error" in d:
            key_before = YT.key_index
            if await YT.is_fatal(d["error"], status_key):
                return None
            if YT.key_index != key_before:
                continue                 # rolled onto a backup key — retry
            await push_status(status_key, "YouTube: " + (d["error"].get("message") or "API error"))
            return None

        items = d.get("items") or []
        if not items:
            await push_status(status_key, "YouTube: video not found (check the ID)")
            return None
        details = items[0].get("liveStreamingDetails") or {}
        chat_id = details.get("activeLiveChatId")
        if not chat_id:
            await push_status(status_key, "YouTube: no active live chat (is the stream live?)")
            return ""
        channel = (items[0].get("snippet") or {}).get("channelTitle", "channel")
        await push_status(status_key, "YouTube: connected to " + channel)
        return chat_id


async def yt_poll_loop(chat_id, video_id, status_key):
    page_token = ""
    fails = 0

    while not YT.exhausted:
        url = ("https://www.googleapis.com/youtube/v3/liveChat/messages"
               "?liveChatId=%s&part=snippet,authorDetails&key=%s" % (chat_id, YT.key()))
        if page_token:
            url += "&pageToken=" + page_token

        _, d = await http("GET", url)

        if "__error__" in d:             # network failure
            fails += 1
            if 0 < YT_MAX_RETRIES < fails:
                await push_status(status_key, "YouTube: gave up after %d failed polls" % YT_MAX_RETRIES)
                return
            await asyncio.sleep(YT.backoff_ms(fails) / 1000.0)
            continue

        if "error" in d:
            key_before = YT.key_index
            if await YT.is_fatal(d["error"], status_key):
                return
            if YT.key_index != key_before:
                # Re-poll the SAME page on the new key so no messages are lost.
                await asyncio.sleep(1)
                continue
            fails += 1
            if 0 < YT_MAX_RETRIES < fails:
                await push_status(status_key, "YouTube: gave up after %d failed polls" % YT_MAX_RETRIES)
                return
            await asyncio.sleep(YT.backoff_ms(fails) / 1000.0)
            continue

        fails = 0
        # Skip the backlog that existed when the relay started; pages want
        # live-from-now. Everything posted since is live, including the first
        # batch after a reconnect.
        for it in d.get("items") or []:
            ts = yt_published_ts(it)
            if ts is not None and ts < YT_START:
                continue
            if not yt_is_new(it):
                continue
            await broadcast({"t": "yt", "videoId": video_id, "item": it})

        page_token = d.get("nextPageToken", "")
        wait = max(d.get("pollingIntervalMillis") or 5000, max(YT_MIN_POLL_MS, 2000))
        await asyncio.sleep(wait / 1000.0)


# --------------------------------------------------------------------------
# Twitch EventSub — alerts and channel point redeems
# --------------------------------------------------------------------------

class Alerts:
    def __init__(self):
        self.access = ""
        self.refresh = TW_REFRESH
        self.user_id = ""
        self.scopes = []


AL = Alerts()


async def refresh_token():
    """Returns True, False (transient) or 'dead' (setup must be redone)."""
    st, d = await http("POST", "https://id.twitch.tv/oauth2/token", form={
        "grant_type": "refresh_token",
        "refresh_token": AL.refresh,
        "client_id": TW_CLIENT_ID,
        "client_secret": TW_SECRET,
    })
    if st in (400, 401):
        await push_status("redeems", "Redeems: refresh token invalid — re-run ?setup in the page")
        return "dead"
    if st != 200 or not d.get("access_token"):
        await push_status("redeems", "Redeems: token refresh failed — retrying")
        return False

    AL.access = d["access_token"]
    if d.get("refresh_token"):
        AL.refresh = d["refresh_token"]          # Twitch rotates these

    if not AL.user_id:
        _, v = await http("GET", "https://id.twitch.tv/oauth2/validate",
                          headers={"Authorization": "OAuth " + AL.access})
        AL.user_id = v.get("user_id", "")
        AL.scopes = v.get("scopes") or []
        if not AL.user_id:
            await push_status("redeems", "Redeems: token validate failed")
            return False

    # Proactively refresh ~5 min before expiry so it never dies mid-stream.
    asyncio.create_task(_refresh_later(max((d.get("expires_in", 14400) - 300), 60)))
    return True


async def _refresh_later(seconds):
    await asyncio.sleep(seconds)
    res = await refresh_token()
    if res is False:
        await asyncio.sleep(30)
        await refresh_token()


def alert_sub_defs():
    bid = AL.user_id
    defs = []
    if SHOW_REDEEMS:
        defs.append(("channel.channel_points_custom_reward_redemption.add", "1",
                     "channel:read:redemptions", {"broadcaster_user_id": bid}))
    if ALERT_FLAGS["follows"]:
        defs.append(("channel.follow", "2", "moderator:read:followers",
                     {"broadcaster_user_id": bid, "moderator_user_id": bid}))
    if ALERT_FLAGS["subs"]:
        defs.append(("channel.subscribe", "1", "channel:read:subscriptions",
                     {"broadcaster_user_id": bid}))
        defs.append(("channel.subscription.message", "1", "channel:read:subscriptions",
                     {"broadcaster_user_id": bid}))
    if ALERT_FLAGS["giftSubs"]:
        defs.append(("channel.subscription.gift", "1", "channel:read:subscriptions",
                     {"broadcaster_user_id": bid}))
    if ALERT_FLAGS["cheers"]:
        defs.append(("channel.cheer", "1", "bits:read", {"broadcaster_user_id": bid}))
    if ALERT_FLAGS["raids"]:
        defs.append(("channel.raid", "1", None, {"to_broadcaster_user_id": bid}))
    if ALERT_FLAGS["hypeTrain"]:
        # v2 only — Twitch retired version 1, which now 400s with
        # "invalid subscription type and version". v2 still carries `level`,
        # which is all the overlay reads.
        defs.append(("channel.hype_train.begin", "2", "channel:read:hype_train",
                     {"broadcaster_user_id": bid}))
    return defs


async def subscribe_all(session_id):
    ok = 0
    missing = []
    for typ, ver, scope, cond in alert_sub_defs():
        if scope and scope not in AL.scopes:
            missing.append(scope)
            continue
        st, d = await http("POST", "https://api.twitch.tv/helix/eventsub/subscriptions",
                           headers={"Client-Id": TW_CLIENT_ID,
                                    "Authorization": "Bearer " + AL.access},
                           body={"type": typ, "version": ver, "condition": cond,
                                 "transport": {"method": "websocket", "session_id": session_id}})
        if st in (200, 202):
            ok += 1
        else:
            log("subscribe failed:", typ, "-", d.get("message") or ("HTTP %s" % st))

    if not ok:
        await push_status("redeems", "Alerts: no subscriptions active" +
                          (" — re-run ?setup to grant the rest" if missing else ""))
    else:
        msg = "Alerts: watching (%d event types)" % ok
        if missing:
            msg += " — re-run ?setup to grant the rest"
        await push_status("redeems", msg)


async def eventsub_task():
    if not (TW_CLIENT_ID and TW_SECRET and TW_REFRESH):
        await push_status("redeems", "Redeems: off (open ?setup once to enable channel points)")
        return

    await push_status("redeems", "Redeems: getting access token…")
    res = await refresh_token()
    if res is not True:
        return

    url = "wss://eventsub.wss.twitch.tv/ws"
    while True:
        try:
            async with ws_connect(url) as ws:
                async for raw in ws:
                    msg = json.loads(raw)
                    meta = msg.get("metadata") or {}
                    payload = msg.get("payload") or {}
                    kind = meta.get("message_type")

                    if kind == "session_welcome":
                        sid = (payload.get("session") or {}).get("id")
                        await subscribe_all(sid)
                    elif kind == "session_reconnect":
                        new = (payload.get("session") or {}).get("reconnect_url")
                        if new:
                            url = new
                            break                     # reconnect to the new url
                    elif kind == "notification":
                        sub_type = (payload.get("subscription") or {}).get("type", "")
                        await broadcast({"t": "alert", "subType": sub_type,
                                         "event": payload.get("event") or {}})
        except Exception as e:
            log("eventsub error:", e)
            await asyncio.sleep(5)
            url = "wss://eventsub.wss.twitch.tv/ws"


# --------------------------------------------------------------------------
# demo mode — fake traffic, generated ONCE and fanned out like the real thing
# --------------------------------------------------------------------------

DEMO_NAMES = ["alice", "Bob_TTV", "carol99", "DangerDan", "emily_x",
              "GamerGirl", "h4x0r", "IzzyLol", "JoeKing", "kevin"]
# Global Twitch emotes (name -> id) — render anywhere, no channel needed.
DEMO_EMOTES = [("Kappa", "25"), ("LUL", "425618"), ("PogChamp", "305954156"),
               ("Kreygasm", "41"), ("4Head", "354"), ("SeemsGood", "64138"),
               ("NotLikeThis", "58765")]
DEMO_LINES = ["hi everyone!", "that was insane", "gg", "poggers", "let's gooo",
              "first time catching you live", "what game is this?", "nice play",
              "LMAO", "o7", "cracked", "welcome back", "this song is such a vibe",
              "no wayyy did you see that clutch?? my heart literally stopped",
              "been watching since the start and this is easily the best run all week",
              "ok but can we talk about how clean that movement was, cracked aim ngl"]


async def fetch_channel_emotes():
    """YOUR channel's sub emotes, from ivr.fi — public, no auth, CORS-open.
    Same source the old in-page demo used, so demo still previews the emotes
    people actually use in your chat rather than only the Twitch globals."""
    found = []
    for login in TWITCH_CHANNELS:
        st, d = await http(
            "GET", "https://api.ivr.fi/v2/twitch/emotes/channel/"
            + urllib.parse.quote(login))
        if st != 200 or not isinstance(d, dict):
            continue
        for sp in d.get("subProducts") or []:
            for e in sp.get("emotes") or []:
                if e.get("code") and e.get("id"):
                    found.append((e["code"], str(e["id"])))
    return found


async def demo_task():
    """Emit fake payloads in the SAME shapes the real sources produce, so the
    pages render them with their normal code and every view matches."""
    await push_status("demo", "DEMO MODE — relay is generating fake messages")
    channel = TWITCH_CHANNELS[0] if TWITCH_CHANNELS else "demo"

    # Your own emotes first, then the globals as a fallback. Weighted so the
    # channel's own emotes are what you mostly see — that's the point of
    # previewing. Offline or no sub emotes: globals only, no error.
    try:
        mine = await fetch_channel_emotes()
    except Exception as e:
        mine = []
        log("demo: couldn't fetch channel emotes (%s) — using globals" % e)
    tw_emotes = (mine * 2 + DEMO_EMOTES) if mine else list(DEMO_EMOTES)
    log("demo: %d channel emotes + %d globals" % (len(mine), len(DEMO_EMOTES)))

    # YouTube member emotes come straight from youtube.emotes in app.properties;
    # the page maps these codes to images itself.
    yt_codes = list(yt_emote_map().keys())
    log("demo: %d YouTube emotes from app.properties" % len(yt_codes))

    while True:
        await asyncio.sleep(1.2)
        name = random.choice(DEMO_NAMES)
        text = random.choice(DEMO_LINES)
        roll = random.random()

        if random.random() < 0.5:
            # A YouTube liveChat item. YouTube sends member emotes as plain
            # :shortcodes: — exactly what we do here — and the page swaps them
            # for images using the map from app.properties.
            if yt_codes and random.random() < 0.45:
                codes = " ".join(random.choice(yt_codes)
                                 for _ in range(random.randint(1, 3)))
                text = (text + " " + codes) if random.random() < 0.5 else (codes + " " + text)

            await broadcast({"t": "yt", "videoId": "demo", "item": {
                "authorDetails": {
                    "displayName": name,
                    "isChatOwner": roll > 0.95,
                    "isChatModerator": 0.85 < roll <= 0.92,
                    "isChatSponsor": 0.55 < roll <= 0.78,
                },
                "snippet": {"displayMessage": text},
            }})
        else:
            # A raw tagged IRC line, exactly as Twitch would send it — including
            # a real `emotes` tag some of the time, so the demo still exercises
            # the page's emote rendering now that the page has no demo of its own.
            # Twitch sends emote positions in the `emotes` tag rather than the
            # text, so build a real one — several emotes are grouped per id,
            # ranges are 0-based and inclusive, groups separated by "/".
            emote_tag = ""
            if random.random() < 0.45:
                by_id = {}
                for _ in range(random.randint(1, 3)):
                    code, eid = random.choice(tw_emotes)
                    start = len(text) + 1
                    text = text + " " + code
                    by_id.setdefault(eid, []).append(
                        "%d-%d" % (start, start + len(code) - 1))
                emote_tag = "/".join(eid + ":" + ",".join(spans)
                                     for eid, spans in by_id.items())

            badges = []
            if roll > 0.95:
                badges.append("broadcaster/1")
            elif 0.85 < roll <= 0.92:
                badges.append("moderator/1")
            elif 0.78 < roll <= 0.85:
                badges.append("vip/1")
            elif 0.55 < roll <= 0.78:
                badges.append("subscriber/%d" % random.choice([2, 6, 12]))
            colour = "#%06x" % random.randint(0x333333, 0xFFFFFF)
            line = ("@badges=%s;color=%s;display-name=%s;emotes=%s "
                    ":%s!%s@%s.tmi.twitch.tv PRIVMSG #%s :%s"
                    % (",".join(badges), colour, name, emote_tag,
                       name.lower(), name.lower(), name.lower(), channel, text))
            await broadcast({"t": "irc", "line": line})

        # An occasional alert, in EventSub's payload shape.
        if random.random() < 0.12:
            kind, event = random.choice([
                ("channel.follow", {"user_name": name}),
                ("channel.subscribe", {"user_name": name, "tier": "1000"}),
                ("channel.cheer", {"user_name": name, "bits": random.choice([100, 500, 1000]),
                                   "message": text}),
                ("channel.raid", {"from_broadcaster_user_name": name,
                                  "viewers": random.choice([12, 48, 230])}),
                ("channel.subscription.gift", {"user_name": name, "tier": "1000",
                                               "total": random.choice([1, 5, 10])}),
            ])
            await broadcast({"t": "alert", "subType": kind, "event": event})


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

async def main():
    log("Merged Chat relay starting")
    log("  twitch channels :", ", ".join(TWITCH_CHANNELS) or "(none)")
    log("  youtube videos  :", ", ".join(YT_VIDEO_IDS) or "(none)")
    log("  youtube channels:", ", ".join(YT_CHANNEL_IDS) or "(none)",
        "(scan every %ds)" % (max(YT_SCAN_MS, 5000) // 1000) if YT_CHANNEL_IDS else "")
    log("  youtube keys    :", "%d (1 primary + %d backup)" % (len(YT_KEYS), max(len(YT_KEYS) - 1, 0))
        if YT_KEYS else "(none)")
    log("  alerts          :", "on" if (TW_CLIENT_ID and TW_REFRESH) else "off")
    if DEMO_MODE:
        log("  *** DEMO MODE *** fake messages only, no live sources contacted")
    log("  listening on    : ws://%s:%d%s  (history %d)"
        % (HOST, PORT,
           "-%d" % (PORT + PORT_ATTEMPTS - 1) if PORT_ATTEMPTS > 1 else "",
           HISTORY_MAX))

    if DEMO_MODE:
        # Demo replaces the live sources entirely — no keys touched, no quota
        # spent, and every page still sees the same fake feed.
        tasks = [asyncio.create_task(demo_task())]
    else:
        tasks = [asyncio.create_task(twitch_irc_task()),
                 asyncio.create_task(eventsub_task())]
        # Pinned video IDs first, then watched channels — one status slot each.
        yt_sources = ([("video", v) for v in YT_VIDEO_IDS] +
                      [("channel", c) for c in YT_CHANNEL_IDS])
        for i, (kind, val) in enumerate(yt_sources):
            key = "youtube" if i == 0 else "youtube%d" % (i + 1)
            tasks.append(asyncio.create_task(
                youtube_task(val, key) if kind == "video"
                else youtube_channel_task(val, key)))

    # Bind the configured port, walking upwards if it's taken — a leftover relay,
    # another app, or a second copy for a different channel. The page scans the
    # same range, so it still finds us on the fallback port.
    async with AsyncExitStack() as stack:
        chosen = None
        for offset in range(max(PORT_ATTEMPTS, 1)):
            port = PORT + offset
            try:
                await stack.enter_async_context(
                    ws_serve(handle_client, HOST, port,
                             process_request=process_request))
                chosen = port
                break
            except OSError as e:
                log("port %d is busy (%s)" % (port, getattr(e, "strerror", e) or e))

        if chosen is None:
            sys.exit("No free port in %d-%d. Close whatever is using them, or set "
                     "relay.port in app.properties." % (PORT, PORT + PORT_ATTEMPTS - 1))

        if chosen != PORT:
            log("*** using port %d instead of %d — the page scans this range, "
                "so no config change is needed ***" % (chosen, PORT))

        ip = lan_ip()
        log("")
        log("relay ready. Open the overlay at:")
        log("    this machine  :  http://127.0.0.1:%d/" % chosen)
        if HOST in ("0.0.0.0", "::", ""):
            if ip:
                log("    other devices :  http://%s:%d/     <-- phone, tablet, second PC" % (ip, chosen))
                log("                     (same wifi/LAN; no setup needed on that device)")
            else:
                log("    other devices :  couldn't work out this machine's LAN address")
        else:
            log("    other devices :  not reachable — bound to %s only." % HOST)
            if ip:
                log("                     Set relay.host=0.0.0.0 in app.properties and")
                log("                     restart to serve http://%s:%d/ to your LAN." % (ip, chosen))
            else:
                log("                     Set relay.host=0.0.0.0 in app.properties to allow it.")
        log("")
        log("In OBS you can keep using the local file, or point the Browser")
        log("source at the http:// address above — both get the same chat.")
        log("")
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("relay stopped")
