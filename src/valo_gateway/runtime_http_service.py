from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from uuid import uuid4

from valo_gateway.capability_frontdoor import CapabilityCatalog, CapabilityDescriptor, CapabilityRequest


@dataclass
class RuntimeConfig:
    capabilities: list[dict[str, Any]]
    grants: list[dict[str, Any]]
    receipt_path: str = '/data/receipts.log'
    operator_authorization: str = ''
    operator_functions: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> 'RuntimeConfig':
        capabilities = json.loads(os.getenv('GATEWAY_CAPABILITIES_JSON', '[]'))
        grants = json.loads(os.getenv('GATEWAY_GRANTS_JSON', '[]'))
        extra_capabilities = json.loads(os.getenv('GATEWAY_EXTRA_CAPABILITIES_JSON', '[]'))
        extra_grants = json.loads(os.getenv('GATEWAY_EXTRA_GRANTS_JSON', '[]'))
        operator_functions = json.loads(os.getenv('GATEWAY_OPERATOR_FUNCTIONS_JSON', '[]'))
        operator_grants = json.loads(os.getenv('GATEWAY_OPERATOR_GRANTS_JSON', '[]'))
        if not isinstance(capabilities, list) or not isinstance(grants, list):
            raise ValueError('gateway capabilities and grants must be JSON arrays')
        if not isinstance(extra_capabilities, list):
            raise ValueError('GATEWAY_EXTRA_CAPABILITIES_JSON must be a JSON array')
        if not isinstance(extra_grants, list):
            raise ValueError('GATEWAY_EXTRA_GRANTS_JSON must be a JSON array')
        if not isinstance(operator_functions, list):
            raise ValueError('GATEWAY_OPERATOR_FUNCTIONS_JSON must be a JSON array')
        if not isinstance(operator_grants, list):
            raise ValueError('GATEWAY_OPERATOR_GRANTS_JSON must be a JSON array')

        composed_capabilities = list(capabilities)
        known_capabilities = {
            item.get('capability_id')
            for item in composed_capabilities
            if isinstance(item, dict)
        }
        for definition in extra_capabilities:
            if not isinstance(definition, dict):
                raise ValueError('extra capability definitions must be objects')
            capability_id = definition.get('capability_id')
            if not isinstance(capability_id, str) or not capability_id.strip():
                raise ValueError('extra capability requires a non-empty capability_id')
            if capability_id in known_capabilities:
                continue
            composed_capabilities.append(dict(definition))
            known_capabilities.add(capability_id)

        for definition in operator_functions:
            if not isinstance(definition, dict):
                raise ValueError('operator function definitions must be objects')
            function = definition.get('function')
            capability_id = definition.get('capability_id', function)
            if not isinstance(function, str) or not function.strip():
                raise ValueError('operator function requires a non-empty function')
            if not isinstance(capability_id, str) or not capability_id.strip():
                raise ValueError('operator function capability_id must be a non-empty string')
            if capability_id in known_capabilities:
                continue
            composed_capabilities.append({
                'capability_id': capability_id,
                'provider': 'operator',
                'description': function.replace('.', ' '),
                'risk': 'effect',
            })
            known_capabilities.add(capability_id)

        for grant in extra_grants:
            if not isinstance(grant, dict):
                raise ValueError('extra grants must be objects')

        return cls(
            capabilities=composed_capabilities,
            grants=[*grants, *extra_grants, *operator_grants],
            receipt_path=os.getenv('GATEWAY_RECEIPT_PATH', '/data/receipts.log'),
            operator_authorization=os.getenv('GATEWAY_OPERATOR_AUTHORIZATION', ''),
            operator_functions=operator_functions,
        )


