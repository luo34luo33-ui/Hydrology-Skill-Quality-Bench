"""Offline controls only: no API credential reads or real model calls."""
import json
from pathlib import Path

from harness.cli_events import command, EventCounter


def test_opencode_pilot_provider_and_permissions():
    root=Path(__file__).resolve().parents[1]
    settings=json.loads((root/'runtime/opencode-pilot.json').read_text())
    assert settings['model']=='deepseek/deepseek-flash'
    assert settings['permission']['skill']=='deny'
    assert settings['permission']['webfetch']=='deny'
    assert settings['permission']['websearch']=='deny'
    assert settings['plugin']==[] and settings['mcp']=={}
    assert settings['provider']['deepseek']['options']['apiKey']=='offline-placeholder-no-real-key'
    assert settings['provider']['deepseek']['models']['deepseek-flash']['variants']['high']['reasoningEffort']=='high'


def test_opencode_frozen_command_and_event_budget():
    argv=command('opencode','deepseek/deepseek-flash','high','same public prompt')
    assert '--pure' in argv and '--auto' in argv and '--format' in argv
    assert 'deepseek/deepseek-flash' in argv
    c=EventCounter('opencode',rounds=1,tools=2)
    c.feed(json.dumps({'type':'step_start','part':{'id':'step-1'}}))
    assert c.exhausted
