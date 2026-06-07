from homebase_bts.urlnorm import NormalizePolicy, normalize, same


def test_strips_tracking_params():
    assert normalize("https://example.com/page?utm_source=x") == "https://example.com/page"


def test_keeps_real_params():
    assert normalize("https://example.com/s?q=cats&utm_medium=ad") == "https://example.com/s?q=cats"


def test_drops_trailing_slash_and_lowercases_host():
    assert normalize("https://Example.COM/path/") == "https://example.com/path"


def test_fragment_dropped_by_default_kept_for_github():
    assert normalize("https://example.com/a#frag") == "https://example.com/a"
    assert normalize("https://github.com/x/y#L20") == "https://github.com/x/y#L20"


def test_keep_fragment_policy():
    pol = NormalizePolicy(keep_fragment=True)
    assert normalize("https://example.com/a#frag", pol) == "https://example.com/a#frag"


def test_same():
    assert same("https://x.com/p?gclid=1", "https://x.com/p")
