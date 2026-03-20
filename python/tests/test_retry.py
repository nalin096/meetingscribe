import time
from meetingscribe.retry import RetryTracker


def test_should_retry_within_max():
    rt = RetryTracker(max_retries=3, backoff_minutes=[1, 5, 30])
    assert rt.should_retry("meeting-1", retry_count=0) is True
    assert rt.should_retry("meeting-1", retry_count=2) is True


def test_should_not_retry_at_max():
    rt = RetryTracker(max_retries=3, backoff_minutes=[1, 5, 30])
    assert rt.should_retry("meeting-1", retry_count=3) is False


def test_get_backoff_returns_correct_delay():
    rt = RetryTracker(max_retries=3, backoff_minutes=[1, 5, 30])
    assert rt.get_backoff_seconds(retry_count=0) == 60
    assert rt.get_backoff_seconds(retry_count=1) == 300
    assert rt.get_backoff_seconds(retry_count=2) == 1800


def test_is_ready_respects_backoff():
    rt = RetryTracker(max_retries=3, backoff_minutes=[0, 0, 0])
    rt.record_attempt("meeting-1")
    assert rt.is_ready("meeting-1", retry_count=0) is True
