from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DB, CurrentUser
from app.api.schemas import LoginRequest, RefreshRequest, RegisterRequest, TokenPair, UserOut
from app.core.rate_limit import (
    LOGIN_PER_EMAIL,
    LOGIN_PER_IP,
    REGISTER_PER_IP,
    RateLimiterDep,
    client_ip,
    email_key,
    enforce,
)
from app.core.security import (
    DUMMY_HASH,
    TokenError,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


def _tokens_for(user_id: int) -> TokenPair:
    return TokenPair(
        access_token=create_token(user_id, "access"),
        refresh_token=create_token(user_id, "refresh"),
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: DB, request: Request, limiter: RateLimiterDep) -> UserOut:
    # Per address: each account gets its own daily interviews, so endless sign-ups would get
    # around that limit.
    enforce(limiter, REGISTER_PER_IP, client_ip(request))
    # Lowercase: "An@Mail.com" and "an@mail.com" are the same person.
    user = User(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        name=body.name,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # The unique constraint from Step 3 caught it, even if two requests raced.
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from None
    db.refresh(user)  # load created_at, which Postgres filled in
    return UserOut.model_validate(user)


@router.post("/login")
def login(body: LoginRequest, db: DB, request: Request, limiter: RateLimiterDep) -> TokenPair:
    # Before the password check: that check is slow on purpose, so it's also what a flood
    # of tries would use up.
    enforce(limiter, LOGIN_PER_IP, client_ip(request))
    enforce(limiter, LOGIN_PER_EMAIL, email_key(body.email))
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    # Always run one hash check, even for an unknown email: otherwise "no such user" answers
    # faster than "wrong password", and the timing would reveal which emails have accounts.
    password_ok = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if user is None or not password_ok:
        # One message for both cases, for the same reason.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return _tokens_for(user.id)


@router.post("/refresh")
def refresh(body: RefreshRequest, db: DB) -> TokenPair:
    """Trade a valid refresh token for a new pair, so the user stays logged in."""
    try:
        user_id = decode_token(body.refresh_token, expected_type="refresh")
    except TokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token") from None
    if db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    return _tokens_for(user_id)


@router.get("/me")
def me(user: CurrentUser) -> UserOut:
    """Who am I? The frontend calls this to check the login is still valid."""
    return UserOut.model_validate(user)
