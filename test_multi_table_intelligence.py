#!/usr/bin/env python3
"""
Comprehensive test suite for Multi-Table Intelligence System
Tests query analysis, clarification, and routing for Greige/Yarn disambiguation
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.multi_table_intelligence import MultiTableIntelligence


class TestRunner:
    def __init__(self):
        self.mti = MultiTableIntelligence()
        self.passed = 0
        self.failed = 0
        self.tests = []
    
    def test(self, name, condition, expected=True):
        """Run a single test assertion"""
        result = condition == expected
        status = "✓ PASS" if result else "✗ FAIL"
        
        if result:
            self.passed += 1
        else:
            self.failed += 1
        
        self.tests.append({
            "name": name,
            "passed": result,
            "condition": condition,
            "expected": expected
        })
        
        print(f"{status}: {name}")
        if not result:
            print(f"    Expected: {expected}")
            print(f"    Got: {condition}")
    
    def test_group(self, group_name):
        """Print test group header"""
        print(f"\n{'='*70}")
        print(f"  {group_name}")
        print(f"{'='*70}")
    
    def summary(self):
        """Print test summary"""
        total = self.passed + self.failed
        success_rate = (self.passed / total * 100) if total > 0 else 0
        
        print(f"\n{'='*70}")
        print(f"  TEST SUMMARY")
        print(f"{'='*70}")
        print(f"Total Tests: {total}")
        print(f"Passed: {self.passed} ✓")
        print(f"Failed: {self.failed} ✗")
        print(f"Success Rate: {success_rate:.1f}%")
        
        if self.failed > 0:
            print(f"\nFailed tests:")
            for test in self.tests:
                if not test["passed"]:
                    print(f"  - {test['name']}")
        
        return self.failed == 0


def main():
    print("\n" + "="*70)
    print("  Multi-Table Intelligence Test Suite")
    print("  Testing Greige/Yarn Query Disambiguation")
    print("="*70)
    
    runner = TestRunner()
    
    # =========================================================================
    # Test Group 1: Greige-Specific Queries (No Clarification Needed)
    # =========================================================================
    runner.test_group("Test Group 1: Greige-Specific Queries")
    
    queries = [
        "total greige meters",
        "greige inventory",
        "greige fabric summary",
        "show me greige data",
        "greige suppliers",
        "greiege total",  # Typo tolerance
    ]
    
    for query in queries:
        analysis = runner.mti.analyze_query(query)
        runner.test(
            f"'{query}' detected as greige-specific",
            analysis.get("target_entity"),
            "greige"
        )
        runner.test(
            f"'{query}' needs no clarification",
            analysis.get("needs_clarification"),
            False
        )
    
    # =========================================================================
    # Test Group 2: Yarn-Specific Queries (No Clarification Needed)
    # =========================================================================
    runner.test_group("Test Group 2: Yarn-Specific Queries")
    
    queries = [
        "total yarn lbs",
        "yarn inventory in bags",
        "yarn data summary",
        "show me yarn suppliers",
        "cotton yarn count",
    ]
    
    for query in queries:
        analysis = runner.mti.analyze_query(query)
        runner.test(
            f"'{query}' detected as yarn-specific",
            analysis.get("target_entity"),
            "yarn"
        )
        runner.test(
            f"'{query}' needs no clarification",
            analysis.get("needs_clarification"),
            False
        )
    
    # =========================================================================
    # Test Group 3: Ambiguous Queries (Clarification Required)
    # =========================================================================
    runner.test_group("Test Group 3: Ambiguous Queries")
    
    queries = [
        "top suppliers",
        "show me supplier ranking",
        "best vendors",
        "supplier performance",
    ]
    
    for query in queries:
        analysis = runner.mti.analyze_query(query)
        runner.test(
            f"'{query}' needs clarification",
            analysis.get("needs_clarification"),
            True
        )
        runner.test(
            f"'{query}' has clarification message",
            "clarification_message" in analysis,
            True
        )
    
    # =========================================================================
    # Test Group 4: Combined Queries (Auto-Combine)
    # =========================================================================
    runner.test_group("Test Group 4: Combined Queries (Both Tables)")
    
    queries = [
        "overall summary",
        "complete inventory",
        "total inventory report",
        "all departments summary",
    ]
    
    for query in queries:
        analysis = runner.mti.analyze_query(query)
        runner.test(
            f"'{query}' detected as combined query",
            analysis.get("auto_combine"),
            True
        )
        runner.test(
            f"'{query}' needs no clarification (auto-combine)",
            analysis.get("needs_clarification"),
            False
        )
    
    # =========================================================================
    # Test Group 5: Clarification Response Parsing
    # =========================================================================
    runner.test_group("Test Group 5: Clarification Response Parsing")
    
    test_cases = [
        ("1", "greige"),
        ("2", "yarn"),
        ("3", "both"),
        ("1.", "greige"),
        ("2.", "yarn"),
        ("option 1", "greige"),
        ("option 2", "yarn"),
        ("the first one", "greige"),
        ("greige", "greige"),
        ("yarn", "yarn"),
        ("both", "both"),
    ]
    
    for user_input, expected in test_cases:
        result = runner.mti.parse_clarification_response(user_input)
        runner.test(
            f"Parse '{user_input}' → {expected}",
            result,
            expected
        )
    
    # =========================================================================
    # Test Group 6: Result Labels
    # =========================================================================
    runner.test_group("Test Group 6: Result Label Generation")
    
    # Greige label
    analysis = runner.mti.analyze_query("greige total")
    runner.test(
        "Greige query has correct label",
        "Greige" in analysis.get("result_label", ""),
        True
    )
    
    # Yarn label
    analysis = runner.mti.analyze_query("yarn inventory")
    runner.test(
        "Yarn query has correct label",
        "Yarn" in analysis.get("result_label", ""),
        True
    )
    
    # Combined label
    analysis = runner.mti.analyze_query("overall summary")
    runner.test(
        "Combined query has correct label",
        "Combined" in analysis.get("result_label", "") or "Both" in analysis.get("result_label", ""),
        True
    )
    
    # =========================================================================
    # Test Group 7: Edge Cases
    # =========================================================================
    runner.test_group("Test Group 7: Edge Cases")
    
    # Mixed keywords (should ask for clarification or default to both)
    analysis = runner.mti.analyze_query("greige and yarn totals")
    runner.test(
        "Mixed keywords detected (needs clarification or auto-combine)",
        analysis.get("needs_clarification") or analysis.get("auto_combine"),
        True
    )
    
    # Typo tolerance
    analysis = runner.mti.analyze_query("greiege summary")
    runner.test(
        "Greige typo 'greiege' handled correctly",
        analysis.get("target_entity"),
        "greige"
    )
    
    # Case insensitivity
    analysis = runner.mti.analyze_query("GREIGE TOTAL")
    runner.test(
        "Uppercase query handled",
        analysis.get("target_entity"),
        "greige"
    )
    
    analysis = runner.mti.analyze_query("YaRn InVeNtOrY")
    runner.test(
        "Mixed case query handled",
        analysis.get("target_entity"),
        "yarn"
    )
    
    # =========================================================================
    # Test Group 8: Domain Config Loading
    # =========================================================================
    runner.test_group("Test Group 8: Domain Configuration")
    
    runner.test(
        "Domain config loaded",
        runner.mti.config is not None,
        True
    )
    
    runner.test(
        "Entities defined in config",
        "entities" in runner.mti.config,
        True
    )
    
    runner.test(
        "Greige entity exists",
        "greige" in runner.mti.config.get("entities", {}),
        True
    )
    
    runner.test(
        "Yarn entity exists",
        "yarn" in runner.mti.config.get("entities", {}),
        True
    )
    
    runner.test(
        "Ambiguous patterns defined",
        "ambiguous_patterns" in runner.mti.config,
        True
    )
    
    # =========================================================================
    # Test Summary
    # =========================================================================
    success = runner.summary()
    
    if success:
        print("\n🎉 All tests passed! Multi-table intelligence system is ready.")
        return 0
    else:
        print(f"\n⚠️  {runner.failed} test(s) failed. Please review.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
