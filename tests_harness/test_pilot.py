"""Pilot infrastructure checks run without calling a real model."""
import json

import pytest

from harness.cli_events import command
from harness.composite_runtime import load_lock
from harness.pilot import allowed_model_route
from harness.confirmation import ConfirmationBroker


@pytest.mark.parametrize('method,path', [
    ('GET', '/backend-api/codex/models?client_version=0.160.0'),
    ('POST', '/backend-api/codex/responses'),
    ('POST', '/backend-api/codex/responses/compact'),
])
def test_pilot_gateway_model_routes(method, path):
    assert allowed_model_route(method, path)


@pytest.mark.parametrize('method,path', [
    ('CONNECT', 'chatgpt.com:443'), ('GET', '/'),
    ('GET', '/backend-api/codex/responses'),
    ('POST', '/backend-api/codex/responses/../files'),
    ('POST', '/backend-api/files'), ('GET', 'https://example.com/'),
])
def test_pilot_gateway_rejects_retrieval_and_arbitrary_upstream(method, path):
    assert not allowed_model_route(method, path)


def test_codex_fresh_session_command():
    argv = command('codex', 'gpt-6.1-sol', 'medium', 'same public prompt')
    assert '--ephemeral' in argv and '--ignore-rules' in argv


def test_pilot_does_not_certify_formal_runtime(tmp_path):
    lock = tmp_path / 'lock.json'
    lock.write_text(json.dumps({'image_digest': 'sha256:built', 'formal_eligible': False,
                               'network_name': 'pilot', 'isolated_network_certified': False}))
    with pytest.raises(ValueError, match='not certified|unattended v2'):
        load_lock(lock)


def test_generic_confirmation_interface_without_task_hints(tmp_path):
    broker = ConfirmationBroker({'confirmations': [
        {'key': 'timezone', 'subject': '时间', 'answer': 'Asia/Shanghai'},
        {'key': 'private_other', 'subject': 'other', 'answer': 'hidden-answer'},
    ]}, tmp_path / 'audit.jsonl')
    rejected = broker.answer({'subject': 'raw.csv 时间', 'fields': ['timezone'],
                              'question': 'What is the timezone?'})
    assert 'data' in rejected['answers'][0]['error']
    assert 'Asia/Shanghai' not in json.dumps(rejected)
    assert 'private_other' not in json.dumps(rejected)
    confirmed = broker.answer({'subject': 'data', 'fields': ['timezone', 'unknown'],
                               'question': 'What is the timezone of the input time column?'})
    assert confirmed['answers'][0]['answer'] == 'Asia/Shanghai'
    assert 'answer' not in confirmed['answers'][1]
    assert 'hidden-answer' not in json.dumps(confirmed)
