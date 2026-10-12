"""Provider discovery uses live, read-only catalogs and never leaks credentials."""
import io
import json
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

import pytest
from engine import model_catalog


def response(data):
    return io.BytesIO(json.dumps(data).encode())


def test_anthropic_pagination_and_auth():
    pages = [response({'data': [{'id': 'claude-new'}], 'has_more': True, 'last_id': 'cursor/1'}),
             response({'data': [{'id': 'claude-other'}, {'id': 'retired', 'lifecycle': 'retired'}], 'has_more': False})]
    with patch.object(model_catalog, 'urlopen', side_effect=pages) as get:
        result = model_catalog.list_models('anthropic', 'test-secret')
    assert result['models'] == ['claude-new', 'claude-other']
    request = get.call_args_list[1].args[0]
    assert parse_qs(urlparse(request.full_url).query)['after_id'] == ['cursor/1']
    assert request.get_header('X-api-key') == 'test-secret'
    assert request.get_header('Anthropic-version') == '2023-06-01'
    assert request.data is None


def test_gemini_follows_pages_and_excludes_non_language_models():
    pages = [response({'models': [{'name': 'models/gemini-new', 'supportedGenerationMethods': ['generateContent']},
                                 {'name': 'models/embedding', 'supportedGenerationMethods': ['embedContent']}], 'nextPageToken': 'page 2'}),
             response({'models': [{'name': 'models/gemini-image', 'supportedGenerationMethods': ['generateContent']},
                                 {'name': 'models/gemini-other', 'supportedGenerationMethods': ['generateContent']}]})]
    with patch.object(model_catalog, 'urlopen', side_effect=pages) as get:
        result = model_catalog.list_models('gemini', 'test-secret')
    assert result['models'] == ['gemini-new', 'gemini-other']
    request = get.call_args.args[0]
    assert parse_qs(urlparse(request.full_url).query)['pageToken'] == ['page 2']
    assert request.get_header('X-goog-api-key') == 'test-secret'
    assert 'test-secret' not in request.full_url


def test_openai_suggestions_only_include_returned_language_models():
    with patch.object(model_catalog, 'urlopen', return_value=response({'data': [
            {'id': 'new-language-model'}, {'id': 'new-language-model'}, {'id': 'tts-1'}, {'id': 'text-embedding-new'}]})) as get:
        result = model_catalog.list_models('openai', 'test-secret')
    assert result['models'] == ['new-language-model']
    assert get.call_args.args[0].get_header('Authorization') == 'Bearer test-secret'


@pytest.mark.parametrize('names', [[], ['my-custom-model:latest', 'local-new:small']])
def test_ollama_uses_only_installed_models(names):
    with patch.object(model_catalog, 'urlopen', return_value=response({'models': [{'name': name} for name in names]})) as get:
        result = model_catalog.list_models('ollama')
    assert result['models'] == sorted(names)
    assert get.call_args.args[0].full_url == 'http://localhost:11434/api/tags'
    assert get.call_args.args[0].headers == {}


def test_missing_key_and_cli_never_make_network_requests():
    with patch.object(model_catalog, 'urlopen') as get:
        assert not model_catalog.list_models('openai')['ok']
        result = model_catalog.list_models('claude_cli')
        assert result['models'] == [] and result['supported'] is False
        get.assert_not_called()


@pytest.mark.parametrize('error', [HTTPError('secret-url', 401, 'secret-key', {}, None), RuntimeError('secret-key')])
def test_failure_never_exposes_secrets_or_falls_back_to_static_models(error):
    with patch.object(model_catalog, 'urlopen', side_effect=error):
        result = model_catalog.list_models('openai', 'secret-key')
    assert not result['ok']
    assert 'secret' not in json.dumps(result)
    assert not result.get('models')


def test_repeated_pagination_token_fails_without_partial_suggestions():
    with patch.object(model_catalog, 'urlopen', side_effect=lambda *a, **kw: response({
            'data': [{'id': 'partial'}], 'has_more': True, 'last_id': 'same'})) as get:
        result = model_catalog.list_models('anthropic', 'test-secret')
    assert not result['ok'] and not result.get('models')
    assert get.call_count == 2
