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
| `README.md` | This file. |

> **Note:** `merged-chat.html` is git-ignored because it holds your private API
> key. Share `merged-chat-example.html` instead.

## How It Works (why it needs what it needs)

- **Twitch:** connects anonymously over WebSocket (IRC). No account, no key.
  Works immediately.
- **YouTube:** live chat **cannot** be read from an iframe (cross-origin), so it
  uses the YouTube Data API v3, which requires a free API key tied to a Google
  account. Without the key, the Twitch half still works; the YouTube half stays
  empty.
- Both work from a plain `file://` page, so **no** local web server is needed.

## Visual Features (what you'll see)

- Platform logo badge on every message (Twitch / YouTube).
- Broadcaster gets a small video-camera icon on a gold tag (works for both the
  Twitch broadcaster and the YouTube channel owner).
- Moderators get a green **MOD** tag.
- Usernames are colored: Twitch uses each chatter's own color; everyone else
  gets a stable auto-generated color from their name.
- Twitch emotes are rendered as images.
- New messages pop in with a quick animation.
- All text has a black outline so it stays readable over any video, and the page
  background is transparent for OBS.
- Connection status box (top-left) shows one line per platform, e.g.:

  ```
  Twitch: connected to #yourchannel
  YouTube: connected to Your Channel Name
  ```

  It auto-hides after a few seconds (configurable — see `STATUS_HIDE_SEC`).

## Step 1 — Edit the Config (top of `merged-chat.html`)

Open `merged-chat.html` in a text editor (right-click → Edit, or open with
Notepad). Near the top, find the CONFIG block.

### Required — who to connect to

| Setting | Value |
| --- | --- |
| `TWITCH_CHANNEL` | `"your_channel"` — your twitch channel (lowercase) |
| `YT_VIDEO_ID` | `"VIDEO_ID"` — the `v=...` id from the youtube URL |
| `YT_API_KEY` | `"YOUR_API_KEY"` — paste your YouTube Data API key |

- The YouTube video ID is the part after `v=` in the watch / live_chat URL.
  Example: `https://www.youtube.com/live_chat?is_popout=1&v=VIDEO_ID` → the ID is
  the `VIDEO_ID` part.
- Leave `TWITCH_CHANNEL` blank (`""`) to run YouTube only, or leave the YouTube
  fields blank to run Twitch only.

### Optional — appearance & behavior

| Setting | Default | Meaning |
| --- | --- | --- |
| `MAX_MESSAGES` | `80` | How many lines stay on screen at once. |
| `SHOW_BACKLOG` | `false` | `false` = only show new messages after load (recommended). `true` = also show recent messages that already existed when it loaded. |
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

## Dark Background for an OBS Dock

The overlay is transparent by design so it composites cleanly over your video as
a Browser **source**. But if you also load it as a docked panel (Browser dock),
OBS paints docks on **white**, which is too bright.

To get a dark background in the **dock only**, add `?bg=dark` to the end of the
file URL:

```
file:///D:/.../merged-chat.html?bg=dark
```

(You can also end the URL with `#dark` instead — same effect.)

- **Without** the flag (your normal stream Browser source): stays fully
  transparent. Nothing changes for the on-stream overlay.
- **With** the flag (the dock): the page renders on a dark background (default
  `#2a2a2e`). Change the shade via `DARK_BG_COLOR` in CONFIG.

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
font, icons, fade-out, and layout. Set `DEMO_MODE` back to `false` before going
live.

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
| `YouTube: quotaExceeded` | Daily API quota used up; resets at midnight US Pacific time. |
| `Twitch: connecting…` forever | Check the channel name is spelled correctly and lowercase. |
| Twitch connected but no messages | Nobody has chatted yet, or `SHOW_BACKLOG` is false so only new messages show. |
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
