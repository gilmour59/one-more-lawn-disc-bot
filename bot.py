"""One More Lawn radio: play locally stored audio in Discord voice."""
import asyncio
import os
import random
import threading
import time
from collections import deque
from dataclasses import dataclass, field

import discord
from discord import app_commands
from discord.ext import commands
try:
    from discord.ext import voice_recv
except ImportError:
    voice_recv = None
from dotenv import load_dotenv
import pathlib

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN", "")
MUSIC_DIR = pathlib.Path(__file__).resolve().parent / "music"
GUILD_ID = os.getenv("DISCORD_GUILD_ID", "").strip()
DEFAULT_VOLUME = max(0.0, min(1.0, float(os.getenv("DEFAULT_VOLUME", "0.35"))))
AUDIO_EXTENSIONS = {".opus", ".mp3", ".m4a", ".webm", ".ogg", ".flac", ".wav"}

@dataclass
class Track:
    title: str
    path: pathlib.Path

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
echo_sessions = {}
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
lawn = app_commands.Group(name="lawn", description="One More Lawn radio controls")

def player_for(guild_id):
    return players.setdefault(guild_id, Player())

def scan_music():
    if not MUSIC_DIR.is_dir():
        raise ValueError(f"Music folder not found: {MUSIC_DIR}. Create it and add audio files.")
    tracks = [
        Track(path.stem, path)
        for path in MUSIC_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
    ]
    return sorted(tracks, key=lambda track: track.title.casefold())


async def ensure_voice(interaction):
    if not interaction.guild or not isinstance(interaction.user, discord.Member) or not interaction.user.voice:
        raise ValueError("Join a voice channel first.")
    if interaction.guild_id in echo_sessions:
        raise ValueError('Stop echo mode before starting music.')
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
        if guild_id in echo_sessions:
            return
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
            print(f"[lawn] Starting: {track.title}", flush=True)
            source = discord.PCMVolumeTransformer(
                discord.FFmpegPCMAudio(str(track.path), options="-vn"), volume=p.volume
            )
            print(f"[lawn] Audio processes started for: {track.title}", flush=True)
            def after(error):
                if error:
                    print(f"[lawn] Discord playback error in {guild_id}: {error}", flush=True)
                else:
                    print(f"[lawn] Playback ended: {track.title}", flush=True)
                asyncio.run_coroutine_threadsafe(advance(guild_id, generation), bot.loop)
            vc.play(source, after=after)
        except Exception as exc:
            print(f"Cannot play {track.title}: {exc}")
            p.current = None
            # Avoid rapidly skipping the whole queue when playback setup fails.
            if p.text_channel:
                try:
                    await p.text_channel.send(f"⚠️ Could not start **{track.title}**: {str(exc)[:250]}")
                except discord.HTTPException:
                    pass

async def load_catalog(p):
    # Refresh each time so newly downloaded tracks appear without restarting.
    p.catalog = scan_music()
    if not p.catalog:
        raise ValueError(f"No audio files found in {MUSIC_DIR}. Download songs into music/ first.")
    return p.catalog

async def error_reply(interaction, exc):
    message = str(exc)
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)

@lawn.command(description="Start shuffled radio from local music folder")
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
    if interaction.guild_id in echo_sessions:
        return await interaction.response.send_message('Use /lawn echo-stop first.', ephemeral=True)
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
    await end_echo(interaction.guild_id)
    p.generation += 1
    p.queue.clear()
    p.current = None
    vc = interaction.guild.voice_client if interaction.guild else None
    if vc:
        await vc.disconnect(force=True)
    await interaction.response.send_message("🛑 Radio off. Go mow some grass.")


class EchoSource(discord.AudioSource):
    def __init__(self, member_id):
        self.member_id = member_id
        self.frames = deque(maxlen=150)
        self.lock = threading.Lock()
        self.closed = False

    def read(self):
        with self.lock:
            if self.closed:
                return b""
            now = time.monotonic()
            while self.frames and self.frames[0][0] < now - 1:
                self.frames.popleft()
            if self.frames and self.frames[0][0] <= now:
                return self.frames.popleft()[1]
        return bytes(3840)

    def cleanup(self):
        with self.lock:
            self.closed = True
            self.frames.clear()


if voice_recv is not None:
    class EchoSink(voice_recv.AudioSink):
        def __init__(self, source):
            super().__init__()
            self.source = source

        def wants_opus(self):
            return False

        def write(self, user, data):
            if user is None or user.id != self.source.member_id:
                return
            pcm = data.pcm
            if pcm and len(pcm) == 3840:
                with self.source.lock:
                    if not self.source.closed:
                        self.source.frames.append((time.monotonic() + 2, bytes(pcm)))

        def cleanup(self):
            pass


