from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgenticRiskContext(BaseModel):
    """Non-authoritative risk context derived from an external agent profile.

    These dimensions may inform policy selection or governance intensity, but
    they never grant authority and never bypass REHT consequence-time checks.
    """

    autonomy: float = Field(ge=0.0, le=1.0)
    efficacy: float = Field(ge=0.0, le=1.0)
    goal_complexity: float = Field(ge=0.0, le=1.0)
    generality: float = Field(ge=0.0, le=1.0)
    source: str = "nature-agentic-profile"
    authoritative: bool = False
    model_config = ConfigDict(extra="forbid", frozen=True)


_DIMENSION_ALIASES = {
    "autonomy": ("autonomy",),
    "efficacy": ("efficacy", "causal_efficacy", "causal_impact"),
    "goal_complexity": ("goal_complexity", "goalComplexity"),
    "generality": ("generality",),
}


def _dimension(payload: dict[str, Any], name: str) -> float:
    for key in _DIMENSION_ALIASES[name]:
        if key in payload:
            return float(payload[key])
    raise ValueError(f"missing agentic profile dimension: {name}")


def adapt_nature_agentic_profile(payload: dict[str, Any]) -> AgenticRiskContext:
    """Map the four-dimensional agentic profile into VALO risk context.

    The adapter deliberately performs no ALLOW/DENY decision. Capability/risk
    describes how strongly an agent should be governed; authority remains a
    separate, freshly resolved consequence-time decision.
    """

    return AgenticRiskContext(
        autonomy=_dimension(payload, "autonomy"),
        efficacy=_dimension(payload, "efficacy"),
        goal_complexity=_dimension(payload, "goal_complexity"),
        generality=_dimension(payload, "generality"),
    )
