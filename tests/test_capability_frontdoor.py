from __future__ import annotations

import pytest

from valo_gateway.capability_frontdoor import (
    CapabilityCatalog,
    CapabilityDescriptor,
    CapabilityFrontDoor,
    CapabilityRequest,
)


class _StagedHandler:
    def __init__(self) -> None:
        self.staged: list[dict[str, object]] = []
        self.committed: list[object] = []

    def stage(self, payload: dict[str, object]) -> dict[str, object]:
        self.staged.append(payload)
        return {"name": payload["name"]}

    def commit(self, stage_ref: object) -> dict[str, object]:
        self.committed.append(stage_ref)
        return {"created": stage_ref["name"]}  # type: ignore[index]


def _catalog() -> CapabilityCatalog:
    return CapabilityCatalog(
        [
            CapabilityDescriptor(
                capability_id="github.create_file",
                provider="github",
                description="Create a UTF-8 file in a GitHub repository",
                verbs=("create", "write"),
                nouns=("file", "github", "repository"),
                risk="effect",
            ),
            CapabilityDescriptor(
                capability_id="notion.search",
                provider="notion",
                description="Search Notion workspace content",
                verbs=("search", "find"),
                nouns=("notion", "page", "workspace"),
                risk="read",
            ),
            CapabilityDescriptor(
                capability_id="n8n.create_workflow",
                provider="n8n",
                description="Create an n8n workflow",
                verbs=("create", "build"),
                nouns=("n8n", "workflow", "automation"),
                risk="effect",
            ),
        ]
    )


def test_discover_returns_only_relevant_capabilities() -> None:
    door = CapabilityFrontDoor(_catalog())
    result = door.discover(CapabilityRequest(intent="create an n8n workflow", limit=2))
    assert [item.capability_id for item in result] == ["n8n.create_workflow"]


def test_discover_caps_context_even_when_catalog_is_large() -> None:
    catalog = CapabilityCatalog(
        CapabilityDescriptor(
            capability_id=f"tool.{index}",
            provider="provider",
            description=f"tool for task {index}",
            verbs=("do",),
            nouns=(f"task{index}",),
            risk="read",
        )
        for index in range(50)
    )
    door = CapabilityFrontDoor(catalog)
    result = door.discover(CapabilityRequest(intent="do task17", limit=3))
    assert 1 <= len(result) <= 3
    assert result[0].capability_id == "tool.17"


def test_invoke_requires_authority_for_effect_capability() -> None:
    door = CapabilityFrontDoor(_catalog())
    door.bind("n8n.create_workflow", _StagedHandler())
    with pytest.raises(PermissionError, match="authority"):
        door.invoke(
            "n8n.create_workflow",
            {"name": "reddit"},
            principal_handle="@njaal",
        )


def test_effect_is_staged_then_committed_when_authority_allows() -> None:
    checked: list[tuple[str, dict[str, object]]] = []
    handler = _StagedHandler()
    door = CapabilityFrontDoor(
        _catalog(),
        authorize=lambda capability_id, payload: checked.append(
            (capability_id, payload)
        )
        or True,
    )
    door.bind("n8n.create_workflow", handler)

    staged = door.invoke(
        "n8n.create_workflow",
        {"name": "reddit"},
        principal_handle="@njaal",
    )
    result = door.commit(staged["receipt_id"])

    assert staged["status"] == "succeeded"
    assert result["response"] == {"created": "reddit"}
    assert result["receipt_id"]
    assert checked == [
        ("n8n.create_workflow", {"name": "reddit"}),
        ("n8n.create_workflow", {"name": "reddit"}),
    ]
    assert door.status(result["receipt_id"])["status"] == "succeeded"


def test_read_capability_does_not_require_effect_authority() -> None:
    door = CapabilityFrontDoor(_catalog())
    door.bind("notion.search", lambda payload: [payload["query"]])
    result = door.invoke("notion.search", {"query": "GAUTE"})
    assert result["response"] == ["GAUTE"]


def test_event_is_normalized_and_stored() -> None:
    door = CapabilityFrontDoor(_catalog())
    event = door.event("n8n", "workflow.completed", {"workflow_id": "wf_1"})
    assert event["event_id"]
    assert event["source"] == "n8n"
    assert event["type"] == "workflow.completed"
    assert door.status(event["event_id"])["payload"] == {"workflow_id": "wf_1"}
