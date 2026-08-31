import pytest
from pydantic import ValidationError

from valo_gateway.risk_adapters import adapt_nature_agentic_profile


def test_maps_four_dimensions_as_non_authoritative_context():
    context = adapt_nature_agentic_profile(
        {
            "autonomy": 0.8,
            "efficacy": 0.9,
            "goal_complexity": 0.6,
            "generality": 0.7,
        }
    )

    assert context.autonomy == 0.8
    assert context.efficacy == 0.9
    assert context.goal_complexity == 0.6
    assert context.generality == 0.7
    assert context.authoritative is False


def test_accepts_causal_efficacy_alias():
    context = adapt_nature_agentic_profile(
        {
            "autonomy": 0.2,
            "causal_efficacy": 0.3,
            "goalComplexity": 0.4,
            "generality": 0.5,
        }
    )
    assert context.efficacy == 0.3
    assert context.goal_complexity == 0.4


def test_missing_dimension_fails_closed():
    with pytest.raises(ValueError, match="missing agentic profile dimension"):
        adapt_nature_agentic_profile(
            {"autonomy": 0.2, "efficacy": 0.3, "goal_complexity": 0.4}
        )


def test_out_of_range_dimension_is_rejected():
    with pytest.raises(ValidationError):
        adapt_nature_agentic_profile(
            {
                "autonomy": 1.1,
                "efficacy": 0.3,
                "goal_complexity": 0.4,
                "generality": 0.5,
            }
        )
