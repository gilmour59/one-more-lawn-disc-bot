# 🌻 One More Lawn Radio — Discord Bot

A private-server Discord music bot for the *One More Lawn* soundtrack. Uses `discord.py`, `yt-dlp` and FFmpeg to stream audio URLs without permanently downloading MP3s.

> **Rights and reliability:** Use only streams you are authorized to relay. Non-commercial use does not automatically grant permission to rebroadcast YouTube audio. YouTube may block extraction or change formats, and playback may stop working.

## 1. Create a Discord bot

1. Visit https://discord.com/developers/applications and create an application.
2. Open **Bot**, generate a token and keep it private.
3. Under **OAuth2 → URL Generator**, select `bot` and `applications.commands`.
4. Grant **View Channels**, **Send Messages**, **Connect**, and **Speak**. Invite the bot to your server.
5. The bot uses slash commands, so **Message Content Intent is not required**.

## 2. Install dependencies

Install **Python 3.11+** and **FFmpeg**.

- macOS: `brew install ffmpeg`
- Windows: `winget install Gyan.FFmpeg` (restart terminal afterwards)
- Ubuntu/Debian: `sudo apt update && sudo apt install ffmpeg`

Then:

```bash
git clone https://github.com/gilmour59/one-more-lawn-disc-bot.git
cd one-more-lawn-disc-bot
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env   # Windows: copy .env.example .env
```

Edit `.env`:

```dotenv
DISCORD_TOKEN=your_secret_token
DISCORD_GUILD_ID=your_test_server_id
LAWN_PLAYLIST_URL=https://www.youtube.com/playlist?list=YOUR_AUTHORIZED_PLAYLIST
DEFAULT_VOLUME=0.35
```

Use a **playlist URL** containing the soundtrack, not a `watch?v=...&list=RD...` auto-generated YouTube radio link. A normal YouTube playlist is more predictable. `DISCORD_GUILD_ID` is optional but recommended for immediate slash-command updates in your test server.

Run:

```bash
python bot.py
```

## 3. Commands

| Command | Description |
| --- | --- |
| `/lawn radio` | Shuffle and enqueue the configured playlist |
| `/lawn play query:<title>` | Queue the first matching track |
| `/lawn search query:<text>` | Search track titles |
| `/lawn queue` | Show current and next 10 tracks |
| `/lawn skip` | Skip current track |
| `/lawn loop mode:...` | Off, repeat track, or repeat playlist |
| `/lawn volume percent:35` | Adjust volume |
| `/lawn stop` | Stop, clear queue, disconnect |

Join a Discord voice channel before using `/lawn radio` or `/lawn play`. The playlist is fetched when first used and cached in memory. This v1 is **one queue per server**, with no persistence across restarts.

## 4. Hosting

Run locally on your PC/Mac for initial testing, or on an always-on Linux VPS or Raspberry Pi for persistent radio. A hosting platform must support long-running processes, voice UDP traffic and FFmpeg. Do not use a request-only serverless function.

## Troubleshooting

- **Commands not showing:** Verify `applications.commands` invite scope, `DISCORD_GUILD_ID`, and restart the bot.
- **Cannot join voice:** Check Connect/Speak permissions.
- **FFmpeg not found:** Install FFmpeg and ensure `ffmpeg -version` works in your terminal.
- **No playable audio:** Verify playlist accessibility, permissions and up-to-date `yt-dlp`. YouTube may block or throttle automated streams.
- **Bot offline:** Check `DISCORD_TOKEN`, Python dependencies and terminal logs.

Never commit your `.env` file or bot token.