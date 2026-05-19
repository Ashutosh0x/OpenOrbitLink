"""
OpenOrbitLink Database Models & Session Management.

SQLAlchemy async ORM with tables for users, messages, transmission logs,
and invite codes. Uses SQLite for MVP, PostgreSQL-swappable via DATABASE_URL.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship

from .config import settings


# ─── Engine & Session ───────────────────────────────────────────────────

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False}
    if "sqlite" in settings.DATABASE_URL
    else {},
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# ─── Enums ──────────────────────────────────────────────────────────────


class MessageDirection(str, PyEnum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"


class MessageStatus(str, PyEnum):
    QUEUED = "queued"
    TRANSMITTING = "transmitting"
    AWAITING_ACK = "awaiting_ack"
    DELIVERED = "delivered"
    FAILED = "failed"
    EXPIRED = "expired"


class TransmitBandEnum(str, PyEnum):
    ISM = "ism"
    AMATEUR = "amateur"
    LICENSED = "licensed"
    NTN = "ntn"


# ─── Models ─────────────────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    invite_code_used = Column(String(64), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    messages = relationship("Message", back_populates="user", lazy="selectin")
    tx_logs = relationship("TxLog", back_populates="user", lazy="selectin")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    direction = Column(
        Enum(MessageDirection), default=MessageDirection.OUTBOUND, nullable=False
    )
    destination_address = Column(String(128), default="", nullable=False)
    payload_text = Column(Text, nullable=False)
    band = Column(Enum(TransmitBandEnum), default=TransmitBandEnum.ISM, nullable=False)
    encrypted = Column(Boolean, default=False, nullable=False)
    status = Column(
        Enum(MessageStatus), default=MessageStatus.QUEUED, nullable=False, index=True
    )
    bundle_id = Column(String(128), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    transmitted_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="messages")
    tx_log = relationship("TxLog", back_populates="message", uselist=False)

    __table_args__ = (
        Index("idx_user_status", "user_id", "status"),
        Index("idx_user_direction", "user_id", "direction"),
    )


class TxLog(Base):
    """Transmission log — every LoRa TX is logged for ISM regulatory compliance."""

    __tablename__ = "tx_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=True)
    tx_timestamp = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    tx_duration_seconds = Column(Float, nullable=False)
    frequency_hz = Column(Float, default=868_100_000.0, nullable=False)
    duty_cycle_remaining_seconds = Column(Float, nullable=True)

    user = relationship("User", back_populates="tx_logs")
    message = relationship("Message", back_populates="tx_log")


class InviteCode(Base):
    __tablename__ = "invite_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(64), unique=True, nullable=False, index=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    used_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    max_uses = Column(Integer, default=1, nullable=False)
    uses_count = Column(Integer, default=0, nullable=False)


# ─── Init ───────────────────────────────────────────────────────────────


async def init_db():
    """Create all tables and seed default invite codes."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed default invite codes
    async with async_session() as session:
        from sqlalchemy import select

        for code in settings.DEFAULT_INVITE_CODES.split(","):
            code = code.strip()
            if not code:
                continue
            existing = await session.execute(
                select(InviteCode).where(InviteCode.code == code)
            )
            if not existing.scalar_one_or_none():
                session.add(InviteCode(code=code, max_uses=10))
        await session.commit()


async def get_session() -> AsyncSession:
    """FastAPI dependency: yields an async DB session."""
    async with async_session() as session:
        yield session
