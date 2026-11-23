from app.logging_utils import redact_url


def test_redact_whoisfreaks_apikey():
    url = "https://api.whoisfreaks.com/v2.0/domain/availability?apiKey=secret123&x=1"
    out = redact_url(url)
    assert "secret123" not in out
    assert "apiKey=***" in out
