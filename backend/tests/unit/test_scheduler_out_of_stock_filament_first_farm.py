"""Farm: #3590 stock suffix together with the #3587 priority suffix."""

from backend.app.services.print_scheduler import _NO_STOCK_SUFFIX, _PRIORITY_IN, _PRIORITY_IN_RE, _is_filament_wait


def test_stock_suffix_inside_entry_keeps_wait_and_priority_parsing():
    reason = f"Waiting for filament: X1C-1 (needs PLA (Red){_NO_STOCK_SUFFIX})"
    assert _is_filament_wait(reason)
    with_priority = reason + _PRIORITY_IN.format(hours=3)
    assert _is_filament_wait(with_priority)
    m = _PRIORITY_IN_RE.search(with_priority)
    assert m is not None
    assert with_priority[: m.start()] == reason
    assert _NO_STOCK_SUFFIX in with_priority[: m.start()]


def test_no_match_reason_with_stock_suffix_is_a_filament_wait():
    reason = f"No matching material/color. Waiting on PLA (Red){_NO_STOCK_SUFFIX}"
    assert _is_filament_wait(reason)
