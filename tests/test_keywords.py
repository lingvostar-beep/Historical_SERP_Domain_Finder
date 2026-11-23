from app.services.keywords import prepare_keywords


def test_dedupe_case_insensitive_keeps_first_original():
    r = prepare_keywords(["  Online Casino  ", "online casino", "", "foo"])
    assert r.unique == 2
    assert r.duplicates_removed == 1
    assert r.invalid >= 1
    originals = [o for o, _n in r.keywords]
    assert "Online Casino" in originals or "  Online Casino  ".strip() in originals


def test_rejects_too_long():
    long_kw = "a" * 701
    r = prepare_keywords([long_kw, "ok"])
    assert r.unique == 1
    assert r.invalid == 1
