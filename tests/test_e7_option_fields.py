"""Wave E7 / DU-05, pinned BEFORE any code change: which field of an answer option each place reads. No decision on the order exists yet (the
recheck proposes «the screen is the reference»), so this only records today's two orders."""
from src.domain import task_display
from src.domain.report_generator import _option_value


def test_an_option_with_text_and_value_is_read_in_two_orders_today():
    option = {"text": "x > 0", "value": "x>0"}
    assert task_display._extract_option_text(option) == "x > 0"      # the screen and the grader: text first
    assert _option_value(option) == "x>0"                            # today: the report looks at `value` first (DU-05)


def test_a_numeric_zero_option_is_lost_by_the_report_chain_today():
    assert task_display._extract_option_text({"value": 0}) == "0"
    assert _option_value({"value": 0}) == ""                         # today: the `or` chain drops 0 (DU-05)
