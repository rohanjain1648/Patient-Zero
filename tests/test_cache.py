import os
import tempfile

from patientzero.cache import Cache


def test_cache_key_is_stable_regardless_of_param_order():
    c = Cache(db_path=":memory:")
    key_a = c.cache_key({"q": "hello", "hl": "en"})
    key_b = c.cache_key({"hl": "en", "q": "hello"})
    assert key_a == key_b


def test_cache_miss_returns_none():
    c = Cache(db_path=":memory:")
    assert c.get({"q": "never stored"}) is None


def test_cache_put_then_get_roundtrips():
    c = Cache(db_path=":memory:")
    params = {"q": "roundtrip test", "hl": "en"}
    response = {"organic_results": [{"title": "A"}]}
    c.put(params, response)
    assert c.get(params) == response


def test_cache_persists_to_file(tmp_path):
    db_path = str(tmp_path / "cache.sqlite3")
    c1 = Cache(db_path=db_path)
    c1.put({"q": "persisted"}, {"result": True})
    del c1

    c2 = Cache(db_path=db_path)
    assert c2.get({"q": "persisted"}) == {"result": True}
