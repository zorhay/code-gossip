# Empires audio provenance

Created for Code Gossip on 2026-10-28. All audio in this directory, including the four lossless reference voices, is synthesized. No recordings from Age of Empires or Rise of Nations are included. New prose, voice direction, event mapping, and mastering are Code Gossip contributions under the project's MIT license, to the extent copyright or related rights exist.

## Authoring tools and models

| Component | License | Source |
| --- | --- | --- |
| Qwen3-TTS 1.7B VoiceDesign | Apache-2.0 | [Qwen model card](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign) |
| Qwen3-TTS 1.7B Base | Apache-2.0 | [Qwen model card](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base) |
| MLX VoiceDesign 4-bit conversion | Apache-2.0 | [Pinned revision 5c390979](https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-4bit/tree/5c390979e4b93af5f2932f90742ca99c7dd04687) |
| MLX Base 4-bit conversion | Apache-2.0 | [Pinned revision 37e955a1](https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-1.7B-Base-4bit/tree/37e955a1deb861c088ae5f3a67043185f3d1a60c) |
| MLX-Audio 0.6.2 | MIT; copyright 2024 Prince Canuma | [Repository and license](https://github.com/Blaizzy/mlx-audio/blob/main/LICENSE) |

[Qwen's license text](https://github.com/QwenLM/Qwen3-TTS/blob/main/LICENSE) and [Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0) permit commercial use and redistribution subject to their terms. Model weights and third-party implementation code are not bundled here. If you redistribute those separately, retain their licenses and applicable notices. SoX and FFmpeg were used as external processing tools; their binaries are not bundled either.

The per-cue `source` and optional `taunt` fields in [palette.json](palette.json) distinguish short game-associated phrases from new writing. The `spoken` field, where present, supplies a pronunciation hint. The models were prompted to design fictional characters by vocal qualities, not to reproduce any named performer. Only the resulting synthetic reference voices were used for voice conditioning.

Permissive tool/model licensing does not itself clear third-party text, trademarks, or voice rights. The short-phrase rationale and sources are documented in [README.md](README.md#sources-and-distribution). No Microsoft game audio license or endorsement is claimed.
