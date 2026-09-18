from __future__ import annotations

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
