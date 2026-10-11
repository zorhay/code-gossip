#!/usr/bin/env python3
"""Render one coding scenario as Default effects, AI narration, and Senior cues.
Requires Pillow, FFmpeg, and an installed Kokoro environment.
Does not change installed preferences. DEMO_KOKORO_PYTHON overrides the speech interpreter.

Run from the checkout: python3 docs/render_demo.py
Use --profiles default narrator to render a subset.
Outputs: docs/assets/demo[-default|-narrator].mp4 and compact silent GIF previews.
"""
import argparse
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
W, H, FPS, RATE = 1280, 720, 24, 48000
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
MANIFEST = json.loads((ROOT / 'code-gossip/data/sounds.json').read_text())
NARRATION = json.loads((ROOT / 'docs/demo-narration.json').read_text())['phrases']
PROFILES = {
    'default': {
        'badge': 'DEFAULT', 'label': 'DEFAULT / EFFECTS', 'output': 'THE SOUND',
        'engine': 'MACOS SYSTEM SOUNDS', 'note': 'Shipped Default sound mappings.',
        'footer': 'Illustrated scenario. Sound effects, no speech.',
        'stem': 'demo-default', 'step': 2.3, 'accent': '#91C7FF',
    },
    'narrator': {
        'badge': 'NARRATOR', 'label': 'LLM NARRATOR', 'output': 'THE COMMENTARY',
        'engine': f'KOKORO  /  {VOICE.upper()}', 'note': 'AI-written, voiced with Kokoro.',
        'footer': 'Illustrated scenario. AI commentary prepared for this demo.',
        'stem': 'demo-narrator', 'step': 3.1, 'accent': '#FFBC7C',
    },
    'senior': {
        'badge': 'SENIOR', 'label': 'SENIOR / VOICE', 'output': 'THE VOICE',
        'engine': f'KOKORO  /  {VOICE.upper()}', 'note': 'Shipped phrases. Real speech.',
        'footer': 'Illustrated scenario. Fixed phrases, no LLM.',
        'stem': 'demo', 'step': STEP_SECONDS, 'accent': '#A5F3CB',
    },
}


def duration(profile):
    return INTRO_SECONDS + len(EVENTS) * PROFILES[profile]['step']


def cue(profile, index):
    event, _action, phrase = EVENTS[index]
    if profile == 'default':
        return Path(MANIFEST['effects']['default']['events'][event]['file']).stem
    return NARRATION[event] if profile == 'narrator' else phrase


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


def audio_track(profile):
    samples = array('h', [0]) * round(duration(profile) * RATE)
    with tempfile.TemporaryDirectory(prefix='code-gossip-demo-audio-') as temp:
        if profile != 'default':
            python = os.environ.get('DEMO_KOKORO_PYTHON', str(ROOT / 'code-gossip/state/.venv/bin/python'))
            if not Path(python).is_file():
                raise SystemExit('Install Kokoro first, or set DEMO_KOKORO_PYTHON to its Python interpreter.')
            # These AI-written demo lines are stored locally; regeneration makes no LLM call.
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
                'phrases': [(event, cue(profile, i)) for i, (event, _action, _phrase) in enumerate(EVENTS)],
            }), text=True, check=True)
        for index, (event, _action, _phrase) in enumerate(EVENTS):
            clip_path = (Path(MANIFEST['effects']['default']['events'][event]['file'])
                         if profile == 'default' else Path(temp) / f'{event}.wav')
            if not clip_path.is_file():
                raise SystemExit(f'Missing audio: {clip_path}. Default effects require macOS.')
            raw = subprocess.check_output([
                'ffmpeg', '-v', 'error', '-i', str(clip_path),
                '-f', 's16le', '-ar', str(RATE), '-ac', '1', '-'])
            clip = array('h')
            clip.frombytes(raw)
            if not clip or max(abs(v) for v in clip) < 100:
                raise SystemExit(f'No audio generated for {profile}/{event}.')
            step = PROFILES[profile]['step']
            if len(clip) >= (step - .15) * RATE:
                raise SystemExit(f'The {profile}/{event} cue exceeds its scene; increase its step duration.')
            offset = round((INTRO_SECONDS + index * step) * RATE)
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


