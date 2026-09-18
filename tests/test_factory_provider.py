from __future__ import annotations

from valo_gateway.runtime_http_service import GatewayRuntime, RuntimeConfig, dispatch


def config(tmp_path):
    return RuntimeConfig(
        capabilities=[],
        grants=[],
        receipt_path=str(tmp_path / 'receipts.log'),
        operator_authorization='Bearer factory-secret',
        factory_functions=[{'function': 'receipt.replay', 'kind': 'receipt_replay'}],
    )


def test_factory_state_is_fail_closed_without_operator_authorization(tmp_path):
    runtime = GatewayRuntime(config(tmp_path))
    status, payload = dispatch('GET', '/factory/state', {}, runtime, authorization='')
    assert status == 403
    assert payload['error'] == 'forbidden'


def test_factory_state_exposes_real_gateway_receipts(tmp_path):
    runtime = GatewayRuntime(config(tmp_path))
    created = runtime.receipt({'record': {
        'action_id': 'action-1', 'status': 'succeeded',
        'capability_id': 'factory.run.pause',
        'payload': {'function': 'run.pause', 'target': 'run-1'},
    }})
    status, snapshot = dispatch('GET', '/factory/state', {}, runtime, authorization='Bearer factory-secret')
    assert status == 200
    assert snapshot['gateway']['status'] == 'ONLINE'
    assert snapshot['runs'] == []
    assert snapshot['authorityGates'] == []
    assert snapshot['exceptions'] == []
    assert snapshot['replays'] == []
    assert snapshot['settlements'] == []
    assert snapshot['receipts'][0]['id'] == created['receipt_ref']
    assert snapshot['receipts'][0]['function'] == 'run.pause'


def test_factory_function_replay_is_registered_evidenced_and_fail_closed(tmp_path):
    runtime = GatewayRuntime(config(tmp_path))
    source = runtime.receipt({'record': {'action_id': 'action-1', 'status': 'succeeded'}})
    denied_status, denied = dispatch('POST', '/factory/function', {'function': 'receipt.replay', 'target': source['receipt_ref'], 'input': {}}, runtime, authorization='')
    assert denied_status == 403
    assert denied['error'] == 'forbidden'
    status, result = dispatch('POST', '/factory/function', {'function': 'receipt.replay', 'target': source['receipt_ref'], 'input': {}}, runtime, authorization='Bearer factory-secret')
    assert status == 200
    assert result['status'] == 'succeeded'
    assert result['sourceReceipt'] == source['receipt_ref']
    assert result['verified'] is True
    assert result['receiptId'].startswith('sha256:')
    unknown_status, unknown = dispatch('POST', '/factory/function', {'function': 'run.destroy', 'target': 'run-1', 'input': {}}, runtime, authorization='Bearer factory-secret')
    assert unknown_status == 400
    assert unknown['error'] == 'invalid_request'
