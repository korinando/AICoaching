"""Rate limits: at most N tries per time window, counted in Redis (Week 7 Step 7).

Why each one exists:
- login, per email: stops someone guessing one account's password. Each try also costs an Argon2
  hash, which is slow on purpose, so a flood of tries would also tie up the CPU.
- login, per address: stops one machine trying many emails.
- sign-up, per address: the daily interview limit is per account, so endless new accounts would
  get around it.
- starting interviews, per user: each start calls Gemini and the voice. The daily limit caps the
  total; this stops a burst (a script, or a button clicked again and again).

A "fixed window": the first try starts a timer of `seconds`, and every try until it runs out
counts. Simple, and exact enough here; a try just after the window ends starts a new one.
"""

import hashlib
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Protocol

from fastapi import Depends, HTTPException, Request, status
from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Rule:
    name: str
    times: int
    seconds: int


LOGIN_PER_EMAIL = Rule("login-email", times=10, seconds=15 * 60)
LOGIN_PER_IP = Rule("login-ip", times=30, seconds=15 * 60)
REGISTER_PER_IP = Rule("register-ip", times=5, seconds=60 * 60)
SESSIONS_PER_USER = Rule("sessions-user", times=3, seconds=10 * 60)


class RateLimiter(Protocol):
    def hit(self, rule: Rule, key: str) -> int | None:
        """Count one try. None if it's allowed; otherwise the seconds until it will be."""
        ...


class RedisRateLimiter:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    def hit(self, rule: Rule, key: str) -> int | None:
        name = f"rate:{rule.name}:{key}"
        # One round trip for all three. INCR creates the key at 1 if it's missing. EXPIRE NX only
        # sets a timer when there's none, so the window starts at the first try and later tries
        # don't push it back (or someone could stay locked out forever by trying every minute).
        pipe = self.redis.pipeline()
        pipe.incr(name)
        pipe.expire(name, rule.seconds, nx=True)
        pipe.ttl(name)
        try:
            count, _, ttl = pipe.execute()
        except RedisError as e:
            # Fail open: with Redis down, logging in still works. Locking every user out would
            # be worse than a few minutes without limits, and the daily limit (in Postgres) holds.
            logger.warning("Rate limit %s not checked: %s", rule.name, e)
            return None
        return max(ttl, 1) if count > rule.times else None


@lru_cache
def get_rate_limiter() -> RateLimiter:
    # Short timeouts: a slow Redis must not make every login slow.
    redis = Redis.from_url(get_settings().redis_url, socket_connect_timeout=1, socket_timeout=1)
    return RedisRateLimiter(redis)


RateLimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter)]


def enforce(limiter: RateLimiter, rule: Rule, key: str) -> None:
    """Raise 429 Too Many Requests if this try is over the limit."""
    wait = limiter.hit(rule, key)
    if wait is None:
        return
    minutes = -(-wait // 60)  # rounded up: "1 minute" rather than "0 minutes"
    raise HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        f"Too many attempts. Please try again in {minutes} minute{'s' if minutes > 1 else ''}.",
        # The standard header: seconds to wait. Well-behaved clients read it.
        headers={"Retry-After": str(wait)},
    )


def email_key(email: str) -> str:
    """A hash and not the address: Redis then holds no personal data."""
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()[:32]


def proxy_ip_header() -> str:
    return get_settings().proxy_ip_header


def client_ip(request: Request) -> str:
    """The visitor's address.

    On Railway, every request reaches the app through Railway's proxy, so the connection's
    address is the proxy's: the same for everyone. The proxy puts the real one in a header.
    Only read that header when we've said a trusted proxy sets it (PROXY_IP_HEADER): anyone
    can send any header, so trusting it everywhere would let a visitor pick their own address.
    """
    header = proxy_ip_header()
    if header and (value := request.headers.get(header)):
        return value.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
