from app.providers.rate_limit import TokenBucket, backoff_with_jitter, parse_retry_after
from app.providers.whoisfreaks import map_whoisfreaks_status, refine_availability_status
from app.services.domains import classify_registrable_domain


def test_map_statuses():
    assert map_whoisfreaks_status("AVAILABLE") == "AVAILABLE_PRELIMINARY"
    assert map_whoisfreaks_status("UNAVAILABLE") == "TAKEN"
    assert map_whoisfreaks_status("UNKNOWN") == "UNKNOWN"
    assert map_whoisfreaks_status(None) == "UNKNOWN"
    assert map_whoisfreaks_status("RESTRICTED") == "RESTRICTED"
    assert map_whoisfreaks_status("UNSUPPORTED") == "UNSUPPORTED_TLD"
    assert map_whoisfreaks_status("UNSUPPORTED_TLD") == "UNSUPPORTED_TLD"
    assert map_whoisfreaks_status("INVALID") == "INVALID"
    assert map_whoisfreaks_status("PREMIUM") == "PREMIUM"
    assert map_whoisfreaks_status("RESERVED") == "RESERVED"
    # never collapse unsupported into TAKEN
    assert map_whoisfreaks_status("not_supported") != "TAKEN"


def test_classify_invalid_and_unsupported():
    assert classify_registrable_domain("notld")[0] == "INVALID"
    assert classify_registrable_domain(".com")[0] == "INVALID"
    assert classify_registrable_domain("http://x.com")[0] == "INVALID"
    assert classify_registrable_domain("com")[0] == "INVALID"
    # bare public suffix
    status, code = classify_registrable_domain("com.au")
    assert status == "INVALID"
    assert code == "public_suffix_only"
    # normal registrable
    assert classify_registrable_domain("example.com") == (None, None)
    assert classify_registrable_domain("example.com.au") == (None, None)


def test_refine_unknown_invalid_tld():
    # WhoisFreaks often returns UNKNOWN for nonsense TLDs — refine via PSL
    refined = refine_availability_status("this-tld-should-fail.invalidtld", "UNKNOWN", raw="UNKNOWN")
    assert refined in {"UNSUPPORTED_TLD", "UNKNOWN", "INVALID"}
    assert refined != "TAKEN"


def test_token_bucket_and_retry_after():
    bucket = TokenBucket(60.0, capacity=2.0)
    assert bucket.try_acquire(1.0)
    assert bucket.try_acquire(1.0)
    assert not bucket.try_acquire(1.0)
    assert parse_retry_after("3") == 3.0
    assert parse_retry_after(None) == 5.0
    assert backoff_with_jitter(0, base=1.0, cap=10.0) >= 1.0