class GatewayRuntime:
    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config
        descriptors = []
        for raw in config.capabilities:
            descriptors.append(CapabilityDescriptor(
                capability_id=str(raw['capability_id']),
                provider=str(raw.get('provider', 'external')),
                description=str(raw.get('description', '')),
                verbs=tuple(str(x) for x in raw.get('verbs', [])),
                nouns=tuple(str(x) for x in raw.get('nouns', [])),
                risk=str(raw.get('risk', 'effect')),
            ))
        self.catalog = CapabilityCatalog(descriptors)
        self.receipt_path = Path(config.receipt_path)
        self.receipt_path.parent.mkdir(parents=True, exist_ok=True)
        self.operator_functions = {
            str(item.get('function')): item
            for item in config.operator_functions
            if isinstance(item, dict) and isinstance(item.get('function'), str) and item.get('function')
        }

    def discover(self, request: dict[str, Any]) -> dict[str, Any]:
        intent = request.get('intent')
        limit = request.get('limit', 5)
        if not isinstance(intent, str) or not intent.strip():
            raise ValueError('intent is required')
        if not isinstance(limit, int):
            raise ValueError('limit must be an integer')
        matches = self.catalog.discover(CapabilityRequest(intent=intent, limit=limit))
        return {'capabilities': [
            {
                'capability_id': item.capability_id,
                'provider': item.provider,
                'description': item.description,
                'verbs': list(item.verbs),
                'nouns': list(item.nouns),
                'risk': item.risk,
            }
            for item in matches
        ]}

    def evaluate(self, request: dict[str, Any]) -> dict[str, Any]:
        principal_id = request.get('principal_id')
        principal_handle = request.get('principal_handle')
        capability_id = request.get('capability_id')
        account_ref = request.get('account_ref')
        if not isinstance(principal_id, str) or not isinstance(capability_id, str):
            raise ValueError('principal_id and capability_id are required')
        now = datetime.now(timezone.utc)
        for grant in self.config.grants:
            grant_principal_id = grant.get('principal_id')
            grant_principal_handle = grant.get('principal_handle')
            if isinstance(grant_principal_id, str):
                if grant_principal_id != principal_id:
                    continue
            elif isinstance(grant_principal_handle, str):
                if grant_principal_handle != principal_handle:
                    continue
            else:
                continue
            if grant.get('capability_id') != capability_id:
                continue
            expected_account = grant.get('account_ref')
            if expected_account is not None and expected_account != account_ref:
                continue
            valid_until = grant.get('valid_until')
            if not isinstance(valid_until, str):
                continue
            try:
                expiry = datetime.fromisoformat(valid_until.replace('Z', '+00:00'))
            except ValueError:
                continue
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry <= now:
                continue
            constraints = grant.get('constraints', {})
            if isinstance(constraints, dict) and not _constraints_match(constraints, request.get('payload')):
                continue
            return {
                'decision': 'ALLOW',
                'fresh': True,
                'permit_id': f"permit_{uuid4().hex}",
                'evaluated_at': now.isoformat(),
                'valid_until': expiry.isoformat(),
            }
        return {
            'decision': 'DENY',
            'fresh': True,
            'evaluated_at': now.isoformat(),
            'reason': 'no_matching_current_grant',
        }

    def receipt(self, request: dict[str, Any]) -> dict[str, Any]:
        record = request.get('record')
        if not isinstance(record, dict):
            raise ValueError('record is required')
        previous_hash = self._last_hash()
        envelope = {
            'previous_hash': previous_hash,
            'record': record,
            'observed_at': datetime.now(timezone.utc).isoformat(),
        }
        canonical = json.dumps(envelope, sort_keys=True, separators=(',', ':'), default=str).encode('utf-8')
        digest = 'sha256:' + hashlib.sha256(canonical).hexdigest()
        line = json.dumps({'hash': digest, **envelope}, sort_keys=True, separators=(',', ':'), default=str)
        with self.receipt_path.open('a', encoding='utf-8') as fh:
            fh.write(line + '\n')
            fh.flush()
            os.fsync(fh.fileno())
        return {'receipt_ref': digest}

    def operator_state(self, authorization: str) -> dict[str, Any]:
        self._require_operator(authorization)
        receipts = []
        for entry in reversed(self._receipt_entries()):
            record = entry.get('record')
            if not isinstance(record, dict):
                continue
            payload = record.get('payload') if isinstance(record.get('payload'), dict) else {}
            function = record.get('function') or payload.get('function') or record.get('capability_id')
            item: dict[str, Any] = {'id': str(entry.get('hash', ''))}
            if isinstance(function, str):
                item['function'] = function
            decision = record.get('decision')
            if decision in {'ALLOW', 'DENY', 'ESCALATE', 'PENDING'}:
                item['decision'] = decision
            run_id = record.get('runId') or record.get('run_id')
            if isinstance(run_id, str):
                item['runId'] = run_id
            receipts.append(item)

        replays = []
        if 'receipt.replay' in self.operator_functions:
            for receipt in receipts:
                receipt_id = receipt.get('id')
                if not isinstance(receipt_id, str) or not receipt_id:
                    continue
                replays.append({
                    'id': 'replay:' + receipt_id,
                    'status': 'READY',
                    'sourceReceipt': receipt_id,
                    'actions': [{
                        'function': 'receipt.replay',
                        'label': 'Replay',
                        'target': receipt_id,
                    }],
                })

        return {
            'gateway': {'status': 'ONLINE', 'reht': 'fresh-at-consequence', 'version': '1'},
            'runs': [],
            'authorityGates': [],
            'exceptions': [],
            'receipts': receipts,
            'replays': replays,
            'settlements': [],
            'gcu': {'active': 0, 'queued': 0, 'consumed': 0, 'capacity': 0, 'unit': 'GCU'},
        }

    def invoke_operator(self, request: dict[str, Any], authorization: str) -> dict[str, Any]:
        self._require_operator(authorization)
        function = request.get('function')
        target = request.get('target')
        input_payload = request.get('input', {})
        if not isinstance(function, str) or not function.strip():
            raise ValueError('function is required')
        if not isinstance(target, str) or not target.strip():
            raise ValueError('target is required')
        if not isinstance(input_payload, dict):
            raise ValueError('input must be an object')
        definition = self.operator_functions.get(function)
        if definition is None:
            raise ValueError('function is not registered')
        kind = definition.get('kind')
        if kind == 'receipt_replay':
            replay = self.replay_receipt(target)
            if replay.get('found') is not True or replay.get('verified') is not True:
                raise ValueError('receipt replay failed')
            result: dict[str, Any] = {
                'status': 'succeeded',
                'verified': True,
                'sourceReceipt': target,
            }
        elif kind == 'http':
            result = self._invoke_http(definition, function, target, input_payload)
        else:
            raise ValueError('registered function kind is unsupported')

        evidence = self.receipt({'record': {
            'kind': 'operator.function',
            'function': function,
            'target': target,
            'input': input_payload,
            'status': result.get('status', 'succeeded'),
            'provider_receipt': result.get('receiptId') or result.get('receipt_id') or result.get('receipt_ref'),
        }})['receipt_ref']
        output = dict(result)
        output.setdefault('status', 'succeeded')
        output['receiptId'] = evidence
        return output

    def replay_receipt(self, receipt_ref: str) -> dict[str, Any]:
        previous: str | None = None
        for entry in self._receipt_entries():
            envelope = {
                'previous_hash': entry.get('previous_hash'),
                'record': entry.get('record'),
                'observed_at': entry.get('observed_at'),
            }
            canonical = json.dumps(envelope, sort_keys=True, separators=(',', ':'), default=str).encode('utf-8')
            expected = 'sha256:' + hashlib.sha256(canonical).hexdigest()
            current = entry.get('hash')
            if current != expected or entry.get('previous_hash') != previous:
                return {'receipt_ref': receipt_ref, 'found': False, 'verified': False}
            if current == receipt_ref:
                return {
                    'receipt_ref': receipt_ref,
                    'found': True,
                    'verified': True,
                    'record': entry.get('record'),
                }
            previous = str(current)
        return {'receipt_ref': receipt_ref, 'found': False, 'verified': False}

    def _invoke_http(self, definition: dict[str, Any], function: str, target: str, input_payload: dict[str, Any]) -> dict[str, Any]:
        url = definition.get('url')
        if not isinstance(url, str) or not url.startswith(('https://', 'http://')):
            raise ValueError('http function requires url')
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        auth_env = definition.get('authorization_env')
        if auth_env is not None:
            if not isinstance(auth_env, str) or not auth_env:
                raise ValueError('authorization_env must be a non-empty string')
            secret = os.getenv(auth_env, '')
            if not secret:
                raise RuntimeError('operator function credential unavailable')
            headers['Authorization'] = secret
        body = json.dumps({'function': function, 'target': target, 'input': input_payload}, separators=(',', ':')).encode('utf-8')
        with urlopen(Request(url, data=body, headers=headers, method='POST'), timeout=30) as response:
            payload = json.loads(response.read().decode('utf-8'))
        if not isinstance(payload, dict):
            raise RuntimeError('operator function returned non-object JSON')
        provider_receipt = payload.get('receiptId') or payload.get('receipt_id') or payload.get('receipt_ref')
        if not isinstance(provider_receipt, str) or not provider_receipt:
            raise RuntimeError('operator function returned no effect receipt')
        status = payload.get('status')
        if status not in {'accepted', 'committed', 'succeeded'}:
            raise RuntimeError('operator function did not report committed effect')
        return payload

    def _require_operator(self, authorization: str) -> None:
        expected = self.config.operator_authorization
        if not expected:
            raise RuntimeError('operator authorization is not configured')
        if not authorization or not hmac.compare_digest(authorization, expected):
            raise PermissionError('operator authorization required')

    def _receipt_entries(self) -> list[dict[str, Any]]:
        if not self.receipt_path.exists():
            return []
        entries = []
        with self.receipt_path.open('r', encoding='utf-8') as fh:
            for line in fh:
                if not line.strip():
                    continue
                value = json.loads(line)
                if isinstance(value, dict):
                    entries.append(value)
        return entries

    def _last_hash(self) -> str | None:
        entries = self._receipt_entries()
        if not entries:
            return None
        value = entries[-1].get('hash')
        return str(value) if value else None


