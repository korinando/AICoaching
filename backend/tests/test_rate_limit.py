"""Rate limits on login, sign-up and starting interviews (Week 7 Step 7): how many tries in a
time window, counted in Redis."""

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from starlette.datastructures import Headers

from app.core import rate_limit
from app.core.rate_limit import (
    LOGIN_PER_EMAIL,
    REGISTER_PER_IP,
    SESSIONS_PER_USER,
    RedisRateLimiter,
    Rule,
    client_ip,
    get_rate_limiter,
)
from app.main import app
from tests.fakes import MemoryRateLimiter, decision

RULE = Rule("test", times=3, seconds=60)


class FakeRedis:
    """Just enough of Redis for the limiter: INCR, EXPIRE NX and TTL in a pipeline."""

    def __init__(self, fail: bool = False) -> None:
        self.counts: dict[str, int] = {}
        self.ttls: dict[str, int] = {}
        self.fail = fail
        self.queued: list = []

    def pipeline(self):
        self.queued = []
        return self

    def incr(self, key):
        self.queued.append(("incr", key))

    def expire(self, key, seconds, nx=False):
        self.queued.append(("expire", key, seconds, nx))

    def ttl(self, key):
        self.queued.append(("ttl", key))

    def execute(self):
        if self.fail:
            raise RedisConnectionError("Redis is down")
        results = []
        for op, key, *rest in self.queued:
            if op == "incr":
                self.counts[key] = self.counts.get(key, 0) + 1
                results.append(self.counts[key])
            elif op == "expire":
                seconds, nx = rest
                if not (nx and key in self.ttls):
                    self.ttls[key] = seconds
                results.append(True)
            else:
                results.append(self.ttls.get(key, -1))
        return results


# --- Counting ----------------------------------------------------------------------------------


def test_allows_that_many_tries_then_says_how_long_to_wait():
    limiter = RedisRateLimiter(FakeRedis())
    assert [limiter.hit(RULE, "a") for _ in range(3)] == [None, None, None]
    assert limiter.hit(RULE, "a") == 60


def test_each_key_has_its_own_count():
    limiter = RedisRateLimiter(FakeRedis())
    for _ in range(3):
        limiter.hit(RULE, "a")
    assert limiter.hit(RULE, "b") is None


def test_the_window_starts_at_the_first_try_and_is_not_pushed_back():
    redis = FakeRedis()
    limiter = RedisRateLimiter(redis)
    limiter.hit(RULE, "a")
    redis.ttls["rate:test:a"] = 10  # 50 seconds later
    limiter.hit(RULE, "a")
    assert redis.ttls["rate:test:a"] == 10  # NX: a new try doesn't restart the window


def test_redis_down_lets_people_in_rather_than_locking_everyone_out():
    assert RedisRateLimiter(FakeRedis(fail=True)).hit(RULE, "a") is None


def test_emails_are_not_stored_in_redis_as_they_are():
    redis = FakeRedis()
    RedisRateLimiter(redis).hit(LOGIN_PER_EMAIL, rate_limit.email_key("An@Example.com"))
    (key,) = redis.counts
    assert "example" not in key.lower()
    assert rate_limit.email_key("An@Example.com") == rate_limit.email_key("an@example.com")


# --- Which address is the visitor? -------------------------------------------------------------


class FakeRequest:
    def __init__(self, headers: dict, host: str = "10.0.0.1") -> None:
        self.headers = Headers(headers)  # like a real request: any upper/lower case matches
        self.client = type("Client", (), {"host": host})()


def test_without_a_proxy_header_setting_the_connection_address_is_used(monkeypatch):
    monkeypatch.setattr(rate_limit, "proxy_ip_header", lambda: "")
    # A header anyone can send is ignored unless we said a trusted proxy sets it.
    assert client_ip(FakeRequest({"x-real-ip": "1.2.3.4"})) == "10.0.0.1"


def test_behind_a_proxy_its_header_is_used(monkeypatch):
    monkeypatch.setattr(rate_limit, "proxy_ip_header", lambda: "X-Real-IP")
    assert client_ip(FakeRequest({"x-real-ip": "1.2.3.4"})) == "1.2.3.4"
    assert client_ip(FakeRequest({})) == "10.0.0.1"  # header missing: fall back


# --- The endpoints -----------------------------------------------------------------------------


@pytest.fixture
def limiter(client) -> MemoryRateLimiter:
    """A limiter that really counts (the client fixture's default lets everything through)."""
    fake = MemoryRateLimiter()
    app.dependency_overrides[get_rate_limiter] = lambda: fake
    return fake


def login(client, email="candidate@example.com"):
    return client.post("/auth/login", json={"email": email, "password": "wrong-password"})


def test_login_is_refused_after_too_many_tries_for_one_email(client, limiter):
    for _ in range(LOGIN_PER_EMAIL.times):
        assert login(client).status_code == 401
    refused = login(client)
    assert refused.status_code == 429
    assert int(refused.headers["Retry-After"]) > 0  # the standard header: seconds to wait
    assert "Too many" in refused.json()["detail"]
    assert login(client, "someone-else@example.com").status_code == 401  # others unaffected


def test_sign_up_is_limited_per_address(client, limiter):
    for i in range(REGISTER_PER_IP.times):
        body = {"email": f"new{i}@example.com", "password": "long-enough-1", "name": "N"}
        assert client.post("/auth/register", json=body).status_code == 201
    body = {"email": "one-more@example.com", "password": "long-enough-1", "name": "N"}
    assert client.post("/auth/register", json=body).status_code == 429


def test_starting_interviews_is_limited_per_user(client, limiter, auth_headers, fake_llm, template):
    for _ in range(SESSIONS_PER_USER.times):
        fake_llm.script.append(decision("next_question", text="Welcome!"))
        response = client.post("/sessions", json={"template_id": template.id}, headers=auth_headers)
        assert response.status_code == 201
    response = client.post("/sessions", json={"template_id": template.id}, headers=auth_headers)
    assert response.status_code == 429
    assert "Too many" in response.json()["detail"]  # this limit, not the daily one
