# 🌻 One More Lawn Radio — Discord Bot

A private-server Discord music bot for the *One More Lawn* soundtrack. Uses `discord.py` and FFmpeg to play audio files stored in the local `music/` folder.

> **Rights:** Store and play only music you have permission to download and relay.

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
DEFAULT_VOLUME=0.35
```

Create a `music/` folder beside `bot.py` and place your authorized `.opus`, `.mp3`, `.m4a`, `.webm`, `.ogg`, `.flac`, or `.wav` files there. The bot scans the folder whenever radio, play, or search is used. The folder is gitignored; downloaded music is not uploaded to GitHub. `LAWN_PLAYLIST_URL` is no longer needed. `DISCORD_GUILD_ID` is optional but recommended for immediate slash-command updates.

Run:

```bash
python bot.py
```

## 3. Commands

| Command | Description |
| --- | --- |
| `/lawn radio` | Shuffle and enqueue local songs |
| `/lawn play query:<title>` | Queue the first matching track |
| `/lawn search query:<text>` | Search track titles |
| `/lawn queue` | Show current and next 10 tracks |
| `/lawn skip` | Skip current track |
| `/lawn loop mode:...` | Off, repeat track, or repeat playlist |
| `/lawn volume percent:35` | Adjust volume |
| `/lawn stop` | Stop, clear queue, disconnect |

Join a Discord voice channel before using `/lawn radio` or `/lawn play`. The local music folder is rescanned when radio, play, or search is used. This v1 is **one queue per server**, with no persistence across restarts.

## 4. Hosting

Run locally on your PC/Mac for initial testing, or on an always-on Linux VPS or Raspberry Pi for persistent radio. A hosting platform must support long-running processes, voice UDP traffic and FFmpeg. Do not use a request-only serverless function.

## Troubleshooting

- **Commands not showing:** Verify `applications.commands` invite scope, `DISCORD_GUILD_ID`, and restart the bot.
- **Cannot join voice:** Check Connect/Speak permissions.
- **FFmpeg not found:** Install FFmpeg and ensure `ffmpeg -version` works in your terminal.
- **No playable audio:** Confirm files exist in `music/` and FFmpeg can decode them (`ffplay music/your-song.opus`).
- **Bot offline:** Check `DISCORD_TOKEN`, Python dependencies and terminal logs.

Never commit your `.env` file or bot token.

### Silent voice playback (green speaking indicator)

On Windows, discord.py 2.7.1 with davey 0.2.0 produced silent voice playback even for a generated test tone. Downgrading to davey 0.1.4 restored audible test-tone playback. Keep the pinned version in requirements.txt until a newer combination is verified. If needed, run `python -m pip install -r requirements.txt` and `python -m pip check`.


## Experimental Parrot Mode (feature/parrot-mode only)

Keep the existing davey==0.1.4 pin. Voice receiving is experimental and requires a DAVE-capable receive extension. For a first test, use a separate virtual environment and install the community PR build:

```powershell
python -m pip install -r requirements.txt
python -m pip install --no-deps "git+https://github.com/imayhaveborkedit/discord-ext-voice-recv.git@6b9fb95"
python -m pip check
````

This is an experimental third-party patch, not a verified production release. Stop music with /lawn stop, then use /lawn echo member:@User. Only the selected human member can approve the request. The session echoes with a two-second delay for up to 60 seconds. Anyone can stop with /lawn echo-stop. Only selected-member PCM is buffered by the bot's echo sink, in RAM, with a bounded queue; nothing is written to disk. Music and echo cannot run concurrently. If the extension fails, switch back to main. Live voice reception has not yet been tested on Windows.
