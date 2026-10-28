#!/usr/bin/env python3
"""Author Empires with Qwen3-TTS. Playback never imports these dependencies."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def master(source, destination):
    """Keep compact unit barks, a little vintage bandwidth, and 6 dB headroom."""
    with tempfile.TemporaryDirectory(prefix='empires-master-') as folder:
        trimmed = Path(folder) / 'trimmed.wav'
        shaped = Path(folder) / 'shaped.wav'
        subprocess.run([
            'sox', str(source), str(trimmed),
            'silence', '1', '0.01', '0.5%', 'reverse',
            'silence', '1', '0.01', '0.5%', 'reverse',
            'gain', '-9', 'highpass', '120', 'lowpass', '6000',
            'compand', '0.01,0.08', '6:-60,-60,-18,-14,-6,-6', '0', '-90', '0.03',
            'overdrive', '5', '12', 'tempo', '1.10', 'pad', '0.025', '0.08', 'gain', '-n', '-6',
        ], check=True)
        subprocess.run(['sox', str(trimmed), str(shaped), 'fade', '0.006', '0', '0.025'], check=True)
        duration = float(subprocess.check_output(['soxi', '-D', str(shaped)], text=True))
        if not 0.15 <= duration <= 4.0:
            raise ValueError(f'{destination.stem}: unexpected duration {duration:.2f}s; review the take')
        subprocess.run([
            'ffmpeg', '-v', 'error', '-y', '-i', str(shaped),
            '-map_metadata', '-1', '-ar', '24000', '-ac', '1',
            '-codec:a', 'libmp3lame', '-b:a', '96k', str(destination),
        ], check=True)
    return duration


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only', nargs='+', help='Regenerate specific cue IDs')
    parser.add_argument('--force', action='store_true', help='Replace existing recordings')
    parser.add_argument('--design-cast', action='store_true', help='Recreate the synthetic references from the saved prompts')
    args = parser.parse_args()
    if args.design_cast and args.only:
        parser.error('--design-cast recreates the whole cast; regenerate all cues together')
    spec = json.loads((ROOT / 'palette.json').read_text())
    selected = set(args.only or [cue['id'] for cue in spec['cues']])
    unknown = selected - {cue['id'] for cue in spec['cues']}
    if unknown:
        parser.error('Unknown cue IDs: ' + ', '.join(sorted(unknown)))
    for tool in ('sox', 'soxi', 'ffmpeg'):
        if not shutil.which(tool):
            parser.error(f'Missing authoring tool: {tool}')
    import mlx.core as mx
    import numpy as np
    from huggingface_hub import snapshot_download
    from mlx_audio.audio_io import write
    from mlx_audio.tts.utils import load_model

    def model(kind):
        details = spec['models'][kind]
        path = snapshot_download(details['repo'], revision=details['revision'])
        return load_model(path)

    if args.design_cast:
        designer = model('design')
        for name, voice in spec['cast'].items():
            target = ROOT / voice['reference']
            if target.exists() and not args.force:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            mx.random.seed(voice['seed'])
            parts = list(designer.generate_voice_design(
                text=voice['text'], instruct=voice['instruct'], language='English',
                temperature=.75, top_p=.9, max_tokens=350,
            ))
            write(target, np.concatenate([np.asarray(part.audio) for part in parts]), parts[0].sample_rate)
            print(f'Designed {name}: {target.name}', flush=True)
        del designer
        mx.clear_cache()

    missing = [v['reference'] for v in spec['cast'].values() if not (ROOT / v['reference']).is_file()]
    if missing:
        parser.error('Missing synthetic references; use --design-cast: ' + ', '.join(missing))
    pending = [c for c in spec['cues'] if c['id'] in selected and (args.force or not (ROOT / (c['id'] + '.mp3')).exists())]
    if not pending:
        print('All selected recordings exist; use --force to regenerate.')
        return
    synthesizer = model('base')
    for cue in pending:
        voice = spec['cast'][cue['voice']]
        mx.random.seed(cue['seed'])
        parts = list(synthesizer.generate(
            text=cue.get('spoken', cue['text']), lang_code='English',
            ref_audio=str(ROOT / voice['reference']), ref_text=voice['text'],
            **spec['sampling'],
        ))
        with tempfile.TemporaryDirectory(prefix='empires-take-') as folder:
            source = Path(folder) / 'raw.wav'
            write(source, np.concatenate([np.asarray(part.audio) for part in parts]), parts[0].sample_rate)
            destination = ROOT / (cue['id'] + '.mp3')
            duration = master(source, destination)
        print(f"{cue['id']}: {duration:.2f}s  {sha256(destination)[:12]}", flush=True)
        mx.clear_cache()


if __name__ == '__main__':
    main()
