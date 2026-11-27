import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from eval import prompt_injection as audit


def test_api_failure_is_recorded_and_stops_run(tmp_path, monkeypatch):
    output = tmp_path / 'audit.jsonl'
    monkeypatch.setattr('sys.argv', ['audit', '--output', str(output)])
    monkeypatch.setattr(audit, 'settings', SimpleNamespace(credentials='synthetic', model='fake'))
    with patch.object(audit.gigachat_client, 'chat', side_effect=audit.gigachat_client.LLMError('offline')) as call:
        audit.main()
    rows = [json.loads(line) for line in output.read_text(encoding='utf-8').splitlines()]
    assert call.call_count == 1
    assert rows[1]['review'] == 'technical_error'
    assert rows[1]['calls'][0]['messages']
    assert rows[1]['calls'][0]['error'] == 'LLMError'


def test_existing_evidence_is_never_overwritten(tmp_path, monkeypatch):
    output = tmp_path / 'audit.jsonl'
    output.write_text('evidence', encoding='utf-8')
    monkeypatch.setattr('sys.argv', ['audit', '--output', str(output)])
    with pytest.raises(SystemExit):
        audit.main()
    assert output.read_text(encoding='utf-8') == 'evidence'


def test_dry_run_does_not_call_model_or_create_output(tmp_path, monkeypatch, capsys):
    output = tmp_path / 'audit.jsonl'
    monkeypatch.setattr('sys.argv', ['audit', '--dry-run', '--output', str(output)])
    with patch.object(audit.gigachat_client, 'chat') as call:
        audit.main()
    assert not output.exists()
    call.assert_not_called()
    cases = json.loads(capsys.readouterr().out)
    assert len({case['id'] for case in cases}) == len(cases)
    assert {case['target'] for case in cases} == set(audit.TARGETS) | {'answer_chain', 'vacancy_chain'}
