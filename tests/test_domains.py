from app.services.domains import parse_result_url


def test_com_au_registrable():
    parts = parse_result_url("https://www.example.com.au/path", "www.example.com.au")
    assert parts.hostname == "www.example.com.au"
    assert parts.registrable_domain == "example.com.au"


def test_blog_subdomain_same_registrable():
    a = parse_result_url("https://blog.example.com.au/")
    b = parse_result_url("https://www.example.com.au/")
    assert a.registrable_domain == b.registrable_domain == "example.com.au"
    assert a.hostname != b.hostname


def test_platform_flag_blogspot():
    parts = parse_result_url("https://foo.blogspot.com/x")
    assert parts.is_platform_host is True