def _constraints_match(constraints: dict[str, Any], payload: object) -> bool:
    if not constraints:
        return True
    if not isinstance(payload, dict):
        return False
    for key, expected in constraints.items():
        if payload.get(key) != expected:
            return False
    return True


def dispatch(
    method: str,
    path: str,
    body: dict[str, Any],
    runtime: GatewayRuntime,
    *,
    authorization: str = '',
) -> tuple[int, dict[str, Any]]:
    if method == 'GET' and path == '/health':
        return 200, {'ok': True, 'service': 'valo-runtime-gateway'}
    try:
        if method == 'POST' and path == '/discover':
            return 200, runtime.discover(body)
        if method == 'POST' and path == '/evaluate':
            return 200, runtime.evaluate(body)
        if method == 'POST' and path == '/receipts':
            return 201, runtime.receipt(body)
        if method == 'GET' and path == '/operator/state':
            return 200, runtime.operator_state(authorization)
        if method == 'POST' and path == '/operator/function':
            return 200, runtime.invoke_operator(body, authorization)
    except PermissionError:
        return 403, {'error': 'forbidden'}
    except ValueError as exc:
        return 400, {'error': 'invalid_request', 'message': str(exc)}
    except Exception as exc:
        return 503, {'error': 'runtime_unavailable', 'message': type(exc).__name__}
    return 404, {'error': 'not_found'}


