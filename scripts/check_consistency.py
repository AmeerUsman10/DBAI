import sys
from pathlib import Path

# Ensure project root is on PYTHONPATH
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.query_classifier import classify_query, get_clarification_for_classification, needs_movement_clarification
from src.query_templates import generate_aggregation_sql


def check_clarification_options():
    q = "top suppliers"
    classification = classify_query(q)
    assert needs_movement_clarification(classification), "Expected movement clarification for supplier ranking"
    options = get_clarification_for_classification(classification)
    assert isinstance(options, list) and len(options) >= 1, "Clarification options missing"
    first = options[0].lower()
    assert "arrival" in first, f"Option #1 should be ARRIVAL, got: {options[0]}"
    print("✅ Clarification mapping stable: 1 = ARRIVAL")


def check_yarn_count_alias():
    params = {
        'department': 'yarn',
        'movement_type': None,
        'time_filter': None
    }
    sql = generate_aggregation_sql(params)
    assert "'Yarn Count'" in sql, "Yarn aggregation must include 'Yarn Count' alias"
    print("✅ Yarn aggregation includes 'Yarn Count' alias")


def check_greige_count_alias():
    params = {
        'department': 'greige',
        'movement_type': None,
        'time_filter': None
    }
    sql = generate_aggregation_sql(params)
    assert "'Greige Count'" in sql, "Greige aggregation must include 'Greige Count' alias"
    print("✅ Greige aggregation includes 'Greige Count' alias")


if __name__ == "__main__":
    ok = True
    try:
        check_clarification_options()
        check_yarn_count_alias()
        check_greige_count_alias()
    except AssertionError as e:
        print(f"❌ Test failed: {e}")
        ok = False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        ok = False
    sys.exit(0 if ok else 1)
