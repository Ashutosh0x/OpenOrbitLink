"""
OpenOrbitLink Backend — FastAPI Application.

REST API for authenticated DTN satellite messaging. Provides user registration
with invite codes, JWT authentication, per-user message queues, and ISM
duty-cycle-aware transmission scheduling.

Usage:
    uvicorn backend.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import (
    consume_invite_code,
    create_access_token,
    get_current_user,
    hash_password,
    validate_invite_code,
    verify_password,
)
from .config import settings
from .database import (
    Message,
    MessageDirection,
    MessageStatus,
    TransmitBandEnum,
    User,
    get_session,
    init_db,
)
from .rate_limiter import duty_cycle_tracker
from .tx_queue import tx_queue
from .satellite_radar import (
    init_radar_engine,
    radar_websocket_endpoint,
    router as radar_router,
)
from .adaptive_modem import router as modem_router
from .lr_fhss import router as lr_fhss_router
from .turbo_compression import compression_router
from .speed_test import speedtest_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("OpenOrbitLink.API")


# ─── Lifespan ───────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB + start TX worker. Shutdown: drain queue."""
    logger.info("=" * 60)
    logger.info("OpenOrbitLink Backend v1.0.0-alpha")
    logger.info(f"Station: {settings.STATION_ID}")
    logger.info(f"LoRa frequency: {settings.LORA_FREQUENCY_HZ / 1e6:.1f} MHz")
    logger.info(f"ISM duty cycle: {settings.ISM_DUTY_CYCLE_PERCENT}%")
    logger.info(f"Max TX/hour: {settings.MAX_TX_SECONDS_PER_HOUR}s")
    logger.info("=" * 60)

    await init_db()
    await tx_queue.start()

    # Initialize satellite radar engine
    try:
        radar = init_radar_engine(
            observer_lat=28.6139,
            observer_lon=77.2090,
            observer_alt=216.0,
        )
        logger.info(f"Satellite radar: {len(radar.catalog)} satellites loaded")
    except Exception as e:
        logger.warning(f"Satellite radar init failed: {e}")

    yield
    await tx_queue.stop()


# ─── App ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="OpenOrbitLink API",
    description=(
        "REST API for delay-tolerant satellite messaging over LoRa/ISM bands. "
        "Provides JWT authentication, per-user message queues, and ISM duty-cycle "
        "rate limiting for the closed beta (10-20 users)."
    ),
    version="1.0.0-alpha",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register satellite radar router
app.include_router(radar_router)

# Register adaptive modem & LR-FHSS high-throughput routers
if modem_router:
    app.include_router(modem_router)
    logger.info("Adaptive modem router registered")
if lr_fhss_router:
    app.include_router(lr_fhss_router)
    logger.info("LR-FHSS router registered")

# Register Starlink-inspired feature routers
app.include_router(compression_router)
logger.info("Turbo compression router registered (3 endpoints)")
app.include_router(speedtest_router)
logger.info("Speed test & network stats router registered (5 endpoints)")

# Register Starlink-inspired intelligence router
from .starlink_intelligence import starlink_router
app.include_router(starlink_router)
logger.info("Starlink intelligence router registered (4 endpoints)")

# Register benchmark suite router
from .benchmark import benchmark_router
app.include_router(benchmark_router)
logger.info("Benchmark suite router registered (3 endpoints)")

# Register voice messaging & comparison routers
from .voice_messaging import voice_router, comparison_router
app.include_router(voice_router)
app.include_router(comparison_router)
logger.info("Voice messaging (3) + Starlink comparison (2) routers registered")



# WebSocket for real-time satellite streaming
@app.websocket("/ws/radar")
async def ws_radar(websocket):
    """Real-time satellite position WebSocket (1Hz updates)."""
    await radar_websocket_endpoint(websocket)


# ─── Pydantic Schemas ──────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_\-]+$")
    password: str = Field(..., min_length=8, max_length=128)
    email: Optional[str] = Field(None, max_length=255)
    invite_code: str = Field(..., min_length=4, max_length=64)


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str
    expires_in_hours: int


class UserProfile(BaseModel):
    id: int
    username: str
    email: Optional[str]
    is_active: bool
    created_at: datetime
    message_count: int = 0
    duty_cycle_remaining: float = 0.0


class SendMessageRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    destination: str = Field("", max_length=128)
    band: TransmitBandEnum = TransmitBandEnum.ISM
    encrypted: bool = False


class MessageResponse(BaseModel):
    id: int
    direction: str
    destination_address: str
    payload_text: str
    band: str
    encrypted: bool
    status: str
    bundle_id: Optional[str]
    created_at: datetime
    transmitted_at: Optional[datetime]
    delivered_at: Optional[datetime]


class QueueStatusResponse(BaseModel):
    queued: int
    transmitting: int
    awaiting_ack: int
    delivered: int
    failed: int
    total: int


class StationStatusResponse(BaseModel):
    station_id: str
    frequency_mhz: float
    duty_cycle: dict
    tx_queue: dict
    uptime_info: str


class HealthResponse(BaseModel):
    status: str
    station_id: str
    version: str
    timestamp: datetime


# ─── Health ─────────────────────────────────────────────────────────────


@app.get("/api/v1/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint (no auth required)."""
    return HealthResponse(
        status="ok",
        station_id=settings.STATION_ID,
        version="1.0.0-alpha",
        timestamp=datetime.now(timezone.utc),
    )


# ─── Auth Endpoints ────────────────────────────────────────────────────


@app.post(
    "/api/v1/auth/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Auth"],
)
async def register(
    req: RegisterRequest, session: AsyncSession = Depends(get_session)
):
    """Register a new user with an invite code."""
    # Check invite code
    if settings.INVITE_CODE_REQUIRED:
        invite = await validate_invite_code(req.invite_code, session)
        if invite is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or exhausted invite code",
            )

    # Check username uniqueness
    existing = await session.execute(
        select(User).where(User.username == req.username)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already taken",
        )

    # Check email uniqueness
    if req.email:
        existing_email = await session.execute(
            select(User).where(User.email == req.email)
        )
        if existing_email.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )

    # Create user
    user = User(
        username=req.username,
        email=req.email,
        password_hash=hash_password(req.password),
        invite_code_used=req.invite_code,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    # Consume invite code
    if settings.INVITE_CODE_REQUIRED:
        await consume_invite_code(invite, user.id, session)

    # Issue JWT
    token = create_access_token(user.id, user.username)

    logger.info(f"New user registered: {user.username} (ID: {user.id})")

    return AuthResponse(
        access_token=token,
        user_id=user.id,
        username=user.username,
        expires_in_hours=settings.JWT_EXPIRY_HOURS,
    )


@app.post("/api/v1/auth/login", response_model=AuthResponse, tags=["Auth"])
async def login(req: LoginRequest, session: AsyncSession = Depends(get_session)):
    """Authenticate and receive a JWT token."""
    result = await session.execute(
        select(User).where(User.username == req.username)
    )
    user = result.scalar_one_or_none()

    if user is None or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account deactivated",
        )

    token = create_access_token(user.id, user.username)

    logger.info(f"User logged in: {user.username}")

    return AuthResponse(
        access_token=token,
        user_id=user.id,
        username=user.username,
        expires_in_hours=settings.JWT_EXPIRY_HOURS,
    )