class Handler(BaseHTTPRequestHandler):
    runtime: GatewayRuntime

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get('Content-Length', '0') or '0')
        if length <= 0:
            return {}
        payload = json.loads(self.rfile.read(length).decode('utf-8'))
        if not isinstance(payload, dict):
            raise ValueError('JSON object required')
        return payload

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        status, payload = dispatch(
            'GET', self.path, {}, self.runtime,
            authorization=self.headers.get('Authorization', ''),
        )
        self._send(status, payload)

    def do_POST(self) -> None:
        try:
            body = self._body()
        except (ValueError, json.JSONDecodeError):
            self._send(400, {'error': 'invalid_json'})
            return
        status, payload = dispatch(
            'POST', self.path, body, self.runtime,
            authorization=self.headers.get('Authorization', ''),
        )
        self._send(status, payload)

    def log_message(self, format: str, *args: object) -> None:
        print(json.dumps({'http': format % args}), flush=True)


def main() -> None:
    runtime = GatewayRuntime(RuntimeConfig.from_env())
    Handler.runtime = runtime
    port = int(os.getenv('PORT', '8080'))
    server = ThreadingHTTPServer(('0.0.0.0', port), Handler)
    print(json.dumps({'event': 'listen', 'service': 'valo-runtime-gateway', 'port': port}), flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
