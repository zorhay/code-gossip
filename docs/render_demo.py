#!/usr/bin/env python3
"""Render one coding scenario using the Senior voice profile.
Requires Pillow, FFmpeg, and an installed Kokoro environment.
Does not change installed preferences. DEMO_KOKORO_PYTHON overrides the speech interpreter.

Run from any directory: python3 docs/render_demo.py
Outputs: docs/assets/demo.mp4 (with audio), demo.gif (silent preview).
"""
from array import array
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import wave

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/assets'
W, H, FPS, SECONDS, RATE = 1280, 720, 24, 12, 48000
INTRO_SECONDS = .5
STEP_SECONDS = 2.3
PHRASES = json.loads((ROOT / "code-gossip/configs/phrases.defaults.json").read_text())
DEFAULTS = json.loads((ROOT / "code-gossip/configs/config.defaults.json").read_text())
VOICE = os.environ.get("DEMO_VOICE", DEFAULTS["kokoro_voice"])
# Fixed choices from the shipped Senior phrases make the scenario reproducible.
EVENTS = [
    ('search', 'Locate the timeout logic', PHRASES['search'][5]),
    ('edit', 'Fix the expiry check', PHRASES['edit'][3]),
    ('test', 'Run the auth tests', PHRASES['test'][1]),
    ('git_commit', 'Commit the fix', PHRASES['git_commit'][1]),
    ('stop', 'Hand back for review', PHRASES['stop'][4]),
]
BG, PANEL, LINE = '#0C141E', '#14202E', '#2A3C4D'
WHITE, MUTED, GREEN, ORANGE = '#F0F5F8', '#91A6BB', '#A5F3CB', '#FFBC7C'


