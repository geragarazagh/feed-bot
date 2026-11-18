<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/icon-github-dark.png">
  <img src="docs/icon-github.png" width="128" height="128" alt="Feed icon">
</picture>

# Feed

Feed ([@FeedChannelsBot](https://t.me/FeedChannelsBot); «Лента» in Russian, «Стрічка» in Ukrainian) is a free,
open-source Telegram bot that sends the new posts of chosen public Telegram channels into one chat. Each post arrives
as its `t.me` link with Telegram's large preview card above it; tapping the card opens the post in its channel, with
its comments. The channels need not be joined, and the bot reads them without a Telegram account.

| | |
|---|---|
| Platform | Telegram, any client |
| Languages | English, Russian, Ukrainian (follows the Telegram app; changeable in Settings) |
| Limits | 50 channels per user; 60 channel checks per hour per user; 100 distinct channels for all users of this instance |
| Stored | Telegram user ID, language, two flags, channel usernames ([PRIVACY.md](PRIVACY.md)) |
| Server | Python 3.11+, one dependency (`httpx`), about 40 MB of memory |
| License | MIT |

## Use

- **Adding a channel.** The *Choose a Channel* button under the input field opens Telegram's own channel picker.
  A channel can also be added by its `@username`, a `t.me` link, or any forwarded post. One channel is added at once:
  the bot answers with the channel's latest post as a card and one line. A message with several channels, or posts
  from several channels forwarded together, opens a checklist instead: one button per channel, all ticked; a tap
  toggles a channel, *Done* adds the ticked ones. Up to 50 channels of a list are checked and all readable ones are shown; as many are ticked as still fit (50 per user), and *Done* refuses a selection larger than the room left. A pasted list longer than 50 is checked
  only in its first 50, and the rest is reported as not checked.
- `/channels` lists the channels, each with *Pause*/*Resume* and *Remove*.
- `/settings`: *Notifications* (off: posts arrive without sound) and *Language*.
- `/help`; `/stop` deletes the user's record after a confirmation, as does blocking the bot.

Only public channels whose posts Telegram shows on the web (`t.me/s/<channel>`) can be read; for the few channels
with that view off, the bot says so. A shared chat folder (`t.me/addlist/…`) cannot be used as a source: its web page
shows only the folder's name and the number of chats, and the list itself is available only to a Telegram account.
`KeyboardButtonRequestChat` selects one chat at a time (Bot API 10.4 has no multi-chat variant), which is why several
channels at once go through text, forwards and the checklist.

The bot explains itself once, on `/start`, and otherwise answers only what the user does; it sends no reminders.

## How it works

- **No Telegram account.** A bot cannot read channels it is not in, so channels are read from
  Telegram's public web view: `GET t.me/s/<channel>` once when a channel is added, then its
  "load newer" call, `POST t.me/s/<channel>?after=<id>` with `X-Requested-With: XMLHttpRequest`,
  which answers `""` (2 bytes) when nothing is new and up to 20 posts, oldest first, when something is.
- **One read per channel** serves all its readers. A channel that posted in the last 2 hours is read
  every 90 s, any other every 5 minutes. All channels' new posts go out in the order they were published.
- **A post is a card:** `sendMessage` with the post's `t.me` link and `link_preview_options`
  `{url, prefer_large_media: true, show_above_text: true}`. An album is one card, linked to its first part.
  Service posts (pins, new photo) are skipped.
- **Telegram's limits:** about one message a second per chat and under 30 a second overall; a flood
  wait is honoured.
- **Privacy:** [PRIVACY.md](PRIVACY.md). Kept: user id, language, two flags, channel usernames;
  per channel the newest post id, the time of the last post and the polling interval. No post content,
  no message logs. `/stop`, "Stop and block", or a 403 "blocked" from Telegram wipe the user at once.
- **A cap on channels.** Every read is a small HTTPS request, and on a free cloud VM outgoing traffic is
  the scarce thing (1 GB a month on Google Cloud's free e2-micro). `max_channels` caps the distinct
  channels across all users; past it new channels wait in a queue, and their readers are told why.

### Egress arithmetic (measured on the e2-micro)

Measured 2026-11-18 on the IPv6-only e2-micro (all of its internet egress is IPv6, `Ip6OutOctets`):

- one read on a warm keep-alive connection: ~420-485 bytes out (request, TLS record, TCP/IP headers, the
  ACK of the answer); a new TLS handshake adds ~2.1 KB, so reads share one connection;
- a quiet channel (read every 5 min): 8 760 reads ≈ 3.9 MB a month; an active one (every 90 s) ≈ 13 MB;
  with a third of its hours active, ≈ 6.7 MB;
- the rest (getUpdates long polling, status uploads, sends): roughly 50-80 MB a month;
- 34 real channels, early morning (33 quiet, 1 active), 15 min: 71.6 KB out for 106 reads, ≈ 206 MB a month.

So `max_channels` is 100: 100 × 6.7 MB + ~80 MB stays near 750 MB, under the free 1 GB with room for busy
days. A shorter `User-Agent` and no cookie saved ~15 % per read; HTTP/2 saved less and was left out.

## Running it

Built for a small always-on Linux server with systemd (a Google Cloud e2-micro, Debian 13, 1 GB RAM).
One Python process (`httpx` is the only dependency), about 40 MB of memory.

- **The bot token** is a [systemd credential](https://systemd.io/CREDENTIALS/) encrypted with the host
  key and the machine's TPM: systemd decrypts it for the service only.
- **Health.** The service pings systemd's watchdog only while updates arrive and polling rounds go on;
  otherwise systemd restarts it (`Restart=always`, also after crashes and reboots). Every 30 s it writes
  `/var/lib/feedbot/status.json` (numbers only) and, if `status_bucket` is set, every 15 minutes a public
  copy to Cloud Storage, so a monitor can read it without SSH.

### Install

On the server, as root:

```sh
install -d -m 0755 /etc/feedbot
cat > /etc/feedbot/config.json <<'JSON'
{
  "max_channels": 100,
  "ipv6_only": false,
  "status_bucket": ""
}
JSON
printf '%s' '123456:ABC-your-bot-token' |
  systemd-creds encrypt --with-key=host+tpm2 --name=token - /etc/feedbot/token.cred
sh deploy/install.sh      # venv in /opt/feedbot, user feedbot, systemd unit, starts the bot
```

On a machine without a TPM use `--with-key=host`. Set `ipv6_only` on a host that has IPv6 but no IPv4
route to the internet. Other settings and their defaults are in `tgfeed/config.py`.

From the admin's computer, for a Google Cloud VM reached through Identity-Aware Proxy:

```sh
VM=tgfeed ZONE=us-east1-b sh deploy/deploy.sh   # ship the current commit and reinstall
```

`deploy/gce-host.sh` is the one-time host tuning used on the e2-micro (TPM libraries, swap, automatic
reboots after security updates, a smaller journal).

The bot sets its own name, About, Description and command menu in each language at start. The avatar
is animated: `avatar/final/feed_a_800_30fps_bt601.mp4` (800 × 800, 30 fps, 2.4 s loop, resting on the cover at 0 s),
set once with `setMyProfilePhoto` as `InputProfilePhotoAnimated` with `main_frame_timestamp` 0; the chat list shows
its first frame, `avatar/final/cover.svg`. Frames: `avatar/final/src/render_a.py`, encoding: `enc.sh`. The video must
use the BT.601 matrix: Telegram cuts the still from it as BT.601, so a BT.709 video gets a washed-out avatar
(measured: #2AABEE came back as #34B1E7).

### Admin tool on the server

```sh
sudo -u feedbot feedbot-admin stats
sudo -u feedbot feedbot-admin channels          # every channel: readers, interval, last post
sudo -u feedbot feedbot-admin sub ID @a t.me/b  # give user ID channels, from their latest posts
sudo -u feedbot feedbot-admin user ID | unsub ID @a | wipe ID
journalctl -u feedbot -f                        # counts and errors only
```

## Development

```sh
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/python -m unittest discover -s tests -t .
```

## License

MIT
