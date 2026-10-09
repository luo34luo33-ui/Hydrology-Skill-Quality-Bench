"""Relative evidence scope must be honored without weakening hash verification."""
import hashlib
import json

import pytest

from harness.grader import grade_criterion


@pytest.mark.parametrize('base,path', [('workspace_root', 'raw.csv'),
                                     ('manifest_parent', '../raw.csv')])
@pytest.mark.parametrize('stale', [False, True])
def test_manifest_declared_scope_and_actual_digest(tmp_path, base, path, stale):
    (tmp_path / 'stage').mkdir()
    raw = tmp_path / 'raw.csv'
    raw.write_text('time,Q\n2023-08-01,42\n')
    digest = '0' * 64 if stale else hashlib.sha256(raw.read_bytes()).hexdigest()
    doc = {'status': 'blocked', 'reference_base': base,
           'inputs': [{'path': path, 'sha256': digest}]}
    (tmp_path / 'stage/result.json').write_text(json.dumps(doc))
    result = grade_criterion({'type': 'scientific_invariant', 'check': 'manifest_integrity',
                             'target': 'stage/result.json'}, tmp_path, tmp_path)
    assert result['score'] == (0 if stale else 1)
    assert not result['details'].startswith('grading error:')


@pytest.mark.parametrize('doc', [{'inputs': []}, {'reference_base': 'guess', 'inputs': []}])
def test_missing_or_unrecognized_evidence_is_unassessable(tmp_path, doc):
    (tmp_path / 'result.json').write_text(json.dumps(doc))
    result = grade_criterion({'type': 'scientific_invariant', 'check': 'manifest_integrity',
                             'target': 'result.json'}, tmp_path, tmp_path)
    assert result['score'] == 0
    assert result['raw_value'] is None
    assert result['details'].startswith('grading error:')
