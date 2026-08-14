from src.domain.report_generator import ERROR_PATTERNS_VERSION
from scripts.rebuild_diag_report_error_patterns import is_stale_report


def test_stale_report_detection_requires_nonempty_current_versioned_journal():
    assert is_stale_report(None)
    assert is_stale_report({"error_patterns": []})
    assert is_stale_report({"report_meta": {"error_patterns_version": ERROR_PATTERNS_VERSION - 1}, "error_patterns": [{"task_id": "x"}]})
    assert not is_stale_report({"report_meta": {"error_patterns_version": ERROR_PATTERNS_VERSION}, "error_patterns": [{"task_id": "x"}]})
