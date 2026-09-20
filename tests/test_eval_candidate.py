#!/usr/bin/env python3
"""Unit tests for the determine_verdict function in scripts/eval_candidate.py.

Tests the SRCH-006 heavy position anti-masking guard alongside existing verdict logic.
"""

import os
import sys
import unittest

# Add scripts/ to path so we can import eval_candidate
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from eval_candidate import (
    HEAVY_POSITIONS,
    HEAVY_REGRESSION_THRESHOLD_PCT,
    determine_verdict,
)


def _make_summary(total_node_delta_pct):
    """Helper: create a minimal summary dict with the given aggregate node delta."""
    return {
        "total_candidate_nodes": 34_000_000_000,
        "total_baseline_nodes": 34_400_000_000,
        "total_node_delta_pct": total_node_delta_pct,
        "total_candidate_time": 100.0,
        "total_baseline_time": 105.0,
        "total_time_delta_pct": -4.76,
    }


def _make_comparison(**overrides):
    """Helper: create a comparison dict with per-position node deltas.

    By default, all positions are neutral (0.0% delta).
    Pass keyword overrides as position_name=delta_pct (e.g., ffo55=+1.5).
    """
    # Map short names to FFO names
    name_map = {
        "ffo40": "FFO #40", "ffo41": "FFO #41", "ffo42": "FFO #42",
        "ffo43": "FFO #43", "ffo44": "FFO #44", "ffo45": "FFO #45",
        "ffo46": "FFO #46", "ffo47": "FFO #47", "ffo48": "FFO #48",
        "ffo49": "FFO #49", "ffo50": "FFO #50", "ffo51": "FFO #51",
        "ffo52": "FFO #52", "ffo53": "FFO #53", "ffo54": "FFO #54",
        "ffo55": "FFO #55", "ffo56": "FFO #56", "ffo57": "FFO #57",
        "ffo59": "FFO #59",
    }
    comparison = {}
    for short, ffo_name in name_map.items():
        delta = overrides.get(short, 0.0)
        comparison[ffo_name] = {
            "candidate_nodes": 1_000_000,
            "baseline_nodes": 1_000_000,
            "node_delta_pct": delta,
            "candidate_time": 1.0,
            "baseline_time": 1.0,
            "time_delta_pct": 0.0,
        }
    return comparison


class TestDetermineVerdictBasic(unittest.TestCase):
    """Tests for existing (pre-SRCH-006) verdict logic."""

    def test_timeout_takes_priority(self):
        verdict, reason = determine_verdict(
            "full", True, True, _make_summary(-2.0),
            timed_out_positions=["FFO #55"]
        )
        self.assertEqual(verdict, "REJECT_TIMEOUT")

    def test_correctness_failure(self):
        verdict, _ = determine_verdict("full", False, True, _make_summary(-2.0))
        self.assertEqual(verdict, "REJECT_CORRECTNESS")

        verdict, _ = determine_verdict("full", True, False, _make_summary(-2.0))
        self.assertEqual(verdict, "REJECT_CORRECTNESS")

    def test_no_baseline(self):
        verdict, _ = determine_verdict("full", True, True, None)
        self.assertEqual(verdict, "ACCEPT_NO_BASELINE")

    def test_aggregate_regression(self):
        verdict, reason = determine_verdict("full", True, True, _make_summary(+0.8))
        self.assertEqual(verdict, "REJECT_REGRESSION")
        self.assertIn("+0.80%", reason)

    def test_screen_needs_full(self):
        verdict, _ = determine_verdict("screen", True, True, _make_summary(-1.0))
        self.assertEqual(verdict, "NEEDS_FULL")

    def test_full_accept(self):
        verdict, _ = determine_verdict("full", True, True, _make_summary(-1.0))
        self.assertEqual(verdict, "ACCEPT")

    def test_neutral(self):
        verdict, _ = determine_verdict("full", True, True, _make_summary(0.1))
        self.assertEqual(verdict, "NEUTRAL")

    def test_neutral_boundary(self):
        verdict, _ = determine_verdict("full", True, True, _make_summary(0.5))
        self.assertEqual(verdict, "NEUTRAL")

        verdict, _ = determine_verdict("full", True, True, _make_summary(-0.5))
        self.assertEqual(verdict, "NEUTRAL")