def frame(t, audio, profile):
    settings = PROFILES[profile]
    step = settings["step"]
    image = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(image)
    active = min(4, int((t - INTRO_SECONDS) / step)) if t >= INTRO_SECONDS else -1
    d.text((56, 32), 'CODE GOSSIP', font=BOLD[20], fill=GREEN)
    d.text((1060, 32), settings['badge'], font=FONTS[18], fill=ORANGE)
    d.text((56, 78), 'Fix the login timeout.', font=BOLD[52], fill=WHITE)
    d.text((58, 150), 'One bug fix. From the first search to the handoff.', font=FONTS[22], fill=MUTED)
    d.text((60, 214), '01   THE EVENT', font=BOLD[20], fill=MUTED)
    d.text((780, 214), '02   ' + settings['output'], font=BOLD[20], fill=MUTED)
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
    d.text((790, 282), settings['engine'], font=FONTS[18], fill=GREEN)
    sound = cue(profile, active) if active >= 0 else 'Listen for the cue'
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
    d.text((790, 529), settings['note'], font=FONTS[18], fill=MUTED)
    if active >= 0:
        phase = min(1, max(0, (t - (INTRO_SECONDS + active * step)) / .3))
        source_y = 284 + active * 65
        d.line((704, source_y, 748, 416), fill=LINE, width=2)
        dot_y = source_y + phase * (416 - source_y)
        d.ellipse((700 + phase * 41, dot_y - 4, 708 + phase * 41, dot_y + 4), fill=GREEN)
    d.line((56, 618, 1224, 618), fill=LINE, width=2)
    d.line((56, 618, 56 + int(1168 * t / duration(profile)), 618), fill=GREEN, width=3)
    d.text((56, 649), settings['footer'], font=FONTS[22], fill=WHITE)
    d.text((1008, 652), 'code-gossip  /  macOS', font=FONTS[18], fill=MUTED)
    return image


def compact_frame(t, audio, profile):
    settings = PROFILES[profile]
    accent = settings['accent']
    active = min(len(EVENTS) - 1, max(0, int((t - INTRO_SECONDS) / settings['step'])))
    event, action, _phrase = EVENTS[active]
    image = Image.new('RGB', (720, 450), BG)
    d = ImageDraw.Draw(image)
    d.text((32, 28), settings['label'], font=BOLD[26], fill=accent)
    d.text((621, 30), f'{active + 1} / 5', font=FONTS[24], fill=MUTED)
    d.text((32, 98), action, font=BOLD[36], fill=WHITE)
    d.text((33, 149), event, font=FONTS[24], fill=MUTED)
    d.line((32, 194, 688, 194), fill=LINE, width=2)
    text = cue(profile, active)
    text = f'{text} sound' if profile == 'default' else '“' + text + '”'
    line, y = '', 218
    for word in text.split():
        candidate = (line + ' ' + word).strip()
        if d.textlength(candidate, font=BOLD[36]) > 654 and line:
            d.text((32, y), line, font=BOLD[36], fill=accent)
            y += 45
            line = word
        else:
            line = candidate
    d.text((32, y), line, font=BOLD[36], fill=accent)
    window = audio[int(t * RATE):int(t * RATE) + RATE // 8]
    rms = math.sqrt(sum(v * v for v in window) / max(1, len(window))) / 32768
    level = min(1, rms * 9)
    for b in range(44):
        height = 6 + int(42 * level * (.35 + .65 * abs(math.sin(b * .83 + t * 9))))
        x = 34 + b * 15
        d.rounded_rectangle((x, 350 - height / 2, x + 6, 350 + height / 2), radius=3,
                            fill=accent if level > .015 else LINE)
    for i in range(len(EVENTS)):
        d.rounded_rectangle((32 + i * 134, 405, 152 + i * 134, 413), radius=4,
                            fill=accent if i <= active else LINE)
    return image


def render(profile):
    audio = audio_track(profile)
    settings = PROFILES[profile]
    with tempfile.TemporaryDirectory(prefix='code-gossip-demo-') as temp:
        track = Path(temp) / 'audio.wav'
        with wave.open(str(track), 'wb') as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(RATE)
            stream.writeframes(audio.tobytes())
        movie = Path(temp) / 'demo.mp4'
        encoder = subprocess.Popen([
            'ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
            '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-', '-i', str(track),
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23', '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', '-shortest',
            str(movie)], stdin=subprocess.PIPE)
        try:
            for i in range(round(duration(profile) * FPS)):
                encoder.stdin.write(frame(i / FPS, audio, profile).tobytes())
            encoder.stdin.close()
            if encoder.wait() != 0:
                raise SystemExit('Video encoding failed.')
        finally:
            if encoder.poll() is None:
                encoder.kill()
                encoder.wait()
        preview = Path(temp) / 'preview.gif'
        frames = [compact_frame(i / 8, audio, profile)
                  for i in range(round(duration(profile) * 8))]
        frames[0].save(preview, save_all=True, append_images=frames[1:],
                       duration=[120 if i % 2 == 0 else 130 for i in range(len(frames))],
                       loop=0, optimize=True)
        # Replace finished outputs only; failed synthesis/encoding preserves prior assets.
        shutil.copyfile(movie, OUT / (settings['stem'] + '.mp4'))
        shutil.copyfile(preview, OUT / (settings['stem'] + '.gif'))
    print(f"Rendered {profile}: {duration(profile):g}s MP4 with audio + compact GIF.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profiles', nargs='+', choices=list(PROFILES), default=list(PROFILES))
    args = parser.parse_args()
    if not shutil.which('ffmpeg'):
        raise SystemExit('ffmpeg is required; install FFmpeg.')
    OUT.mkdir(parents=True, exist_ok=True)
    for profile in args.profiles:
        render(profile)


if __name__ == '__main__':
    main()
