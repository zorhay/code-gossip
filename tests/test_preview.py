"""Draft speech uses selected speakers and leaves saved settings untouched."""
from unittest.mock import patch, Mock
import pytest
import preview


@pytest.mark.parametrize('event,roles', [('subagent_start', ['main','sub']), ('subagent_stop', ['sub','main'])])
def test_dialogue_speaker_order(event, roles):
    request = {'config': {}, 'check': False, 'mode': 'phrases', 'event': event,
               'phrases': {event: [['First', 'Second']]}}
    with patch.object(preview, 'speak') as speak:
        assert preview.run(request)['ok']
    assert [call.args[2] for call in speak.call_args_list] == roles


def test_kokoro_preview_honors_subagent_voice():
    with patch.object(preview.narrate, '_ensure_kokoro_daemon', return_value=True), patch.object(preview.narrate, '_kokoro_request', return_value={'ok': True}) as send:
        preview.speak('Hello', {'tts_engine':'kokoro','kokoro_voice':'af_heart','kokoro_voice_sub':'am_adam','voice_volume':42}, 'sub')
    assert send.call_args.kwargs['voice'] == 'am_adam'
    assert send.call_args.kwargs['volume'] == 42


def test_say_preview_passes_text_as_argument_not_shell():
    with patch.object(preview.subprocess, 'run', return_value=Mock(returncode=0)) as run:
        preview.speak('$(do-not-execute)', {'tts_engine':'say','voice_main':'Tara'})
    assert '$(do-not-execute)' in run.call_args_list[0].args[0]
    assert not run.call_args_list[0].kwargs.get('shell')


def test_failed_speech_is_reported():
    with patch.object(preview.narrate, '_ensure_kokoro_daemon', return_value=False):
        with pytest.raises(RuntimeError):
            preview.speak('Hello', {'tts_engine':'kokoro'})


def test_phrase_preview_plays_requested_alternative():
    request = {'config': {}, 'check': False, 'mode': 'phrases', 'event': 'edit',
               'variant': 1, 'phrases': {'edit': ['First', 'Selected']}}
    with patch.object(preview, 'speak') as speak:
        preview.run(request)
    assert speak.call_args.args[0] == 'Selected'


def test_generation_and_replay_are_separate():
    config = {'narrator_provider':'openai','narrator_model':'model','narrator_api_key':'test','narrator_style':'pair_programmer'}
    with patch.object(preview.narrate, 'call_provider', return_value='Exact sample') as generate, patch.object(preview, 'speak') as speak:
        result = preview.run({'config':config,'check':False,'mode':'ai','action':'generate'})
        assert result['text'] == 'Exact sample'
        speak.assert_not_called()
        preview.run({'config':config,'check':False,'mode':'ai','action':'play','text':result['text']})
        generate.assert_called_once()
        assert speak.call_args.args[0] == 'Exact sample'


def test_provider_check_does_not_require_speech():
    config = {'tts_engine':'kokoro','narrator_provider':'openai','narrator_model':'model','narrator_api_key':'test'}
    with patch.object(preview.narrate, 'check_provider', return_value={'ok':True}), patch.object(preview.narrate, 'check_kokoro') as speech:
        assert preview.run({'config':config,'check':True,'mode':'ai','scope':'provider'})['ok']
        speech.assert_not_called()


def test_speech_check_does_not_call_provider():
    with patch.object(preview.narrate, 'check_kokoro', return_value={'ok':False,'message':'Broken engine'}), patch.object(preview.narrate, 'check_provider') as provider:
        assert not preview.run({'config':{'tts_engine':'kokoro'},'check':True,'mode':'ai','scope':'speech'})['ok']
        provider.assert_not_called()