@app.get("/api/v1/auth/me", response_model=UserProfile, tags=["Auth"])
async def get_profile(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get current user profile."""
    # Count messages
    result = await session.execute(
        select(func.count(Message.id)).where(Message.user_id == user.id)
    )
    message_count = result.scalar() or 0

    budget = duty_cycle_tracker.get_budget(user.id)

    return UserProfile(
        id=user.id,
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        created_at=user.created_at,
        message_count=message_count,
        duty_cycle_remaining=budget.remaining_seconds,
    )


# ─── Messaging Endpoints ───────────────────────────────────────────────


@app.post(
    "/api/v1/send",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Messaging"],
)
async def send_message(
    req: SendMessageRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Enqueue a message for satellite transmission."""
    # Validate band/encryption policy
    if req.band == TransmitBandEnum.AMATEUR and req.encrypted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Encryption is not allowed on amateur band transmissions",
        )

    # Check rate limit (messages per hour)
    one_hour_ago = datetime.now(timezone.utc).replace(
        hour=datetime.now(timezone.utc).hour - 1
        if datetime.now(timezone.utc).hour > 0
        else 23
    )
    result = await session.execute(
        select(func.count(Message.id))
        .where(Message.user_id == user.id)
        .where(Message.created_at >= one_hour_ago)
    )
    recent_count = result.scalar() or 0
    if recent_count >= settings.MAX_MESSAGES_PER_USER_PER_HOUR:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit: max {settings.MAX_MESSAGES_PER_USER_PER_HOUR} messages per hour",
        )

    # Check payload size
    if len(req.text.encode("utf-8")) > settings.MAX_PAYLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Payload exceeds {settings.MAX_PAYLOAD_BYTES} byte limit",
        )

    # Check duty cycle budget
    budget = duty_cycle_tracker.get_budget(user.id)
    if not budget.can_transmit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"ISM duty cycle exhausted. "
                f"Next window in {budget.next_available_in_seconds:.0f}s"
            ),
        )

    # Create message
    message = Message(
        user_id=user.id,
        direction=MessageDirection.OUTBOUND,
        destination_address=req.destination,
        payload_text=req.text,
        band=req.band,
        encrypted=req.encrypted,
        status=MessageStatus.QUEUED,
    )
    session.add(message)
    await session.commit()
    await session.refresh(message)

    logger.info(
        f"Message queued: user={user.username} id={message.id} "
        f"band={req.band.value} dest='{req.destination}'"
    )

    return _message_to_response(message)


@app.get("/api/v1/inbox", response_model=List[MessageResponse], tags=["Messaging"])
async def get_inbox(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get received messages for the current user."""
    result = await session.execute(
        select(Message)
        .where(Message.user_id == user.id)
        .where(Message.direction == MessageDirection.INBOUND)
        .order_by(Message.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    messages = result.scalars().all()
    return [_message_to_response(m) for m in messages]


@app.get("/api/v1/queue", response_model=QueueStatusResponse, tags=["Messaging"])
async def get_queue_status(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get the current user's outbound message queue status."""
    counts = {}
    for s in MessageStatus:
        result = await session.execute(
            select(func.count(Message.id))
            .where(Message.user_id == user.id)
            .where(Message.direction == MessageDirection.OUTBOUND)
            .where(Message.status == s)
        )
        counts[s.value] = result.scalar() or 0

    return QueueStatusResponse(
        queued=counts.get("queued", 0),
        transmitting=counts.get("transmitting", 0),
        awaiting_ack=counts.get("awaiting_ack", 0),
        delivered=counts.get("delivered", 0),
        failed=counts.get("failed", 0),
        total=sum(counts.values()),
    )


@app.get(
    "/api/v1/messages",
    response_model=List[MessageResponse],
    tags=["Messaging"],
)
async def get_all_messages(
    direction: Optional[str] = Query(None, pattern="^(inbound|outbound)$"),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get all messages for the current user with optional filters."""
    query = select(Message).where(Message.user_id == user.id)

    if direction:
        query = query.where(Message.direction == MessageDirection(direction))
    if status_filter:
        query = query.where(Message.status == MessageStatus(status_filter))

    query = query.order_by(Message.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(query)
    messages = result.scalars().all()
    return [_message_to_response(m) for m in messages]


# ─── Station Status ────────────────────────────────────────────────────


@app.get(
    "/api/v1/status", response_model=StationStatusResponse, tags=["Station"]
)
async def get_station_status(user: User = Depends(get_current_user)):
    """Get ground station status and duty cycle budget."""
    return StationStatusResponse(
        station_id=settings.STATION_ID,
        frequency_mhz=settings.LORA_FREQUENCY_HZ / 1e6,
        duty_cycle=duty_cycle_tracker.get_global_status(),
        tx_queue=tx_queue.get_stats(),
        uptime_info="Phase 1 closed beta — invite-only access",
    )


# ─── Helpers ────────────────────────────────────────────────────────────


def _message_to_response(msg: Message) -> MessageResponse:
    return MessageResponse(
        id=msg.id,
        direction=msg.direction.value if msg.direction else "outbound",
        destination_address=msg.destination_address or "",
        payload_text=msg.payload_text,
        band=msg.band.value if msg.band else "ism",
        encrypted=msg.encrypted,
        status=msg.status.value if msg.status else "queued",
        bundle_id=msg.bundle_id,
        created_at=msg.created_at,
        transmitted_at=msg.transmitted_at,
        delivered_at=msg.delivered_at,
    )


# ─── Run ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True,
    )
