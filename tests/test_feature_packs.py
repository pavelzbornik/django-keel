"""Tests for the progressive feature-pack resolver in the billing app (ADR-068).

The resolver is pure Python (no Stripe, no Django), so these tests generate a
project, assert the module renders under the right feature flags, and then import
the rendered module to exercise the cumulative-ladder logic directly.
"""

import importlib.util
import sys

import pytest


def _load_feature_packs(project):
    """Import the generated apps/billing/feature_packs.py as a module."""
    path = project / "apps/billing/feature_packs.py"
    name = "gen_feature_packs"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    # Register before exec so dataclass can resolve the module's annotations.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Generation


@pytest.mark.feature
def test_feature_packs_generated_with_advanced_stripe(generate):
    """The resolver ships when Stripe is enabled (advanced/dj-stripe mode)."""
    project = generate(use_stripe=True, stripe_mode="advanced")

    module_file = project / "apps/billing/feature_packs.py"
    assert module_file.exists()

    source = module_file.read_text()
    assert "class Pack" in source
    assert "class AddOn" in source
    assert "class FeaturePackLadder" in source
    assert "def features_for" in source


@pytest.mark.feature
def test_feature_packs_generated_with_basic_stripe(generate):
    """The resolver is stripe_mode-agnostic — it ships in basic mode too."""
    project = generate(use_stripe=True, stripe_mode="basic")
    assert (project / "apps/billing/feature_packs.py").exists()


@pytest.mark.feature
def test_feature_packs_not_generated_without_stripe(generate):
    """No billing, no resolver."""
    project = generate(use_stripe=False)
    assert not (project / "apps/billing/feature_packs.py").exists()


# Behaviour (rendered module executed directly)


@pytest.mark.feature
def test_ladder_resolves_packs_cumulatively(generate):
    """A higher pack unlocks every lower pack's features (progressive ladder)."""
    module = _load_feature_packs(generate(use_stripe=True, stripe_mode="advanced"))

    ladder = module.FeaturePackLadder(
        packs=[
            module.Pack("free", "Free", frozenset({"spend"})),
            module.Pack("kitchen", "Kitchen", frozenset({"pantry"})),
            module.Pack("planner", "Planner", frozenset({"meals"})),
        ]
    )

    assert ladder.features_for("free") == frozenset({"spend"})
    assert ladder.features_for("planner") == frozenset({"spend", "pantry", "meals"})
    assert ladder.has_feature("pantry", "planner")
    assert not ladder.has_feature("meals", "kitchen")


@pytest.mark.feature
def test_ladder_add_ons_unlock_independently(generate):
    """Add-ons unlock their own features on top of any pack, non-cumulatively."""
    module = _load_feature_packs(generate(use_stripe=True, stripe_mode="advanced"))

    ladder = module.FeaturePackLadder(
        packs=[
            module.Pack("free", "Free", frozenset({"spend"})),
            module.Pack("planner", "Planner", frozenset({"meals"})),
        ],
        add_ons=[module.AddOn("ai_nutrition", "AI Nutrition", frozenset({"photo_log"}))],
    )

    assert ladder.features_for("planner") == frozenset({"spend", "meals"})
    assert ladder.features_for("planner", ["ai_nutrition"]) == frozenset(
        {"spend", "meals", "photo_log"}
    )
    assert not ladder.has_feature("photo_log", "planner")
    assert ladder.has_feature("photo_log", "planner", ["ai_nutrition"])


@pytest.mark.feature
def test_ladder_unknown_slugs_resolve_empty_not_raise(generate):
    """A stale/unknown pack or add-on slug yields no features, never a 500."""
    module = _load_feature_packs(generate(use_stripe=True, stripe_mode="advanced"))

    ladder = module.FeaturePackLadder(
        packs=[module.Pack("free", "Free", frozenset({"spend"}))],
        add_ons=[module.AddOn("ai", "AI", frozenset({"photo"}))],
    )

    assert ladder.features_for("gone") == frozenset()
    assert ladder.features_for("free", ["missing"]) == frozenset({"spend"})
    assert ladder.pack_slugs() == ["free"]
