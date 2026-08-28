from src.campaigns.constants import ATTEMPT_WINDOWS, MAX_ATTEMPTS


def test_max_attempts_is_three():
    """spec §6's 3-attempt policy."""
    assert MAX_ATTEMPTS == 3


def test_attempt_windows_cover_attempts_1_and_2():
    """A window is needed after attempt 1 (before attempt 2) and after attempt 2 (before
    attempt 3) — none after attempt 3, since that's the final automated attempt."""
    assert set(ATTEMPT_WINDOWS) == {1, 2}


def test_delay_seconds_is_bounded_by_min_and_max():
    for window in ATTEMPT_WINDOWS.values():
        low = window.delay_seconds(random_value=0.0)
        high = window.delay_seconds(random_value=1.0)
        assert low == window.min_delay.total_seconds()
        assert high == window.max_delay.total_seconds()
        assert low <= window.delay_seconds(random_value=0.5) <= high


def test_windows_respect_spec_minimum_of_two_hours():
    """spec §6.1: attempt 2 retries 'preferably at least 2-4 hours later'."""
    for window in ATTEMPT_WINDOWS.values():
        assert window.min_delay.total_seconds() >= 2 * 3600
