from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from valo_gateway.runtime_http_service import GatewayRuntime, RuntimeConfig


def config(tmp_path):
    now = datetime.now(timezone.utc)
    return RuntimeConfig(
        capabilities=[{
            'capability_id': 'workflow.create',
            'provider': 'workflow',
            'description': 'create workflow automation',
            'verbs': ['create'],
            'nouns': ['workflow'],
            'risk': 'effect',
        }],
        grants=[{
            'principal_id': 'p:njaal',
            'capability_id': 'workflow.create',
            'account_ref': 'acct:main',
            'valid_until': (now + timedelta(hours=1)).isoformat(),
        }],
        receipt_path=str(tmp_path / 'receipts.log'),
    )


def test_discover_returns_only_relevant_capability(tmp_path):
    runtime = GatewayRuntime(config(tmp_path))
    result = runtime.discover({'intent': 'create workflow', 'limit': 5})
    assert [item['capability_id'] for item in result['capabilities']] == ['workflow.create']


def test_evaluate_allows_matching_unexpired_grant_and_denies_mismatch(tmp_path):
    runtime = GatewayRuntime(config(tmp_path))
    allowed = runtime.evaluate({
        'principal_id': 'p:njaal',
        'account_ref': 'acct:main',
        'capability_id': 'workflow.create',
        'payload': {'name': 'reddit'},
    })
    assert allowed['decision'] == 'ALLOW'
    assert allowed['fresh'] is True
    assert allowed['permit_id']

    denied = runtime.evaluate({
        'principal_id': 'p:other',
        'account_ref': 'acct:main',
        'capability_id': 'workflow.create',
        'payload': {'name': 'reddit'},
    })
    assert denied['decision'] == 'DENY'
    assert denied['fresh'] is True


def test_expired_grant_fails_closed(tmp_path):
    cfg = config(tmp_path)
    cfg.grants[0]['valid_until'] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    result = GatewayRuntime(cfg).evaluate({
        'principal_id': 'p:njaal',
        'account_ref': 'acct:main',
        'capability_id': 'workflow.create',
        'payload': {},
    })
    assert result['decision'] == 'DENY'


def test_receipts_are_append_only_hash_chained(tmp_path):
    runtime = GatewayRuntime(config(tmp_path))
    first = runtime.receipt({'record': {'action_id': 'a1', 'status': 'staged'}})
    second = runtime.receipt({'record': {'action_id': 'a1', 'status': 'succeeded'}})
    assert first['receipt_ref'].startswith('sha256:')
    assert second['receipt_ref'].startswith('sha256:')
    assert first['receipt_ref'] != second['receipt_ref']

    lines = (tmp_path / 'receipts.log').read_text().strip().splitlines()
    assert len(lines) == 2
    assert first['receipt_ref'] in lines[0]
    assert second['receipt_ref'] in lines[1]


def test_from_env_composes_extra_capability_and_grant(monkeypatch, tmp_path):
    valid_until = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    monkeypatch.setenv('GATEWAY_CAPABILITIES_JSON', json.dumps([{
        'capability_id': 'workflow.create',
        'provider': 'workflow',
        'description': 'create workflow automation',
        'verbs': ['create'],
        'nouns': ['workflow'],
        'risk': 'effect',
    }]))
    monkeypatch.setenv('GATEWAY_GRANTS_JSON', json.dumps([{
        'principal_id': 'p:njaal',
        'capability_id': 'workflow.create',
        'valid_until': valid_until,
    }]))
    monkeypatch.setenv('GATEWAY_EXTRA_CAPABILITIES_JSON', json.dumps([{
        'capability_id': 'site.publish',
        'provider': 'here.now',
        'description': 'publish website files to a live URL',
        'verbs': ['publish', 'deploy', 'host'],
        'nouns': ['site', 'website', 'webpage'],
        'risk': 'effect',
    }]))
    monkeypatch.setenv('GATEWAY_EXTRA_GRANTS_JSON', json.dumps([{
        'principal_handle': '@justyou',
        'capability_id': 'site.publish',
        'valid_until': valid_until,
    }]))
    monkeypatch.setenv('GATEWAY_RECEIPT_PATH', str(tmp_path / 'receipts.log'))

    cfg = RuntimeConfig.from_env()
    assert len(cfg.capabilities) == 2
    assert len(cfg.grants) == 2
    assert {item['capability_id'] for item in cfg.capabilities} == {'workflow.create', 'site.publish'}
    assert {item['capability_id'] for item in cfg.grants} == {'workflow.create', 'site.publish'}

    runtime = GatewayRuntime(cfg)
    discovered = runtime.discover({'intent': 'publish website', 'limit': 5})
    assert [item['capability_id'] for item in discovered['capabilities']] == ['site.publish']

    allowed = runtime.evaluate({
        'principal_handle': '@justyou',
        'principal_id': 'p:njaal',
        'capability_id': 'site.publish',
        'payload': {'files': [{'path': 'index.html'}]},
    })
    assert allowed['decision'] == 'ALLOW'
    assert allowed['fresh'] is True
