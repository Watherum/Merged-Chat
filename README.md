# Merged Twitch + YouTube Chat Overlay — Setup & Usage

One scrolling chat feed that merges Twitch and YouTube live chat into a single
list. Each message is tagged with the platform's logo on a colored badge:

- **Twitch** — white Twitch glyph on a purple badge
- **YouTube** — white play button on a red badge

Built as a transparent overlay for use as an OBS Browser source.

## Files

Keep all files together in the same folder.

| File | Purpose |
| --- | --- |
| `merged-chat.html` | The real overlay. Your channel + API key go in here. This is the one you load in OBS. |
| `merged-chat-example.html` | A clean copy with **no** channel/key filled in (safe to share or back up). Uses the default font; Teko left as an option. |
| `relay.py` | Optional but recommended: one local process that does all the network work and feeds every open view, so a source and a dock share one connection and one quota. See [Sharing one connection](#sharing-one-connection-between-every-view-relaypy). |
| `install-requirements.bat` | Windows one-time setup: installs the Python package and creates `app.properties`. |
| `start-relay.bat` | Windows: starts the relay. Double-click it before you stream. |
| `requirements.txt` | The Python packages the relay needs. |
| `app.properties.example` | Documented template for the relay's settings. |
| `app.properties` | Your real relay settings (channel, keys, token). Created by you from the template. |
| `README.md` | This file. |

> **Note:** `merged-chat.html` and `app.properties` are git-ignored because they
> hold your private API keys. Share `merged-chat-example.html` and
> `app.properties.example` instead.

## How It Works (why it needs what it needs)

- **Twitch:** connects anonymously over WebSocket (IRC). No account, no key.
  Works immediately.
- **YouTube:** live chat **cannot** be read from an iframe (cross-origin), so it
  uses the YouTube Data API v3, which requires a free API key tied to a Google
  account. Without the key, the Twitch half still works; the YouTube half stays
  empty.
- **Twitch alerts & channel points (optional):** subs, cheers, follows, raids,
  hype trains, and channel point redeems can also appear in the feed. These don't
  travel over chat, so they use Twitch EventSub and need a one-time Twitch token
  (see [Twitch Alerts & Channel Point
  Redeems](#twitch-alerts--channel-point-redeems-optional)). Plain chat needs none.
- Both work from a plain `file://` page, so **no** local web server is needed.

## Visual Features (what you'll see)

- Platform logo badge on every message (Twitch / YouTube).
- Broadcaster gets a small video-camera icon on a gold tag (works for both the
  Twitch broadcaster and the YouTube channel owner).
- Moderators get a green **MOD** tag.
- Usernames are colored: Twitch uses each chatter's own color; everyone else
  gets a stable auto-generated color from their name.
- Twitch emotes are rendered as images.
- Optionally, Twitch **alerts and channel point redeems** (subs, cheers, follows,
  raids, hype trains, redemptions) appear as distinct colored rows — see [Twitch
  Alerts & Channel Point Redeems](#twitch-alerts--channel-point-redeems-optional).
- New messages pop in with a quick animation.
- All text has a black outline so it stays readable over any video, and the page
  background is transparent for OBS.
- Connection status box (top-left) shows one line per platform, e.g.:

  ```
  Twitch: connected to #yourchannel
  YouTube: connected to Your Channel Name
  ```

  It auto-hides after a few seconds (configurable — see `STATUS_HIDE_SEC`).

## Where settings live

Once you're running the relay — the normal setup — there are two files, and only
one of them you'll normally touch:

| File | Holds | When it's used |
| --- | --- | --- |
| **`app.properties`** | Channel, video IDs, API keys, Twitch token, **and all appearance settings** (font size, message caps, fade, colours, head mods, YouTube emotes) | Read by the relay and sent to every view on connect. **This is the file to edit.** |
| `merged-chat.html` CONFIG | The same appearance keys, as fallback defaults, plus `RELAY_URL` | Only used when no relay is running. `RELAY_URL` / `RELAY_PORT_TRIES` always come from here — they're how a page finds the relay. |

Change appearance in `app.properties`, restart the relay, refresh the page. You
should not need to edit the HTML at all.

The rest of this section describes the HTML CONFIG keys; each has an
`app.properties` equivalent listed in `app.properties.example`.

## Step 1 — Edit the Config (top of `merged-chat.html`)

Open `merged-chat.html` in a text editor (right-click → Edit, or open with
Notepad). Near the top, find the CONFIG block.

### Required — who to connect to

| Setting | Value |
| --- | --- |
| `TWITCH_CHANNEL` | `"your_channel"` — your twitch channel (lowercase) |
| `TWITCH_CHANNELS` | `[]` — optional extra Twitch channels to merge in (see below) |
| `YT_VIDEO_ID` | `"VIDEO_ID"` — the `v=...` id from the youtube URL |
| `YT_VIDEO_IDS` | `[]` — optional extra live video IDs to merge in (see below) |
| `YT_API_KEY` | `"YOUR_API_KEY"` — paste your YouTube Data API key |
| `YT_MIN_POLL_MS` | `15000` — how often to poll YouTube chat (quota saver, see below) |

- The YouTube video ID is the part after `v=` in the watch / live_chat URL.
  Example: `https://www.youtube.com/live_chat?is_popout=1&v=VIDEO_ID` → the ID is
  the `VIDEO_ID` part.
- Leave `TWITCH_CHANNEL` blank (`""`) to run YouTube only, or leave the YouTube
  fields blank to run Twitch only.

### Merging multiple Twitch channels

To blend more than one Twitch chat into the same feed, list the extra channels in
`TWITCH_CHANNELS` (an array). They're merged in alongside `TWITCH_CHANNEL`:

```js
TWITCH_CHANNEL  : "your_channel",
TWITCH_CHANNELS : ["co_streamer", "another_channel"],
```

- All channels are joined over a single anonymous connection — no extra keys or
  accounts needed, and no added quota cost.
- Names are case-insensitive and a leading `#` is fine; duplicates are ignored.
- Each channel's own broadcaster still gets the gold broadcaster tag, and each
  channel's mods get the green **MOD** tag.
- You can also run channels-only by leaving `TWITCH_CHANNEL` blank and putting
  everything in `TWITCH_CHANNELS`.

### Merging multiple YouTube chats

Same idea for YouTube — list extra live video IDs in `YT_VIDEO_IDS` (an array).
They're merged in alongside `YT_VIDEO_ID`:

```js
YT_VIDEO_ID  : "VIDEO_ID",
YT_VIDEO_IDS : ["VIDEO_ID_2", "VIDEO_ID_3"],
```

- Each video gets its own connection and status line (e.g. `YouTube: connected
  to Channel A` / `YouTube: connected to Channel B`).
- Each stream's owner gets the broadcaster tag and each stream's mods get the
  **MOD** tag.
- Duplicate IDs are ignored; you can also run videos-only by leaving
  `YT_VIDEO_ID` blank and filling `YT_VIDEO_IDS`.

> **⚠️ Quota warning:** unlike Twitch (which is free), **every** YouTube chat
> consumes your daily API quota (10,000 units). Merging two or three streams
> burns through it 2–3× faster, and a long multi-stream session can hit
> `quotaExceeded` (resets at midnight US Pacific). For heavy use, add
> [backup keys](#backup-api-keys-for-when-quota-runs-out-yt_api_key_backup) from
> extra Google Cloud projects, raise `YT_MIN_POLL_MS`, or request a quota increase.

### Auto-detecting your live stream (`youtube.channel.ids`, relay only)

YouTube mints a **new video ID for every broadcast**, so pinning
`youtube.video.ids` means editing `app.properties` before each stream — and a
forgotten edit fails quietly: the relay just reports *"no active live chat"* and
never delivers a message.

Instead, point the relay at the **channel** and let it find the current stream:

```properties
youtube.channel.ids=@your_channel
youtube.scan.ms=30000
```

Accepts an `@handle`, a `UC…` channel id, or a channel URL; comma-separate to
watch several. While the channel is offline the relay reports *"@name isn't live
yet — watching"* and re-checks on `youtube.scan.ms`. When you go live it picks up
the video ID, connects, and stops scanning. When the stream ends it goes back to
watching, so an OBS source left running overnight reconnects by itself.

**Cost: 2 units per scan.** The uploads playlist id is derived from the channel
id (`UC…` → `UU…`) rather than looked up, and a broadcast appears at the top of
that playlist the moment it goes live. At 30s that's ~240 units/hr while idle,
against a 10,000/day budget. The official alternative — `search.list` with
`eventType=live` — returns the same answer but costs **100 units a call**, which
would drain a key in under two hours of waiting.

> **⚠️ Check the handle.** A channel's `@handle` isn't always the obvious one,
> and an unused placeholder channel with a similar name will resolve fine but
> never go live — leaving you with a relay that watches forever and never
> connects. If in doubt, use the `UC…` id from the channel page URL.

`youtube.video.ids` still works and can be combined with this — use it to pin one
specific broadcast, or to merge in someone else's stream.

### Controlling YouTube quota usage (polling rate)

YouTube quota is spent on **how often** the page polls for new messages. Each
poll costs **5 quota units**, so the 10,000/day allowance is really **2,000
polls**, shared across every YouTube source on that key. The default is:

```js
YT_MIN_POLL_MS : 15000,   // poll every 15s — roughly 8 hours of stream
```

| `YT_MIN_POLL_MS` | Polls/hr | Units/hr | Runtime on a fresh 10,000 |
| --- | --- | --- | --- |
| `0` (as fast as the API allows, ~5s) | 720 | 3,600 | ~2.8 hr |
| `10000` | 360 | 1,800 | ~5.5 hr |
| `15000` (default) | 240 | 1,200 | ~8.3 hr |
| `30000` | 120 | 600 | ~16.6 hr |

- **Polling slower never drops messages.** Each poll returns everything posted
  since the previous one, so a longer interval just delivers a bigger batch. The
  only cost is latency — at 15s a YouTube message shows up ~7s late on average.
  Twitch is unaffected (it's free and event-driven, not polled).
- The value is the **minimum** milliseconds between polls. A 2-second hard floor
  always applies, so values below 2000 behave the same as `0`.
- **Divide the runtime by the number of YouTube sources.** Each video ID in
  `YT_VIDEO_ID` / `YT_VIDEO_IDS` gets its own poll loop, so two YouTube chats at
  `15000` = ~4 hr, not ~8. Opening the overlay as *both* a Browser source and a
  dock costs nothing extra when [`relay.py`](#sharing-one-connection-between-every-view-relaypy)
  is running — they share one connection. To extend the runtime past a single
  key, add a backup key.
- Watch your real usage in **Google Cloud Console → APIs & Services → YouTube
  Data API v3 → Metrics**. Quota resets at midnight US Pacific.

### When YouTube errors out

The overlay won't retry a broken connection forever in the background. Errors are
split into two kinds:

- **Fatal — stops immediately.** Quota exhausted, invalid/blocked API key, or the
  live chat ended / was disabled / the video is gone. Retrying can't fix any of
  these, so the loop stops and the status line says why. Quota exhaustion stops
  **every** YouTube source on that key at once, and blocks the connect call too,
  so reloading the page won't nibble at a quota that's already gone.
- **Transient — retries with backoff, then gives up.** Network drops, rate
  limits, Google 5xx, or any error the overlay doesn't recognise. Each retry
  waits roughly twice as long as the last (jittered so merged sources don't
  retry in lockstep), then the loop stops for good.

```js
YT_MAX_RETRIES    : 6,        // consecutive failed polls before giving up (0 = never)
YT_BACKOFF_MAX_MS : 300000,   // ceiling on the wait between retries (5 min)
```

At the defaults that's retries at roughly 15s, 30s, 1m, 2m, 4m, 5m — about 13
minutes of trying before it stops — 6 requests total, where the old fixed
5-second retry would have kept firing 720 an hour indefinitely. The status line shows
the countdown (`YouTube: retrying in 30s (2/6)`), and reloading the page starts
a fresh connection.

> **Tip:** another way to expand headroom is to give each page its own API key
> from a *separate* Google Cloud project — each project has its own independent
> 10,000/day quota. See the next section for how to point the dock at a second key.

### Sharing one connection between every view (`relay.py`)

**This is the recommended way to run a source + dock.**

Open this overlay twice — the usual setup being an OBS Browser source plus an OBS
custom browser dock — and each page would poll YouTube separately (double quota)
and each would try to claim the same Twitch EventSub subscriptions (Twitch
answers the second one with a 409).

`relay.py` fixes that by moving the network work out of the browser. One small
Python process holds **one** Twitch chat connection, polls each YouTube chat
**once**, holds **one** EventSub session, and re-broadcasts everything to every
open page over a local WebSocket. Every view then shows identical chat, however
many you have open.

#### Setup (Windows)

1. **Double-click `install-requirements.bat`.** It finds Python, installs the
   one package the relay needs, and creates `app.properties` from the template
   (offering to open it in Notepad).

2. **Fill in `app.properties`** — your channel, YouTube video ID and API key.
   Every setting is documented in `app.properties.example`. This file is
   **git-ignored**, so your keys stay out of the repo.

3. **Double-click `start-relay.bat`** before you stream, and leave the window
   open. Closing it stops the relay.

If Python isn't installed, get it from
[python.org/downloads](https://www.python.org/downloads/) and tick
**"Add python.exe to PATH"** during setup.

#### Setup (macOS / Linux, or by hand)

1. Install the dependency:

   ```
   python3 -m pip install -r requirements.txt
   ```

2. Copy the config template and fill it in:

   ```
   cp app.properties.example app.properties
   ```

3. Start it (leave it running while you stream):

   ```
   python3 relay.py
   ```

   ```
   [09:42:01] Merged Chat relay starting
   [09:42:01]   twitch channels : your_channel
   [09:42:01]   youtube keys    : 2 (1 primary + 1 backup)
   [09:42:01]   listening on    : ws://127.0.0.1:8777-8786  (history 400)
   [09:42:01] relay ready on ws://127.0.0.1:8777 — open merged-chat.html in OBS
   ```

Then open the overlay in OBS as usual. `RELAY_URL` in the CONFIG block already
points at `ws://127.0.0.1:8777`, so there's nothing else to change.

#### Viewing chat on another device (phone, tablet, second PC)

The relay also serves the overlay over plain HTTP on the same port, so another
device on your network can just browse to it — nothing to copy, nothing to
install there.

1. Set `relay.host=0.0.0.0` in `app.properties` (it defaults to `127.0.0.1`,
   which only allows this machine).
2. Restart the relay. It prints the address to use:

   ```
   relay ready. Open the overlay at:
       this machine  :  http://127.0.0.1:8777/
       other devices :  http://192.168.50.83:8777/     <-- phone, tablet, second PC
                        (same wifi/LAN; no setup needed on that device)
   ```

3. Type that second address into the other device's browser.

The page works out where the relay is from the address it was loaded from, so a
phone talks to your PC rather than to itself — there is nothing to configure on
the device. Add `?bg=dark` for a readable dark background on a phone:
`http://192.168.50.83:8777/?bg=dark&docked=true`.

You can also point the **OBS Browser source** at the `http://` address instead of
the local file if you prefer; both show the same chat.

> **Only do this on a network you trust.** The port has no password, so anyone
> who can reach your machine on the LAN can read your chat overlay. It stays
> bound to `127.0.0.1` until you change `relay.host` yourself.

#### If the port is already in use

The relay walks upward to the next free port (`8777`, `8778`, … for
`relay.port.attempts` tries) and says so:

```
[09:42:01] port 8777 is busy ([WinError 10048] ...)
[09:42:01] *** using port 8778 instead of 8777 — the page scans this range,
           so no config change is needed ***
```

The page scans the same range (`RELAY_PORT_TRIES` in the CONFIG block), so it
finds the relay wherever it landed — **you don't need to change anything**. Keep
the two numbers in step if you edit either. If every port in the range is taken,
the relay exits with a message rather than starting up unreachable.

#### What you get

- **One** YouTube quota, no matter how many views are open.
- **One** set of EventSub subscriptions — no 409s, no second Twitch app, so
  `TWITCH_CLIENT_ID_DOCK` and friends are no longer needed.
- Every view renders **identical** chat, because they all receive the same
  payloads.
- A dock opened mid-stream replays the last `relay.history` rows, so it has
  scroll-back immediately instead of an empty feed.
- Chat survives an OBS refresh — the relay keeps running, so nothing reconnects
  and no messages are missed while a source reloads.

#### If the relay isn't running

Each page just connects directly, exactly as before. Nothing breaks; you simply
go back to one quota per page. So it's safe to leave `RELAY_URL` set even when
you don't start the relay.

To force a page to connect directly, blank `RELAY_URL` in the CONFIG block.

#### Notes

- The relay listens on `127.0.0.1` only, so nothing is exposed off your machine.
  `relay.host=0.0.0.0` would let other machines on your LAN connect — the port is
  unauthenticated, so only do that deliberately.
- Config lives in `app.properties`, **not** in the HTML, when you run the relay.
  The HTML's `TWITCH_CHANNEL` / `YT_API_KEY` / etc. are only used in direct mode.
  Appearance settings (fonts, sizes, fade, badges) always come from the HTML.
- Run a second setup by pointing it at another file: `python relay.py other.properties`.
- Restart the relay after editing `app.properties`.

### Backup API keys for when quota runs out (`YT_API_KEY_BACKUP`)

YouTube quota is granted **per Google Cloud project**, so a key from a second
project carries its own separate 10,000/day. Give the overlay one or more backup
keys and it will roll onto the next one when the current key runs dry, instead of
dropping YouTube chat for the rest of the day:

```js
YT_API_KEY        : "AIza...PRIMARY",
YT_API_KEY_BACKUP : "AIza...SECOND",                      // one key
YT_API_KEY_BACKUP : ["AIza...SECOND", "AIza...THIRD"],    // ...or several
```

To make a backup key: in Google Cloud create a **new project**, enable **YouTube
Data API v3** in it, and make an API key with Application restrictions = **None**
(same as the primary — a referrer restriction blocks `file://` pages). Repeat for
as many as you want.

What you'll see when the primary drains mid-stream:

```
YouTube: quota used up — switched to backup key 1/2
```

The switch re-polls the *same* page of chat on the new key, so no messages are
lost and it doesn't go through the retry backoff — chat keeps flowing. All poll
loops share one key pointer, so if you merge several YouTube chats they all move
across together. Only once **every** key is drained does it stop for the day:

```
YouTube: all 3 API keys out of quota — resets at midnight US Pacific
```

Notes:

- Keys are tried in order and de-duplicated; blanks are ignored. With no backup
  set, behaviour is exactly as before.
- Rotation only triggers on a genuine quota error (`quotaExceeded` /
  `dailyLimitExceeded`). A bad key or a disabled API is still reported as a plain
  error rather than silently burning through your spares.
- Backups don't multiply your polling rate — they extend how long you can run.
  `YT_MIN_POLL_MS` is still what decides how fast a single key is consumed.

> **Migrating from `YT_API_KEY_DOCK`:** that key used to serve the dock's separate
> quota, which the relay made unnecessary. It's now read as a backup key, so an
> existing config keeps working untouched — but rename it to `YT_API_KEY_BACKUP`
> when convenient, since that's what it now does.

#### Keeping a long history & scrolling back (`DOCK_RETAIN_ALL`)

In docked mode the dock is meant to be *read*, so by default it keeps a **long
scroll-back history** (the last `DOCK_MAX_MESSAGES`, default **400**) and lets you
**scroll up** through it — unlike the on-stream overlay, which only keeps the last
`MAX_MESSAGES` lines and fades them out.

This is controlled by `DOCK_RETAIN_ALL` in the CONFIG block (default `true`):

```js
DOCK_RETAIN_ALL : true,    // docked mode: long scroll-back history
DOCK_MAX_MESSAGES : 400,   // how many messages that history holds
```

When it's on (and `?docked=true` is in the URL):

- **Up to `DOCK_MAX_MESSAGES` (400) lines are kept** instead of `MAX_MESSAGES`, so
  you can scroll back through the session. 400 is plenty for a full stream while
  keeping memory bounded.
- **`FADE_OUT` is ignored** so old messages don't disappear while you're reading.
- **Stick-to-bottom:** new messages auto-follow only while you're already at the
  bottom. Scroll up to read history and it stops jumping (and stops trimming, so
  what you're reading doesn't get yanked); scroll back to the bottom to resume
  auto-following and trim back down to the cap.

It only affects docked mode — the normal transparent overlay is unchanged. To
turn it off for a single dock without editing the file, add `&retain=0` (or
`&retain=false`) to that dock's URL:

```
file:///D:/.../merged-chat.html?docked=true&retain=0
```

### YouTube member / custom emotes (`YT_EMOTES`)

Twitch emotes (global, sub, and channel) render as images **automatically** — Twitch
tells the overlay exactly which emotes are in each message. YouTube does **not**: its
API only sends the emote's text shortcode (e.g. `:_happy:`), with no image. So to show
YouTube custom/membership emotes as images, you map each shortcode to its image URL in
`YT_EMOTES`:

```js
YT_EMOTES : {
  ":_happy:"  : "https://yt3.ggpht.com/.../=s48-c-k-nd",
  ":_hype:"   : "https://yt3.ggpht.com/.../=s48-c-k-nd",
},
```

How to find the two values:

- **Shortcode** — the exact `:text:` form as it appears in chat. Easiest way: run the
  overlay during a live stream; any emote you haven't mapped yet shows up as its raw
  `:shortcode:` text in the feed **and** is logged in the browser console (F12) as
  `unmapped YouTube emote shortcode: …`. Copy it verbatim, colons included.
- **URL** — right-click the emote in your YouTube live chat → **Copy image address**.

Unmapped emotes simply stay as their `:shortcode:` text (harmless). Standard unicode
emoji (😀🔥) always work without mapping. To preview your mapped emotes without going
live, fill in `YT_EMOTES`, set `DEMO_MODE : true`, and Refresh — they'll appear on the
demo's YouTube rows.

### Optional — appearance & behavior

| Setting | Default | Meaning |
| --- | --- | --- |
| `MAX_MESSAGES` | `80` | How many lines stay on screen at once (overlay mode; docked mode uses `DOCK_MAX_MESSAGES` instead when `DOCK_RETAIN_ALL` is on). |
| `DOCK_RETAIN_ALL` | `true` | Docked mode only: keep a long scroll-back history (`DOCK_MAX_MESSAGES`) and allow scrolling up through it, with fade-out disabled. Override per-dock with `&retain=0`. See [Keeping a long history & scrolling back](#keeping-a-long-history--scrolling-back-dock_retain_all). |
| `DOCK_MAX_MESSAGES` | `400` | Size of the docked scroll-back buffer (how many messages are kept when `DOCK_RETAIN_ALL` is on). |
| `SHOW_BACKLOG` | `false` | `false` = only show new messages after load (recommended). `true` = also show recent messages that already existed when it loaded. **YouTube only** — Twitch connects via anonymous IRC, which sends no history on join, so Twitch always starts live-from-connect regardless of this setting. |
| `SHOW_STATUS` | `true` | Show the connection status box, top-left (set to `false` to hide it completely). |
| `STATUS_HIDE_SEC` | `12` | Seconds the status box stays on screen before fading out. Set to `0` to keep it visible permanently (handy while testing). |
| `FONT_SIZE_PX` | `24` | Base text size (see [Changing the Font](#changing-the-font)). |
| `DARK_BG_COLOR` | `"#2a2a2e"` | Background shade used **only** when the page is opened with `?bg=dark` (see [Dark Background for an OBS Dock](#dark-background-for-an-obs-dock)). No effect on the normal transparent overlay. |

### Optional — fade-out (auto-remove old messages)

| Setting | Default | Meaning |
| --- | --- | --- |
| `FADE_OUT` | `true` | On/off. `true` = each message fades away after its lifetime; `false` = messages stay until pushed off by `MAX_MESSAGES`. |
| `MESSAGE_LIFE_SEC` | `30` | Seconds a message stays fully visible before it begins to fade. |
| `FADE_DURATION_SEC` | `1` | How long the fade animation itself takes. |

Example: `FADE_OUT true`, `MESSAGE_LIFE_SEC 30`, `FADE_DURATION_SEC 1` means a
message shows for 30s, then fades out over 1s and is removed. Set `FADE_OUT` to
`false` for a classic always-on chat list.

### Optional — testing

| Setting | Default | Meaning |
| --- | --- | --- |
| `DEMO_MODE` | `false` | `true` = show fake test messages (no stream or keys needed). Set back to `false` before going live. |

Save the file after editing, then Refresh the source in OBS.

## Changing the Font

`merged-chat.html` ships using the **Teko** font (a tall, condensed Google Font)
at `FONT_SIZE_PX 24`.

To change fonts, find this line in the `<style>` section:

```css
font-family: "Teko", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
```

- To go back to the plain default look, remove the `"Teko",` part:

  ```css
  font-family: "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  ```

- To use a different Google Font, change the `<link ...>` near the top of the
  file to that font, then put its name first in `font-family`.

> **Note:** Teko is condensed, so it reads smaller than normal fonts. Teko ~24px
> looks about the same size as a normal font at ~18px. Adjust `FONT_SIZE_PX` to
> taste after switching.

(`merged-chat-example.html` is set the opposite way: default font at 18px, with
Teko left available as a commented option.)

## Step 2 — Get a Free YouTube API Key (~3 minutes)

1. Go to <https://console.cloud.google.com/>
2. Create a project (top bar → New Project). Any name is fine.
3. APIs & Services → Library → search "YouTube Data API v3" → click it → Enable.
4. APIs & Services → Credentials → Create Credentials → API key.
5. Copy the key and paste it into `YT_API_KEY` in the CONFIG block.

> **Important:** On the key's settings, leave "Application restrictions" set to
> **None**. If you add an "HTTP referrers" restriction, requests from a `file://`
> page (OBS) get **blocked** and the YouTube side will silently show nothing.

> **Keep it private:** the key sits in plain text inside `merged-chat.html`.
> Don't screen-share or post that file. Share `merged-chat-example.html` instead
> (it has no key).

## Step 3 — Add It to OBS

1. In OBS: Sources → **+** → Browser (give it a name → OK).
2. Tick "Local file" and Browse to `merged-chat.html`.
3. Set Width / Height — see [How to Size It](#how-to-size-it-in-obs) below.
4. Click OK.
5. Whenever you change the CONFIG, right-click the source → Refresh (OBS caches
   the page).

## How to Size It in OBS

There are **two** different sizes, and mixing them up is the usual cause of tiny
text or cut-off messages:

### A) The Browser source resolution

The Width / Height fields in the source's Properties window.

- This is the actual canvas the chat page renders into.
- The feed is a tall vertical list, so a portrait size works best, e.g.
  `400 x 800` (try 350–450 wide, 600–1000 tall).
- Text size is controlled by `FONT_SIZE_PX` in the CONFIG, **not** by this box.
  If text looks too small/large, change `FONT_SIZE_PX` in `merged-chat.html` and
  Refresh — do not just stretch the source.
- Rule of thumb: set Width/Height here to roughly the real pixel size you want it
  on screen, then leave it.

### B) The on-canvas size

The red box you drag in the main preview.

- After adding the source you can drag its corners to move and scale it in your
  scene.
- **Important:** dragging the corners *scales* (zooms) the rendered page — it
  does **not** give it more room. Scaling up = blurry / huge text; scaling down =
  tiny text.
- For crisp text, get it close to right with the Width/Height in (A), then only
  fine-tune position here.
- To reset scaling: right-click the source → Transform → Reset Transform (sets it
  back to 1:1 with its resolution).

### Recommended workflow

1. Add the source with Width 400, Height 800 (a starting point).
2. Position it where you want in the scene (drag to move, not resize).
3. If text is too small or too big, change `FONT_SIZE_PX` in the CONFIG and
   Refresh the source — repeat until it looks right.
4. If you need a wider/taller area, change the Width/Height in the source
   Properties (step A), not by dragging corners.

> **Tip:** to make the chat area taller/shorter without changing text size,
> adjust the Height in (A). To fit more/fewer lines on screen, also tune
> `MAX_MESSAGES` in the CONFIG.

### Quick size presets

`FONT_SIZE_PX` values are for the **default** font; with Teko, add about +6 since
it reads smaller.

| Use case | Size | `FONT_SIZE_PX` |
| --- | --- | --- |
| Narrow side-rail beside gameplay | 320 x 720 | 16 |
| Standard vertical overlay | 400 x 800 | 18 |
| Big, readable "just chatting" | 480 x 900 | 22 |

## Twitch Alerts & Channel Point Redeems (optional)

By default the feed shows **chat only**. You can also fold your Twitch **channel
point redemptions** and **alerts** — subs, resubs, gift subs, cheers (bits),
follows, raids, and hype trains — into the same feed, each as a colored row with
its own icon.

These don't travel over chat, so they use **Twitch EventSub** (a separate
connection) which needs a token for **your broadcaster account**. Unlike the chat
connection, this one takes a one-time setup — but it **auto-refreshes**, so once
configured it never expires mid-stream.

> You can only read events for the channel that **owns the token** — i.e. your own
> channel. You can't pull another streamer's redeems/subs.

### What shows up

| Event | Example row | Color |
| --- | --- | --- |
| Channel point redeem | `name redeemed` **Hydrate!** `◍500` | purple |
| Subscription | `name subscribed` **Tier 1** | red |
| Resub (with message) | `name resubscribed` **Tier 1** `· 6 months — message` | red |
| Gift sub | `name gifted` **5** `Tier 1 subs` | magenta |
| Cheer / bits | `name cheered` **500** `bits — message` | purple |
| Follow | `name followed` | blue |
| Raid | `name raided with` **48** `viewers` | amber |
| Hype train | `Hype Train started!` **Level 2** | orange |

Each type can be toggled independently — see the config keys below.

### One-time setup

1. **Register a Twitch app** at <https://dev.twitch.tv/console/apps> → *Register
   Your Application*.
   - **OAuth Redirect URL:** exactly `http://localhost`
   - **Category:** anything; **Client Type:** Confidential.
   - Copy the **Client ID**, then click **New Secret** and copy the **Client
     Secret**. (Already have a Twitch app? Reuse it — just make sure
     `http://localhost` is in its redirect URLs.)
2. Paste both into the CONFIG block and save:

   ```js
   TWITCH_CLIENT_ID     : "your-client-id",
   TWITCH_CLIENT_SECRET : "your-client-secret",
   TWITCH_REFRESH_TOKEN : "",   // filled in by the next step
   ```
3. **Get your refresh token** — open the file in a normal browser with `?setup`
   on the end:

   ```
   file:///D:/.../merged-chat.html?setup
   ```

   Click **Authorize with Twitch** (logged in as your broadcaster account), approve
   the permissions, then copy the `http://localhost/?code=…` address your browser
   lands on (that page failing to load is expected) and paste it back into the box.
   It hands you a **refresh token**.
4. Paste that into `TWITCH_REFRESH_TOKEN`, save, and Refresh the OBS source. The
   status box should read **`Alerts: watching <you> (8 event types)`**.

From then on the overlay refreshes its own token automatically — no more manual
steps, even across multi-hour streams.

> **Where the credentials live:** the Client Secret and refresh token sit in plain
> text in `merged-chat.html`, which is git-ignored — same as the YouTube API key.
> Don't screen-share or post that file.

### Config keys

| Setting | Default | Meaning |
| --- | --- | --- |
| `SHOW_REDEEMS` | `true` | Show channel point redemptions. |
| `SHOW_ALERTS.follows` | `true` | Show follows. |
| `SHOW_ALERTS.subs` | `true` | Show new subs + resubs (with message). |
| `SHOW_ALERTS.giftSubs` | `true` | Show gift subs. |
| `SHOW_ALERTS.cheers` | `true` | Show cheers (bits). |
| `SHOW_ALERTS.raids` | `true` | Show incoming raids. |
| `SHOW_ALERTS.hypeTrain` | `true` | Announce when a hype train starts. |
| `TWITCH_CLIENT_ID` | `""` | Your Twitch app's Client ID. |
| `TWITCH_CLIENT_SECRET` | `""` | Your Twitch app's Client Secret. |
| `TWITCH_REFRESH_TOKEN` | `""` | The refresh token from the `?setup` flow. |
| `TWITCH_CLIENT_ID_DOCK` | `""` | Second Twitch app's Client ID, used only with `?docked=true`. |
| `TWITCH_CLIENT_SECRET_DOCK` | `""` | Second Twitch app's Client Secret. |
| `TWITCH_REFRESH_TOKEN_DOCK` | `""` | Refresh token from `?setup&docked=true`. |

Turn a type off and Refresh — no re-setup needed (the token already carries every
scope). Set all of them off (or leave the token blank) to run chat-only as before.

### Alerts in a dock *and* on stream at the same time

> **[`relay.py`](#sharing-one-connection-between-every-view-relaypy) already
> handles this** — it holds the one EventSub session and feeds every page, so
> both views show every alert with a single Twitch app and no
> `?setup&docked=true` flow. Everything below only applies when you're running
> without the relay.

Twitch allows only **one** EventSub subscription per app + event type + channel.
So if the Browser **source** and the `?docked=true` **dock** share one Twitch app,
whichever connects first takes the alerts and the other reports
`Alerts: already claimed…` and shows no alerts. Chat itself is unaffected — this
is only about alerts/redeems.

To get alerts in both, give the dock its own Twitch app:

1. Register a **second** app at [dev.twitch.tv/console/apps](https://dev.twitch.tv/console/apps),
   Redirect URL `http://localhost`.
2. Paste its Client ID + Secret into `TWITCH_CLIENT_ID_DOCK` and
   `TWITCH_CLIENT_SECRET_DOCK`, and save.
3. Open the file with **`?setup&docked=true`** and run the two steps. The success
   page tells you to paste into `TWITCH_REFRESH_TOKEN_DOCK` — do that and save.
4. Refresh the dock. Its console logs
   `using dock Twitch app (own alert subscriptions)`.

All three `_DOCK` values must be filled in for the dock app to be used; if any is
blank the dock falls back to the main app (and loses the race to the source).

- **Leave them blank if you only want alerts on stream.** The dock still tries
  once at startup, gets told the subscriptions are taken, and then stops — it
  won't keep retrying or keep re-showing the status box.

### Notes & gotchas

- **Adding this to an existing redeems-only token:** if you set up channel points
  before alerts existed, your old token is missing the newer scopes. Just run
  `?setup` once more to re-grant them all — the status line nags you
  (`re-run ?setup to grant the rest`) until you do.
- **"Sound Alerts" extension:** sound redeems created with Twitch's official
  *Sound Alerts extension* may **not** appear — only channel point rewards from
  your dashboard (or tools like Streamer.bot) are guaranteed. Test one to be sure.
- **Follow spam:** if you ever get follow-botted, set `SHOW_ALERTS.follows` to
  `false` and Refresh.
- **Preview the styling:** set `DEMO_MODE : true` and Refresh — fake subs, cheers,
  raids, hype trains, follows, and redeems cycle through so you can check colors
  and layout without waiting for real events.

## Dark Background (`?bg=dark`)

The overlay is transparent by design so it composites cleanly over your video as
a Browser **source**. But if you load it as a docked panel (Browser dock), OBS
paints docks on **white**, which is too bright — so there's an opt-in dark
background.

To render on a dark background, add `?bg=dark` to the end of the file URL:

```
file:///D:/.../merged-chat.html?bg=dark
```

(You can also end the URL with `#dark` instead — same effect.)

- **Without** the flag: stays fully transparent (your normal stream overlay).
- **With** the flag: the page renders on a dark background (default `#2a2a2e`).
  Change the shade via `DARK_BG_COLOR` in CONFIG.

`?bg=dark` is **purely cosmetic and independent** of everything else — it's most
useful for a dock, but you can use it anywhere you want a solid backdrop (even on
stream). It does **not** affect which API key is used; that's the separate
`?docked=true` flag (see [Giving the dock its own API
quota](#giving-the-dock-its-own-api-quota-dockedtrue)).

**Why not use a color-key filter to fake transparency instead?** Don't — OBS
Browser sources already give true alpha transparency, so no key is needed on
stream. Color-keying a dark background would also eat the black text outlines and
any dark pixels in emotes/usernames, leaving crunchy, artifact-y edges. The
`?bg=dark` trick keeps the stream pixel-perfect while only the dock goes dark.

## Testing Without Your Own Stream

**Option 1 — test the real YouTube feed:** The API can read any public live
stream's chat. Find any live YouTube stream with chat enabled, copy its video ID
(the `v=...` part), paste it into `YT_VIDEO_ID`, and Refresh. Messages will flow
in using your API key. Put your own video ID back later.

**Option 2 — test the look with fake messages (no stream, no key):** In the
CONFIG set `DEMO_MODE : true` and Refresh. Fake Twitch + YouTube messages (with
the occasional MOD / broadcaster tag) appear every ~1.2s so you can check the
font, icons, fade-out, and layout. Fake **alerts and redeems** (subs, cheers,
raids, hype trains, follows, redemptions) also cycle through so you can preview
their colored rows. Set `DEMO_MODE` back to `false` before going live.

Demo mode lives in the relay, so **every open view shows the same fake feed** —
a Browser source and a dock stay in step, which is what makes it useful for
checking that a dock's layout matches the overlay.

1. Set `relay.demo=true` in `app.properties`.
2. Restart the relay (`start-relay.bat`).
3. Refresh the pages.

It generates fake Twitch and YouTube messages, role badges and alerts, and
spends **no** API quota — no keys are touched.

**Your own emotes show up.** The relay looks your channel's Twitch sub emotes up
on [ivr.fi](https://api.ivr.fi) (public, no auth, the only network call demo
makes) and weights them so they appear more often than the Twitch globals. Your
YouTube member emotes come from `youtube.emotes` in `app.properties`. So demo is
still the way to check that your emotes render at the right size. If ivr.fi is
unreachable it quietly falls back to globals only.

Set `relay.demo` back to `false` before going live.

> **Tip while testing:** set `STATUS_HIDE_SEC : 0` so the connection box stays on
> screen and you can confirm both platforms connected.

## Troubleshooting

The status box (top-left, when `SHOW_STATUS` is true) shows one line per platform
and reports exactly what each side is doing.

| Message | Meaning |
| --- | --- |
| `Twitch: connected to #name` | Twitch is working. |
| `YouTube: connected to <channel>` | YouTube is working. |
| `YouTube: no API key set` | Paste your key into CONFIG. |
| `YouTube: no active live chat` | The stream isn't live, or the video ID is wrong. YouTube only returns chat while the stream is actually LIVE. |
| `YouTube API: ...` / 403 errors | Key not enabled for YouTube Data API v3, or the key has an HTTP-referrer restriction (set restrictions to None). |
| `YouTube: quotaExceeded` | Daily API quota used up; resets at midnight US Pacific time. Add a backup key to keep going. |
| `YouTube: quota used up — switched to backup key 1/2` | Normal. The primary key drained and polling moved to a backup; chat continues uninterrupted. |
| `YouTube: all N API keys out of quota` | Every key is drained. Raise `YT_MIN_POLL_MS`, add another backup key, or wait for the midnight US Pacific reset. |
| `Twitch: connecting…` forever | Check the channel name is spelled correctly and lowercase. |
| `Alerts: watching <you> (N event types)` | Alerts/redeems are working (N = how many event types subscribed; 8 with everything on). |
| `Alerts: … re-run ?setup to grant the rest` | The token is missing some scopes — open `?setup` again and re-authorize. |
| `Redeems: refresh token invalid — re-run ?setup` | The Twitch alerts token is dead or from the wrong app/account — regenerate it via `?setup`. |
| `Redeems: off (open ?setup once to enable…)` | No Client ID / Secret / refresh token set — alerts are simply off (chat still works). |
| Twitch connected but no messages | Nobody has chatted yet, or `SHOW_BACKLOG` is false so only new messages show. |
| `Relay: connecting…` that never clears | `relay.py` isn't running, or it's on a different port than `RELAY_URL`. The page falls back to connecting directly after a moment. |
| Setting `DEMO_MODE : true` seems to do nothing | You're on an older copy. Current builds check `DEMO_MODE` before the relay; the console logs `DEMO_MODE is on — ignoring the relay`. |
| Another device can't load `http://<ip>:8777/` | `relay.host` is still `127.0.0.1`. Set it to `0.0.0.0` and restart — the relay prints the exact URL on startup. Also check both devices are on the same network. |
| `Relay: lost connection, reconnecting…` | The relay stopped or was restarted. It reconnects on its own within a few seconds. |
| Two views showing different chat | They aren't both on the relay. Check the relay window says `page connected (2 total)`, and that `RELAY_URL` is set in the HTML both are loading. |
| Dock shows nothing while the source works | The dock is a follower but the leader hasn't posted a row yet — followers only show what arrives after the leader renders it. Wait for the next message, or confirm the leader says it's sharing with 1 view. |
| Nothing appears at all | Right-click the OBS source → Refresh; confirm you picked the correct `.html` file. |

To test outside OBS: just double-click `merged-chat.html` to open it in your
browser. The Twitch side will connect live right away. Press F12 → Console to see
detailed log messages.

## Notes / Limits

- The YouTube stream must be **LIVE** for messages to come through.
- The YouTube Data API has a daily quota (10,000 units). Polling a single chat is
  fine for normal stream lengths; very long streams could exhaust it (chat would
  then stop until the quota resets at midnight US Pacific time).
- Text has a black outline baked in for readability over any video; the page
  background is transparent for OBS.
- The Teko font and Twitch/YouTube emotes load from the internet, so OBS needs an
  internet connection (it normally has one).
