"""One More Lawn radio: Discord voice bot, streaming public YouTube URLs where authorized."""
import asyncio
import os
import random
from collections import deque
from dataclasses import dataclass, field

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import yt_dlp

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN", "")
PLAYLIST = os.getenv("LAWN_PLAYLIST_URL", "")
GUILD_ID = os.getenv("DISCORD_GUILD_ID", "").strip()
DEFAULT_VOLUME = max(0.0, min(1.0, float(os.getenv("DEFAULT_VOLUME", "0.35"))))
YDL = {"quiet": True, "no_warnings": True, "extract_flat": "in_playlist", "ignoreerrors": True, "noplaylist": False}
STREAM_YDL = {"quiet": True, "no_warnings": True, "format": "bestaudio/best", "noplaylist": True, "skip_download": True}
FFMPEG_BEFORE = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"

@dataclass
class Track:
    title: str
    url: str

@dataclass
class Player:
    queue: deque = field(default_factory=deque)
    catalog: list = field(default_factory=list)
    current: Track | None = None
    loop: str = "off"
    volume: float = DEFAULT_VOLUME
    text_channel: object = None
    generation: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

players: dict[int, Player] = {}
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
lawn = app_commands.Group(name="lawn", description="One More Lawn radio controls")

def player_for(guild_id):
    return players.setdefault(guild_id, Player())

def extract_playlist(url):
    with yt_dlp.YoutubeDL(YDL) as ydl:
        data = ydl.extract_info(url, download=False)
    if not data:
        return []
    entries = data.get("entries") or [data]
    result = []
    for e in entries:
        if not e:
            continue
        link = e.get("webpage_url") or e.get("url") or ""
        if link and not link.startswith("http"):
            link = "https://www.youtube.com/watch?v=" + link
        if link.startswith("http"):
            result.append(Track(e.get("title") or "Unknown track", link))
    return result

def extract_stream(url):
    with yt_dlp.YoutubeDL(STREAM_YDL) as ydl:
        data = ydl.extract_info(url, download=False)
    if "entries" in data:
        data = next((e for e in data["entries"] if e), None)
    if not data or not data.get("url"):
        raise RuntimeError("No playable audio stream found")
    return data["url"]

async def ensure_voice(interaction):
    if not interaction.guild or not isinstance(interaction.user, discord.Member) or not interaction.user.voice:
        raise ValueError("Join a voice channel first.")
    target = interaction.user.voice.channel
    vc = interaction.guild.voice_client
    if vc and vc.channel != target:
        await vc.move_to(target)
    elif not vc:
        vc = await target.connect(timeout=20, reconnect=True)
    return vc

async def advance(guild_id, expected_generation=None):
    p = player_for(guild_id)
    async with p.lock:
        if expected_generation is not None and expected_generation != p.generation:
            return
        guild = bot.get_guild(guild_id)
        vc = guild.voice_client if guild else None
        if not vc or not vc.is_connected():
            return
        if vc.is_playing() or vc.is_paused():
            return
        if p.current and p.loop == "one":
            track = p.current
        else:
            if p.current and p.loop == "all":
                p.queue.append(p.current)
            if not p.queue:
                p.current = None
                return
            track = p.queue.popleft()
            p.current = track
        p.generation += 1
        generation = p.generation
        try:
            stream = await asyncio.to_thread(extract_stream, track.url)
            source = discord.PCMVolumeTransformer(
                discord.FFmpegPCMAudio(stream, before_options=FFMPEG_BEFORE, options="-vn"),
                volume=p.volume,
            )
            def after(error):
                if error:
                    print(f"Playback error in {guild_id}: {error}")
                asyncio.run_coroutine_threadsafe(advance(guild_id, generation), bot.loop)
            vc.play(source, after=after)
        except Exception as exc:
            print(f"Cannot play {track.title}: {exc}")
            p.current = None
            asyncio.create_task(advance(guild_id, generation))

async def load_catalog(p):
    if not PLAYLIST:
        raise ValueError("Set LAWN_PLAYLIST_URL in your .env first.")
    if not p.catalog:
        p.catalog = await asyncio.to_thread(extract_playlist, PLAYLIST)
    if not p.catalog:
        raise ValueError("The playlist has no accessible tracks.")
    return p.catalog

async def error_reply(interaction, exc):
    message = str(exc)
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)

