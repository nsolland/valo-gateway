from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from valo_gateway.runtime_http_service import GatewayRuntime, RuntimeConfig, dispatch


def cfg(tmp_path):
    return RuntimeConfig(
        capabilities=[],
        grants=[],
        receipt_path=str(tmp_path / 'receipts.log'),
        operator_authorization='Bearer operator-secret',
        operator_functions=[{'function': 'receipt.replay', 'kind': 'receipt_replay'}],
    )


def test_operator_state_requires_server_authorization(tmp_path):
    runtime = GatewayRuntime(cfg(tmp_path))
    status, payload = dispatch('GET', '/operator/state', {}, runtime, authorization='')
    assert status == 403
    assert payload['error'] == 'forbidden'


def test_operator_state_exposes_gateway_receipts(tmp_path):
    runtime = GatewayRuntime(cfg(tmp_path))
    created = runtime.receipt({'record': {
        'action_id': 'a1',
        'status': 'succeeded',
        'capability_id': 'run.pause',
        'payload': {'function': 'run.pause', 'target': 'run-1'},
    }})
    status, snapshot = dispatch('GET', '/operator/state', {}, runtime, authorization='Bearer operator-secret')
    assert status == 200
    assert snapshot['gateway']['status'] == 'ONLINE'
    assert snapshot['runs'] == []
    assert snapshot['authorityGates'] == []
    assert snapshot['exceptions'] == []
    assert snapshot['replays'] == []
    assert snapshot['settlements'] == []
    assert snapshot['receipts'][0]['id'] == created['receipt_ref']
    assert snapshot['receipts'][0]['function'] == 'run.pause'


def test_registered_operator_function_is_evidenced_and_unknown_function_fails_closed(tmp_path):
    runtime = GatewayRuntime(cfg(tmp_path))
    source = runtime.receipt({'record': {'action_id': 'a1', 'status': 'succeeded'}})

    status, result = dispatch(
        'POST', '/operator/function',
        {'function': 'receipt.replay', 'target': source['receipt_ref'], 'input': {}},
        runtime,
        authorization='Bearer operator-secret',
    )
    assert status == 200
    assert result['status'] == 'succeeded'
    assert result['verified'] is True
    assert result['sourceReceipt'] == source['receipt_ref']
    assert result['receiptId'].startswith('sha256:')

    status, payload = dispatch(
        'POST', '/operator/function',
        {'function': 'run.destroy', 'target': 'run-1', 'input': {}},
        runtime,
        authorization='Bearer operator-secret',
    )
    assert status == 400
    assert payload['error'] == 'invalid_request'


def test_operator_env_adds_capability_and_grant_without_overwriting_base(monkeypatch, tmp_path):
    valid_until = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    monkeypatch.setenv('GATEWAY_CAPABILITIES_JSON', json.dumps([{
        'capability_id': 'workflow.create', 'provider': 'workflow', 'risk': 'effect',
    }]))
    monkeypatch.setenv('GATEWAY_GRANTS_JSON', json.dumps([{
        'principal_id': 'p:njaal', 'capability_id': 'workflow.create', 'valid_until': valid_until,
    }]))
    monkeypatch.setenv('GATEWAY_OPERATOR_FUNCTIONS_JSON', json.dumps([{
        'function': 'receipt.replay', 'kind': 'receipt_replay',
    }]))
    monkeypatch.setenv('GATEWAY_OPERATOR_GRANTS_JSON', json.dumps([{
        'principal_handle': '@justyou', 'capability_id': 'receipt.replay', 'valid_until': valid_until,
    }]))
    monkeypatch.setenv('GATEWAY_RECEIPT_PATH', str(tmp_path / 'receipts.log'))

    runtime = GatewayRuntime(RuntimeConfig.from_env())
    discovered = runtime.discover({'intent': 'receipt replay'})
    assert [item['capability_id'] for item in discovered['capabilities']] == ['receipt.replay']

    assert runtime.evaluate({
        'principal_handle': '@justyou',
        'principal_id': 'some-authenticated-id',
        'capability_id': 'receipt.replay',
        'payload': {},
    })['decision'] == 'ALLOW'
    assert runtime.evaluate({
        'principal_handle': '@other',
        'principal_id': 'some-authenticated-id',
        'capability_id': 'receipt.replay',
        'payload': {},
    })['decision'] == 'DENY'

    assert runtime.evaluate({
        'principal_id': 'p:njaal',
        'capability_id': 'workflow.create',
        'payload': {},
    })['decision'] == 'ALLOW'