async def end_echo(guild_id):
    session = echo_sessions.pop(guild_id, None)
    if session is None:
        return False
    vc, source, channel, expiry = session
    source.cleanup()
    if expiry is not asyncio.current_task():
        expiry.cancel()
    if vc.is_listening():
        vc.stop_listening()
    if vc.is_playing() or vc.is_paused():
        vc.stop()
    try:
        await vc.disconnect(force=True)
    finally:
        try:
            await channel.send("🦜 Echo mode stopped. Audio buffer cleared.")
        except discord.HTTPException:
            pass
    return True


class EchoConsent(discord.ui.View):
    def __init__(self, member_id, channel_id, requester_id):
        super().__init__(timeout=60)
        self.member_id = member_id
        self.channel_id = channel_id
        self.requester_id = requester_id

    @discord.ui.button(label="Allow echo for 60 seconds", style=discord.ButtonStyle.success)
    async def accept(self, interaction, button):
        if interaction.user.id != self.member_id:
            return await interaction.response.send_message("Only the selected member can accept.", ephemeral=True)
        self.stop()
        await interaction.response.edit_message(content="Echo approved. Connecting...", view=None)
        guild = interaction.guild
        p = player_for(guild.id)
        async with p.lock:
            member = guild.get_member(self.member_id)
            requester = guild.get_member(self.requester_id)
            if not member or not member.voice or member.voice.channel.id != self.channel_id or not requester or not requester.voice or requester.voice.channel.id != self.channel_id:
                return await interaction.followup.send("Both members must still be in the original voice channel.")
            if guild.id in echo_sessions or guild.voice_client or p.queue or p.current:
                return await interaction.followup.send("Stop the existing voice session with /lawn stop first.")
            source = EchoSource(self.member_id)
            vc = None
            try:
                await interaction.followup.send(f"🦜 Echo active for {member.mention} for up to 60 seconds. Use /lawn echo-stop to end it. Only the selected member's audio is buffered.")
                vc = await member.voice.channel.connect(cls=voice_recv.VoiceRecvClient, timeout=20)
                if not member.voice or member.voice.channel.id != self.channel_id:
                    raise ValueError("Selected member left the channel.")
                async def expire():
                    await asyncio.sleep(60)
                    await end_echo(guild.id)
                expiry = asyncio.create_task(expire())
                echo_sessions[guild.id] = (vc, source, interaction.channel, expiry)
                vc.listen(EchoSink(source))
                vc.play(source)
            except Exception as exc:
                source.cleanup()
                if guild.id in echo_sessions:
                    await end_echo(guild.id)
                elif vc:
                    await vc.disconnect(force=True)
                await interaction.followup.send(f"Echo could not start: {exc}")

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.secondary)
    async def decline(self, interaction, button):
        if interaction.user.id != self.member_id:
            return await interaction.response.send_message("Only the selected member can decline.", ephemeral=True)
        self.stop()
        await interaction.response.edit_message(content="Echo request declined.", view=None)


@lawn.command(description="Request consent to echo a member with a two-second delay")
async def echo(interaction: discord.Interaction, member: discord.Member):
    if voice_recv is None:
        return await interaction.response.send_message("Experimental voice receive extension is not installed.", ephemeral=True)
    if not interaction.guild or not isinstance(interaction.user, discord.Member) or not interaction.user.voice or not member.voice or member.voice.channel != interaction.user.voice.channel or member.bot:
        return await interaction.response.send_message("Select a human member in your voice channel.", ephemeral=True)
    if interaction.guild.voice_client or interaction.guild_id in echo_sessions:
        return await interaction.response.send_message("Use /lawn stop before requesting echo.", ephemeral=True)
    await interaction.response.send_message(f"{member.mention}, allow Jerem to echo your voice in this channel for 60 seconds? Audio is buffered in memory only. You can stop at any time with /lawn echo-stop.", view=EchoConsent(member.id, member.voice.channel.id, interaction.user.id))


@lawn.command(name="echo-stop", description="Stop echo mode and discard buffered audio")
async def echo_stop(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    stopped = await end_echo(interaction.guild_id)
    await interaction.followup.send("Echo stopped." if stopped else "No echo session is active.", ephemeral=True)


@bot.event
async def on_voice_state_update(member, before, after):
    session = echo_sessions.get(member.guild.id)
    if session is None:
        return
    vc, source, _, _ = session
    if member.id in (source.member_id, bot.user.id) and after.channel != vc.channel:
        await end_echo(member.guild.id)
    elif member.id == source.member_id and (after.self_mute or after.mute):
        await end_echo(member.guild.id)


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
