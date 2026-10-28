# Empires

A Clips collection of short, theatrical RTS unit calls: rough village workers, an eager scout, a resonant scholar, and a swaggering commander. It combines newly performed short phrases associated with Age of Empires and Rise of Nations with new writing for coding actions. **These are AI-generated performances, not recordings extracted from the games.**

Select **Clips → Empires → Save & use** in Soundbar, or run `~/.code-gossip/switch.sh voice-profile empires` with the Voice channel enabled. Browsing or previewing the collection does not activate it. Playback uses bundled MP3 files; it needs no speech model, account, or download.

## Cast and event palette

The [sound manifest](../../sounds.json) maps all 24 events to 52 recordings. The [palette](palette.json) records each phrase, speaker, source, pronunciation input, and random seed. Twenty-one cues use short game-associated expressions; 31 are new writing. Rise of Nations contributes multiplayer taunts, rather than invented quotations attributed to its units. Subagent events have three alternative two-speaker exchanges, separated by 180 ms.

| Agent action | Example recording | Phrase origin |
| --- | --- | --- |
| Session starts | Worker: “Ready!” | AoE II Britons |
| Edits code | Worker: “Builden!” / “Chopper!” | AoE II Britons |
| Reads files | Scholar: “I need Knowledge!” | Rise of Nations taunt 9 |
| Delegates | Commander: “Scout the frontier!” → Scout: “On my way!” | New writing → RoN taunt 78 |
| Runs tests | Commander: “Test the defenses!” | New writing |
| Needs approval | Scholar: “Mandatum?” | AoE II Latin acknowledgement |
| Compacts context | Scholar: “Wololo!” | AoE Priest chant, newly interpreted |
| Finishes the turn | Commander: “Victory is mine!” | RoN taunt 73 |

Victory and campaign-ending cues appear only at `stop` and `session_end`. Tests, builds, and subagent returns have separate cues and do not announce that checks passed. The Priest reference comes from the original Age of Empires; it is not presented as the normal AoE II Monk conversion sound. Transcribed medieval/Latin spellings vary; `spoken` entries are practical synthesis hints, not claims of historically exact pronunciation.

## Sources and distribution

The four reference voices were designed from written descriptions with **Qwen3-TTS VoiceDesign**, then reused with **Qwen3-TTS Base** to keep each fictional character consistent. No game audio, human voice samples, or actor names were supplied to either model. The references in [references/](references/) are our generated performances of new text, with their prompts and transcripts preserved in the palette.

Qwen publishes these model weights under [Apache 2.0](https://github.com/QwenLM/Qwen3-TTS/blob/main/LICENSE). The authoring engine, [MLX-Audio](https://github.com/Blaizzy/mlx-audio), uses [MIT](https://github.com/Blaizzy/mlx-audio/blob/main/LICENSE). These are permissive licenses that allow commercial use; no noncommercial or share-alike condition was found in these model/tool licenses. The repository distributes generated audio and our recipe, not the model weights or inference library. Our contributions are offered under Code Gossip's [MIT license](../../../../LICENSE), to the extent rights exist in them. See [NOTICE.md](NOTICE.md) for exact models and license references.

Phrase references: [AoE II Britons dialogue](https://ageofempires.fandom.com/wiki/Britons), [AoE II dialogue transcription](https://steamcommunity.com/sharedfiles/filedetails/?id=1639464279), [AoE Priest](https://ageofempires.fandom.com/wiki/Priest_(Age_of_Empires)), and [Rise of Nations taunt guide](https://steamcommunity.com/sharedfiles/filedetails/?id=270326450). These links document wording, not permission to redistribute game audio. Only brief expressions are used, alongside our own text. The [U.S. Copyright Office's guidance on short phrases](https://www.copyright.gov/circs/circ33.pdf) supports this approach under U.S. copyright law; it is not a guarantee about every jurisdiction or other rights. Game names identify the inspiration; there is no affiliation or endorsement. Bundling actual game recordings would require a separate rights assessment.

## Regenerate

Authoring requires Apple Silicon, Python 3.11, SoX, FFmpeg, and `mlx-audio==0.6.2`. Use an isolated environment; these packages are not runtime dependencies. The recipe pins both MLX model revisions in the palette and downloads roughly 2.3 GB for Base. Recreating the cast downloads VoiceDesign as well.

```bash
python3.11 -m venv /tmp/empires-authoring
/tmp/empires-authoring/bin/python -m pip install mlx-audio==0.6.2
PYTHON=/tmp/empires-authoring/bin/python bash code-gossip/data/sounds/empires/generate.sh --force
```

Use `--only builden chopper --force` to replace selected takes. Use `--design-cast --force` to recreate all reference voices and clips. Keep the shipped lossless references when you want the same cast: seeds and pinned models make the recipe repeatable, but model/library/hardware changes can still affect the exact waveform. Regeneration is explicit; existing clips are skipped without `--force`.

Mastering trims boundary silence, filters to 120–6000 Hz, compresses peaks, adds mild overdrive, slightly tightens the pace, and adds short fades. Peaks are normalized to −6 dB before mono 24 kHz / 96 kb/s MP3 encoding. Review regenerated takes for pronunciation, repetition, and level; the script rejects unexpectedly long or empty takes. Then [regenerate website previews and run the website checks](../../../../ARCHITECTURE.md#website-builds-and-recordings).
