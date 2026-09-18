from __future__ import annotations

import json

from valo_gateway.runtime_http_service import GatewayRuntime, RuntimeConfig, dispatch


def _runtime(tmp_path):
    return GatewayRuntime(RuntimeConfig(
        capabilities=[],
        grants=[],
        receipt_path=str(tmp_path / 'receipts.log'),
    ))


def test_receipt_append_and_replay_verifies_full_chain(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    first = runtime.receipt({'record': {'action_id': 'a-1', 'status': 'staged'}})
    second = runtime.receipt({'record': {'action_id': 'a-1', 'status': 'succeeded'}})

    replay = runtime.replay_receipt({'receipt_ref': second['receipt_ref']})
    assert replay['found'] is True
    assert replay['verified'] is True
    assert replay['receipt_ref'] == second['receipt_ref']
    assert replay['record']['status'] == 'succeeded'

    status, body = dispatch('POST', '/receipts/replay', {'receipt_ref': first['receipt_ref']}, runtime)
    assert status == 200
    assert body['verified'] is True


def test_receipt_replay_fails_closed_on_chain_tamper(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    first = runtime.receipt({'record': {'action_id': 'a-1', 'status': 'staged'}})
    second = runtime.receipt({'record': {'action_id': 'a-1', 'status': 'succeeded'}})

    lines = runtime.receipt_path.read_text(encoding='utf-8').splitlines()
    entry = json.loads(lines[0])
    entry['record']['status'] = 'tampered'
    lines[0] = json.dumps(entry, sort_keys=True, separators=(',', ':'))
    runtime.receipt_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    replay = runtime.replay_receipt({'receipt_ref': second['receipt_ref']})
    assert replay['verified'] is False
    assert replay['found'] is False

    status, body = dispatch('POST', '/receipts/replay', {'receipt_ref': first['receipt_ref']}, runtime)
    assert status == 404 or body['verified'] is False