def font(size, bold=False):
    custom = os.environ.get('DEMO_FONT_BOLD' if bold else 'DEMO_FONT')
    choices = [custom] if custom else []
    choices += [
        '/System/Library/Fonts/Supplemental/Arial Bold.ttf' if bold else '/System/Library/Fonts/Supplemental/Arial.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    ]
    for path in choices:
        if path and Path(path).is_file():
            return ImageFont.truetype(path, size)
    raise SystemExit('Set DEMO_FONT and DEMO_FONT_BOLD to installed TTF font paths.')


FONTS = {size: font(size) for size in (16, 18, 20, 22, 24)}
BOLD = {size: font(size, True) for size in (20, 26, 30, 36, 52)}


def audio_track():
    samples = array('h', [0]) * (SECONDS * RATE)
    with tempfile.TemporaryDirectory(prefix='code-gossip-senior-') as temp:
        python = os.environ.get('DEMO_KOKORO_PYTHON', str(ROOT / 'code-gossip/state/.venv/bin/python'))
        if not Path(python).is_file():
            raise SystemExit('Install Kokoro first, or set DEMO_KOKORO_PYTHON to its Python interpreter.')
        # Load the speech model once, then synthesize the shipped Senior phrases.
        synthesize = """
import json, sys
from pathlib import Path
import numpy as np
import soundfile as sf
from kokoro import KPipeline
request = json.load(sys.stdin)
voice = request['voice']
pipeline = KPipeline(lang_code='b' if voice.startswith('b') else 'a', repo_id='hexgrad/Kokoro-82M')
for event, phrase in request['phrases']:
    chunks = [audio.numpy() for _, _, audio in pipeline(phrase, voice=voice, speed=1.12) if audio is not None]
    if not chunks:
        raise RuntimeError('No Kokoro speech for ' + event)
    sf.write(Path(request['directory']) / (event + '.wav'), np.concatenate(chunks), 24000)
"""
        subprocess.run([python, '-c', synthesize], input=json.dumps({
            'directory': temp, 'voice': VOICE,
            'phrases': [(event, phrase) for event, _action, phrase in EVENTS],
        }), text=True, check=True)
        for index, (event, _action, phrase) in enumerate(EVENTS):
            clip_path = Path(temp) / f'{event}.wav'
            raw = subprocess.check_output([
                'ffmpeg', '-v', 'error', '-i', str(clip_path),
                '-f', 's16le', '-ar', str(RATE), '-ac', '1', '-'])
            clip = array('h'); clip.frombytes(raw)
            if not clip or max(abs(v) for v in clip) < 100:
                raise SystemExit(f'No speech generated for {event}; check the Kokoro {VOICE} voice.')
            if len(clip) >= (STEP_SECONDS - .15) * RATE:
                raise SystemExit(f'The {event} phrase exceeds its scene; increase STEP_SECONDS and SECONDS.')
            offset = int((INTRO_SECONDS + index * STEP_SECONDS) * RATE)
            samples[offset:offset + len(clip)] = clip
    return samples


def draw_quote(draw, text, y):
    words = ('“' + text + '”').split()
    line = ''
    for word in words:
        candidate = (line + ' ' + word).strip()
        if draw.textlength(candidate, font=BOLD[30]) > 402 and line:
            draw.text((790, y), line, font=BOLD[30], fill=WHITE)
            y += 40
            line = word
        else:
            line = candidate
    draw.text((790, y), line, font=BOLD[30], fill=WHITE)


def frame(t, audio):
    image = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(image)
    active = min(4, int((t - INTRO_SECONDS) / STEP_SECONDS)) if t >= INTRO_SECONDS else -1
    d.text((56, 32), 'CODE GOSSIP', font=BOLD[20], fill=GREEN)
    d.text((1090, 32), 'SENIOR', font=FONTS[18], fill=ORANGE)
    d.text((56, 78), 'Fix the login timeout.', font=BOLD[52], fill=WHITE)
    d.text((58, 150), 'One bug fix. From the first search to the handoff.', font=FONTS[22], fill=MUTED)
    d.text((60, 214), '01   THE EVENT', font=BOLD[20], fill=MUTED)
    d.text((780, 214), '02   THE VOICE', font=BOLD[20], fill=MUTED)
    for i, (event, title, _phrase) in enumerate(EVENTS):
        y = 256 + i * 65
        current = i == active
        d.rounded_rectangle((56, y, 690, y + 56), radius=12,
                            fill='#203B39' if current else PANEL,
                            outline=GREEN if current else LINE, width=2 if current else 1)
        d.ellipse((76, y + 20, 90, y + 34), fill=GREEN if i <= active else LINE)
        d.text((110, y + 12), title, font=BOLD[26] if current else FONTS[24], fill=WHITE if current else MUTED)
        box = d.textbbox((0, 0), event, font=FONTS[18])
        d.text((670 - (box[2] - box[0]), y + 19), event, font=FONTS[18], fill=GREEN if current else MUTED)
    d.rounded_rectangle((762, 256, 1224, 572), radius=18, fill=PANEL, outline=LINE)
    d.text((790, 282), f'KOKORO  /  {VOICE.upper()}', font=FONTS[18], fill=GREEN)
    sound = EVENTS[active][2] if active >= 0 else 'Listen for the cue'
    draw_quote(d, sound, 336)
    start = int(t * RATE)
    window = audio[start:start + RATE // FPS]
    rms = math.sqrt(sum(v * v for v in window) / max(1, len(window))) / 32768
    level = min(1, rms * 9)
    for b in range(31):
        height = 8 + int(96 * level * (0.35 + 0.65 * abs(math.sin(b * 0.83 + t * 9))))
        x = 791 + b * 13
        d.rounded_rectangle((x, 458 - height / 2, x + 6, 458 + height / 2), radius=3,
                            fill=GREEN if level > 0.015 else LINE)
    d.text((790, 529), 'Shipped phrases. Real speech.', font=FONTS[18], fill=MUTED)
    if active >= 0:
        phase = min(1, max(0, (t - (INTRO_SECONDS + active * STEP_SECONDS)) / .3))
        source_y = 284 + active * 65
        d.line((704, source_y, 748, 416), fill=LINE, width=2)
        dot_y = source_y + phase * (416 - source_y)
        d.ellipse((700 + phase * 41, dot_y - 4, 708 + phase * 41, dot_y + 4), fill=GREEN)
    d.line((56, 618, 1224, 618), fill=LINE, width=2)
    d.line((56, 618, 56 + int(1168 * t / SECONDS), 618), fill=GREEN, width=3)
    d.text((56, 649), 'Illustrated scenario. Fixed phrases, no LLM.', font=FONTS[22], fill=WHITE)
    d.text((1008, 652), 'code-gossip  /  macOS', font=FONTS[18], fill=MUTED)
    return image


def main():
    for binary in ('ffmpeg', 'ffprobe'):
        if not shutil.which(binary):
            raise SystemExit(f'{binary} is required; install FFmpeg.')
    OUT.mkdir(parents=True, exist_ok=True)
    audio = audio_track()
    with tempfile.TemporaryDirectory(prefix='code-gossip-demo-') as temp:
        track = Path(temp) / 'audio.wav'
        with wave.open(str(track), 'wb') as stream:
            stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(RATE)
            stream.writeframes(audio.tobytes())
        encoder = subprocess.Popen([
            'ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
            '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-', '-i', str(track),
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23', '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', '-shortest',
            str(OUT / 'demo.mp4')], stdin=subprocess.PIPE)
        try:
            for i in range(SECONDS * FPS):
                encoder.stdin.write(frame(i / FPS, audio).tobytes())
        finally:
            encoder.stdin.close()
        if encoder.wait() != 0:
            raise SystemExit('Video encoding failed.')
        subprocess.run([
            'ffmpeg', '-v', 'error', '-y', '-i', str(OUT / 'demo.mp4'),
            '-filter_complex', 'fps=8,scale=800:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=bayer',
            '-loop', '0', str(OUT / 'demo.gif')], check=True)
    print('Rendered demo.mp4 with audio and silent demo.gif preview.')


if __name__ == '__main__':
    main()