@lawn.command(description="Start shuffled radio from the configured playlist")
@app_commands.checks.cooldown(1, 5.0, key=lambda i: (i.guild_id, i.user.id))
async def radio(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        vc = await ensure_voice(interaction)
        p = player_for(interaction.guild_id)
        catalog = await load_catalog(p)
        tracks = catalog.copy()
        random.shuffle(tracks)
        p.queue.extend(tracks)
        p.text_channel = interaction.channel
        await interaction.followup.send(f"🌻 Radio queued **{len(tracks)}** songs!")
        if not vc.is_playing() and not vc.is_paused():
            await advance(interaction.guild_id)
    except Exception as exc:
        await error_reply(interaction, exc)

@lawn.command(description="Search the catalog and queue a matching track")
@app_commands.describe(query="Part of a song title")
async def play(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    try:
        vc = await ensure_voice(interaction)
        p = player_for(interaction.guild_id)
        catalog = await load_catalog(p)
        matches = [t for t in catalog if query.casefold() in t.title.casefold()]
        if not matches:
            return await interaction.followup.send("No matching song. Try /lawn search.")
        track = matches[0]
        p.queue.append(track)
        await interaction.followup.send(f"🌱 Queued **{track.title}**")
        if not vc.is_playing() and not vc.is_paused():
            await advance(interaction.guild_id)
    except Exception as exc:
        await error_reply(interaction, exc)

@lawn.command(description="Find songs by title")
async def search(interaction: discord.Interaction, query: str):
    await interaction.response.defer(ephemeral=True)
    try:
        catalog = await load_catalog(player_for(interaction.guild_id))
        matches = [t.title for t in catalog if query.casefold() in t.title.casefold()]
        await interaction.followup.send("\n".join(matches[:15])[:1900] if matches else "No matches.", ephemeral=True)
    except Exception as exc:
        await error_reply(interaction, exc)

@lawn.command(description="Show the current song and upcoming queue")
async def queue(interaction: discord.Interaction):
    p = player_for(interaction.guild_id)
    upcoming = list(p.queue)[:10]
    text = f"🎵 Now: **{p.current.title if p.current else 'Nothing'}**\n"
    text += "\n".join(f"{i}. {t.title}" for i, t in enumerate(upcoming, 1)) or "Queue empty."
    await interaction.response.send_message(text[:1900])

@lawn.command(description="Skip the current track")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client if interaction.guild else None
    if not vc or not vc.is_playing():
        return await interaction.response.send_message("Nothing playing.", ephemeral=True)
    p = player_for(interaction.guild_id)
    if p.loop == "one":
        p.current = None
    vc.stop()
    await interaction.response.send_message("⏭️ Skipped!")

@lawn.command(description="Set repeat mode")
@app_commands.choices(mode=[
    app_commands.Choice(name="Off", value="off"),
    app_commands.Choice(name="Repeat current track", value="one"),
    app_commands.Choice(name="Repeat playlist", value="all"),
])
async def loop(interaction: discord.Interaction, mode: app_commands.Choice[str]):
    p = player_for(interaction.guild_id)
    p.loop = mode.value
    await interaction.response.send_message(f"🔁 Loop: **{mode.name}**")

@lawn.command(description="Set volume from 0 to 100 percent")
async def volume(interaction: discord.Interaction, percent: app_commands.Range[int, 0, 100]):
    p = player_for(interaction.guild_id)
    p.volume = percent / 100
    vc = interaction.guild.voice_client if interaction.guild else None
    if vc and isinstance(vc.source, discord.PCMVolumeTransformer):
        vc.source.volume = p.volume
    await interaction.response.send_message(f"🔊 Volume: {percent}%")

@lawn.command(description="Stop music, clear queue and disconnect")
async def stop(interaction: discord.Interaction):
    p = player_for(interaction.guild_id)
    p.generation += 1
    p.queue.clear()
    p.current = None
    vc = interaction.guild.voice_client if interaction.guild else None
    if vc:
        await vc.disconnect(force=True)
    await interaction.response.send_message("🛑 Radio off. Go mow some grass.")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.event
async def setup_hook():
    bot.tree.add_command(lawn)
    if GUILD_ID:
        guild = discord.Object(id=int(GUILD_ID))
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
    else:
        await bot.tree.sync()

@lawn.error
async def lawn_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    await error_reply(interaction, getattr(error, "original", error))

if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Missing DISCORD_TOKEN in .env")
    bot.run(TOKEN)
