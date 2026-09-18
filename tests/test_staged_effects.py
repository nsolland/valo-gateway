from __future__ import annotations

import pytest

from valo_gateway.capability_frontdoor import (
    CapabilityCatalog,
    CapabilityDescriptor,
    CapabilityFrontDoor,
    PrincipalContext,
)


class StagedHandler:
    def __init__(self) -> None:
        self.staged: list[dict[str, object]] = []
        self.committed: list[object] = []

    def stage(self, payload: dict[str, object]) -> dict[str, str]:
        self.staged.append(payload)
        return {"draft_ref": "draft_1"}

    def commit(self, stage_ref: object) -> dict[str, str]:
        self.committed.append(stage_ref)
        return {"external_id": "done_1"}


def _door(**kwargs: object) -> CapabilityFrontDoor:
    catalog = CapabilityCatalog(
        [
            CapabilityDescriptor(
                capability_id="legal.submit",
                provider="legal",
                description="Submit a legal filing",
                verbs=("submit",),
                nouns=("filing",),
                risk="effect",
            )
        ]
    )
    return CapabilityFrontDoor(catalog, **kwargs)


def test_effect_is_staged_not_executed_until_commit() -> None:
    handler = StagedHandler()
    door = _door(authorize=lambda *_: True)
    door.bind("legal.submit", handler)

    staged = door.invoke("legal.submit", {"matter": "m1"}, principal_handle="@njaal")

    assert staged["status"] == "staged"
    assert handler.staged == [{"matter": "m1"}]
    assert handler.committed == []

    committed = door.commit(staged["receipt_id"])

    assert committed["status"] == "succeeded"
    assert handler.committed == [{"draft_ref": "draft_1"}]


def test_commit_rechecks_authority_fresh() -> None:
    allowed = [True, False]
    handler = StagedHandler()
    door = _door(authorize=lambda *_: allowed.pop(0))
    door.bind("legal.submit", handler)

    staged = door.invoke("legal.submit", {"matter": "m1"}, principal_handle="@njaal")

    with pytest.raises(PermissionError, match="authority"):
        door.commit(staged["receipt_id"])

    assert handler.committed == []


def test_pre_verifier_runs_only_when_policy_requires_it() -> None:
    calls: list[object] = []
    handler = StagedHandler()
    catalog = CapabilityCatalog(
        [
            CapabilityDescriptor(
                "legal.submit",
                "legal",
                "Submit a legal filing",
                risk="effect",
                verification="pre_post",
            )
        ]
    )
    door = CapabilityFrontDoor(
        catalog,
        authorize=lambda *_: True,
        pre_verify=lambda *args: calls.append(args) or True,
    )
    door.bind("legal.submit", handler)

    door.invoke("legal.submit", {"matter": "m1"}, principal_handle="@njaal")

    assert len(calls) == 1


def test_post_verifier_can_flag_committed_effect() -> None:
    handler = StagedHandler()
    catalog = CapabilityCatalog(
        [
            CapabilityDescriptor(
                "legal.submit",
                "legal",
                "Submit a legal filing",
                risk="effect",
                verification="pre_post",
            )
        ]
    )
    door = CapabilityFrontDoor(
        catalog,
        authorize=lambda *_: True,
        pre_verify=lambda *_: True,
        post_verify=lambda *_: False,
    )
    door.bind("legal.submit", handler)

    staged = door.invoke("legal.submit", {"matter": "m1"}, principal_handle="@njaal")
    result = door.commit(staged["receipt_id"])

    assert result["status"] == "verification_failed"
    assert result["verification"] == "semantic_post_failed"


def test_identity_handle_is_resolved_and_bound_to_stage_record() -> None:
    handler = StagedHandler()
    door = _door(
        authorize=lambda *_: True,
        resolve_identity=lambda handle: PrincipalContext(
            handle=handle,
            principal_id="principal_njaal",
            account_ref="account://njaal",
        ),
    )
    door.bind("legal.submit", handler)

    staged = door.invoke("legal.submit", {"matter": "m1"}, principal_handle="@njaal")

    assert staged["principal_handle"] == "@njaal"
    assert staged["principal_id"] == "principal_njaal"
    assert staged["account_ref"] == "account://njaal"
