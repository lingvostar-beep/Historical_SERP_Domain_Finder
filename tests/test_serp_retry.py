from decimal import Decimal

from app.providers.types import SerpFetchResult
from app.services.serp_retry import backoff_seconds, is_retryable


def _fetch(**kwargs) -> SerpFetchResult:
    base = dict(
        provider="test",
        http_status=200,
        top_status_code=20000,
        task_status_code=20000,
        task_status_message="Ok",
        cost_usd=Decimal("0"),
        snapshots=[],
        error=None,
    )
    base.update(kwargs)
    return SerpFetchResult(**base)


def test_retry_on_429_and_5xx_and_network():
    assert is_retryable(_fetch(http_status=429, error="rate limit"))
    assert is_retryable(_fetch(http_status=503, error="unavailable"))
    assert is_retryable(_fetch(http_status=0, error="ConnectTimeout"))


def test_no_retry_on_business_40xxx():
    assert not is_retryable(
        _fetch(http_status=200, task_status_code=40501, error="Invalid Field: date_from")
    )
    assert not is_retryable(_fetch(http_status=200, task_status_code=40102, error="no data"))


def test_no_retry_on_success_or_4xx_http():
    assert not is_retryable(_fetch(http_status=200, task_status_code=20000))
    assert not is_retryable(_fetch(http_status=400, error="bad request", task_status_code=None))


def test_backoff_grows_and_caps():
    a0 = backoff_seconds(0, base=1.0, cap=30.0)
    a3 = backoff_seconds(3, base=1.0, cap=30.0)
    assert 1.0 <= a0 <= 1.25
    assert a3 <= 30.0 * 1.25