class TestHeavyPositionGuard(unittest.TestCase):
    """Tests for SRCH-006 heavy position anti-masking guard."""

    def test_heavy_regression_rejects_despite_aggregate_improvement(self):
        """Core anti-masking scenario: aggregate is great (-2.0%) but FFO #55 regressed +1.5%."""
        comparison = _make_comparison(ffo55=1.5)
        verdict, reason = determine_verdict(
            "full", True, True, _make_summary(-2.0),
            comparison=comparison
        )
        self.assertEqual(verdict, "REJECT_REGRESSION")
        self.assertIn("FFO #55", reason)
        self.assertIn("anti-masking guard", reason)
        self.assertIn("+1.50%", reason)

    def test_multiple_heavy_regressions(self):
        """Multiple heavy positions regressing should all be listed."""
        comparison = _make_comparison(ffo53=2.0, ffo55=1.5, ffo57=3.0)
        verdict, reason = determine_verdict(
            "full", True, True, _make_summary(-2.0),
            comparison=comparison
        )
        self.assertEqual(verdict, "REJECT_REGRESSION")
        self.assertIn("FFO #53", reason)
        self.assertIn("FFO #55", reason)
        self.assertIn("FFO #57", reason)

    def test_heavy_position_within_threshold_passes(self):
        """Heavy positions at or below threshold should not trigger guard."""
        comparison = _make_comparison(ffo55=0.8, ffo53=1.0)  # 1.0 is not > 1.0
        verdict, _ = determine_verdict(
            "full", True, True, _make_summary(-2.0),
            comparison=comparison
        )
        self.assertEqual(verdict, "ACCEPT")

    def test_non_heavy_position_regression_ignored_by_guard(self):
        """Non-heavy positions (e.g. FFO #45) regressing > 1.0% should NOT trigger the heavy guard."""
        comparison = _make_comparison(ffo45=5.0)
        verdict, _ = determine_verdict(
            "full", True, True, _make_summary(-2.0),
            comparison=comparison
        )
        # Should pass because FFO #45 is not a heavy position
        self.assertEqual(verdict, "ACCEPT")

    def test_heavy_guard_applies_in_screen_mode(self):
        """Heavy guard should trigger even in screen mode."""
        comparison = _make_comparison(ffo55=2.0)
        verdict, reason = determine_verdict(
            "screen", True, True, _make_summary(-2.0),
            comparison=comparison
        )
        self.assertEqual(verdict, "REJECT_REGRESSION")
        self.assertIn("anti-masking guard", reason)

    def test_custom_heavy_threshold(self):
        """Custom heavy_threshold should override the default."""
        comparison = _make_comparison(ffo55=1.5)

        # With default threshold (1.0%), this should reject
        verdict, _ = determine_verdict(
            "full", True, True, _make_summary(-2.0),
            comparison=comparison, heavy_threshold=1.0
        )
        self.assertEqual(verdict, "REJECT_REGRESSION")

        # With higher threshold (2.0%), this should accept
        verdict, _ = determine_verdict(
            "full", True, True, _make_summary(-2.0),
            comparison=comparison, heavy_threshold=2.0
        )
        self.assertEqual(verdict, "ACCEPT")

    def test_no_comparison_skips_guard(self):
        """When comparison is None, heavy guard is skipped (backward compat)."""
        verdict, _ = determine_verdict(
            "full", True, True, _make_summary(-2.0),
            comparison=None
        )
        self.assertEqual(verdict, "ACCEPT")

    def test_timeout_still_takes_priority_over_heavy_guard(self):
        """Timeout should still win over heavy position regression."""
        comparison = _make_comparison(ffo55=5.0)
        verdict, _ = determine_verdict(
            "full", True, True, _make_summary(-2.0),
            timed_out_positions=["FFO #55"],
            comparison=comparison
        )
        self.assertEqual(verdict, "REJECT_TIMEOUT")

    def test_correctness_still_takes_priority_over_heavy_guard(self):
        """Correctness failure should still win over heavy position regression."""
        comparison = _make_comparison(ffo55=5.0)
        verdict, _ = determine_verdict(
            "full", False, True, _make_summary(-2.0),
            comparison=comparison
        )
        self.assertEqual(verdict, "REJECT_CORRECTNESS")

    def test_heavy_guard_before_aggregate_regression(self):
        """When both aggregate and heavy regress, heavy guard message should appear (checked first)."""
        comparison = _make_comparison(ffo55=2.0)
        verdict, reason = determine_verdict(
            "full", True, True, _make_summary(+1.0),
            comparison=comparison
        )
        self.assertEqual(verdict, "REJECT_REGRESSION")
        # Heavy guard fires first, so reason should mention anti-masking
        self.assertIn("anti-masking guard", reason)

    def test_heavy_positions_set_correct(self):
        """Verify the HEAVY_POSITIONS constant contains the expected positions."""
        self.assertEqual(HEAVY_POSITIONS, {"FFO #53", "FFO #54", "FFO #55", "FFO #57"})

    def test_default_threshold(self):
        """Verify the default threshold constant."""
        self.assertEqual(HEAVY_REGRESSION_THRESHOLD_PCT, 1.0)


if __name__ == "__main__":
    unittest.main()
