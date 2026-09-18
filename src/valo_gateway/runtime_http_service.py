from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from uuid import uuid4

from valo_gateway.capability_frontdoor import CapabilityCatalog, CapabilityDescriptor, CapabilityRequest


@dataclass
class RuntimeConfig:
    capabilities: list[dict[str, Any]]
    grants: list[dict[str, Any]]
    receipt_path: str = '/data/receipts.log'

    @classmethod
    def from_env(cls) -> 'RuntimeConfig':
        capabilities = json.loads(os.getenv('GATEWAY_CAPABILITIES_JSON', '[]'))
        grants = json.loads(os.getenv('GATEWAY_GRANTS_JSON', '[]'))
        if not isinstance(capabilities, list) or not isinstance(grants, list):
            raise ValueError('gateway capabilities and grants must be JSON arrays')
        return cls(
            capabilities=capabilities,
            grants=grants,
            receipt_path=os.getenv('GATEWAY_RECEIPT_PATH', '/data/receipts.log'),
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
        capability_id = request.get('capability_id')
        account_ref = request.get('account_ref')
        if not isinstance(principal_id, str) or not isinstance(capability_id, str):
            raise ValueError('principal_id and capability_id are required')
        now = datetime.now(timezone.utc)
        for grant in self.config.grants:
            if grant.get('principal_id') != principal_id:
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

    def _last_hash(self) -> str | None:
        if not self.receipt_path.exists() or self.receipt_path.stat().st_size == 0:
            return None
        last = ''
        with self.receipt_path.open('r', encoding='utf-8') as fh:
            for line in fh:
                if line.strip():
                    last = line
        if not last:
            return None
        payload = json.loads(last)
        value = payload.get('hash')
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


def dispatch(method: str, path: str, body: dict[str, Any], runtime: GatewayRuntime) -> tuple[int, dict[str, Any]]:
    if method == 'GET' and path == '/health':
        return 200, {'ok': True, 'service': 'valo-runtime-gateway'}
    try:
        if method == 'POST' and path == '/discover':
            return 200, runtime.discover(body)
        if method == 'POST' and path == '/evaluate':
            result = runtime.evaluate(body)
            return 200, result
        if method == 'POST' and path == '/receipts':
            return 201, runtime.receipt(body)
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
        status, payload = dispatch('GET', self.path, {}, self.runtime)
        self._send(status, payload)

    def do_POST(self) -> None:
        try:
            body = self._body()
        except (ValueError, json.JSONDecodeError):
            self._send(400, {'error': 'invalid_json'})
            return
        status, payload = dispatch('POST', self.path, body, self.runtime)
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
