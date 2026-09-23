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


def test_corrupted_cached_body_is_treated_as_a_miss_not_a_crash(tmp_path):
    db_path = str(tmp_path / "cache.sqlite3")
    c = Cache(db_path=db_path)
    key = c.cache_key({"q": "corrupt me"})
    c._conn.execute("INSERT INTO responses (key, body) VALUES (?, ?)", (key, "not valid json {{{"))
    c._conn.commit()
    assert c.get({"q": "corrupt me"}) is None


def test_concurrent_threads_share_one_cache(tmp_path):
    import threading

    cache = Cache(str(tmp_path / "c.db"))
    errors = []

    def work(n):
        try:
            for i in range(50):
                cache.put({"q": f"{n}-{i}"}, {"v": i})
                assert cache.get({"q": f"{n}-{i}"}) == {"v": i}
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == []
