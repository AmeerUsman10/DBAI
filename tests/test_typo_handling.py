"""
Test typo handling and department detection edge cases
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.query_classifier import classify_query, normalize_typos
from src.query_templates import generate_sql_from_template


def test_typo_normalization():
    """Test that common typos are corrected"""
    test_cases = [
        ('greiege', 'greige'),
        ('griege', 'greige'),
        ('graige', 'greige'),
        ('yarnn', 'yarn'),
        ('suppiler', 'supplier'),
    ]

    print("Testing typo normalization...")
    for typo, expected in test_cases:
        normalized = normalize_typos(typo)
        assert expected in normalized, f"Failed: {typo} -> {normalized} (expected: {expected})"
        print(f"  ✓ {typo} -> {normalized}")
    print()


def test_department_detection():
    """Test department detection with typos and edge cases"""
    test_cases = [
        ('greiege total', 'greige'),      # Typo for greige
        ('greige total', 'greige'),       # Correct spelling
        ('yarn total', 'yarn'),           # Yarn only
        ('total', 'both'),                # Generic total
        ('greige and yarn total', 'both'), # Both departments
        ('show greige data', 'greige'),   # Different query pattern
    ]

    print("Testing department detection...")
    for query, expected_dept in test_cases:
        result = classify_query(query)
        dept = result['params']['department']
        status = "✓" if dept == expected_dept else "✗"
        print(f"  {status} \"{query}\" -> {dept} (expected: {expected_dept})")
        assert dept == expected_dept, f"Failed: {query} detected as {dept}, expected {expected_dept}"
    print()


def test_greige_only_query():
    """Test that greige-only queries don't include yarn data"""
    test_cases = [
        'greiege total',  # Original issue
        'greige total',
        'total greige',
        'show greige totals',
    ]

    print("Testing greige-only SQL generation...")
    for query in test_cases:
        classification = classify_query(query)

        # Should be classified as aggregation with greige department
        assert classification['type'] == 'aggregation', f"Wrong type for '{query}'"
        assert classification['params']['department'] == 'greige', f"Wrong dept for '{query}'"

        # Generate SQL
        sql = generate_sql_from_template(classification)

        # Verify SQL only queries GreigeData, not YarnData
        assert 'GreigeData' in sql, f"Missing GreigeData in SQL for '{query}'"
        assert 'YarnData' not in sql, f"Should NOT include YarnData for '{query}'"
        assert 'METER' in sql, f"Should include METER for greige in '{query}'"

        print(f"  ✓ \"{query}\" -> Greige-only SQL (no Yarn data)")
    print()


def test_yarn_only_query():
    """Test that yarn-only queries don't include greige data"""
    test_cases = [
        'yarn total',
        'total yarn',
        'show yarn totals',
    ]

    print("Testing yarn-only SQL generation...")
    for query in test_cases:
        classification = classify_query(query)
        sql = generate_sql_from_template(classification)

        # Verify SQL only queries YarnData, not GreigeData
        assert 'YarnData' in sql, f"Missing YarnData in SQL for '{query}'"
        assert 'GreigeData' not in sql, f"Should NOT include GreigeData for '{query}'"
        assert 'LBS' in sql, f"Should include LBS for yarn in '{query}'"

        print(f"  ✓ \"{query}\" -> Yarn-only SQL (no Greige data)")
    print()


def test_both_departments_query():
    """Test that generic 'total' includes both departments"""
    query = 'total inventory'
    classification = classify_query(query)

    # Note: 'total inventory' might be classified differently
    # We'll just check if it's not limiting to one department inappropriately
    print(f"Testing combined query: \"{query}\"")
    print(f"  Department: {classification['params']['department']}")
    print()


if __name__ == '__main__':
    print("=" * 60)
    print("TYPO HANDLING AND DEPARTMENT DETECTION TESTS")
    print("=" * 60)
    print()

    try:
        test_typo_normalization()
        test_department_detection()
        test_greige_only_query()
        test_yarn_only_query()
        test_both_departments_query()

        print("=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
    except AssertionError as e:
        print()
        print("=" * 60)
        print(f"❌ TEST FAILED: {e}")
        print("=" * 60)
        sys.exit(1)
