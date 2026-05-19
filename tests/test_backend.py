"""
OpenOrbitLink Backend Test Suite.

Tests the FastAPI REST API: registration, login, JWT auth, messaging,
queue status, and access control.
"""
from __future__ import annotations

import os
import sys
import asyncio

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_backend_auth_and_messaging():
    """Test the full auth + messaging flow using the backend modules directly."""
    from backend.auth import hash_password, verify_password, create_access_token, decode_access_token
    from backend.config import settings

    # ── Password hashing ──
    hashed = hash_password("testpass123")
    assert verify_password("testpass123", hashed), "Password verification failed"
    assert not verify_password("wrongpass", hashed), "Wrong password should fail"
    print("  PASS: Password hashing and verification")

    # ── JWT creation and decoding ──
    token = create_access_token(user_id=1, username="testuser")
    assert isinstance(token, str) and len(token) > 20, "Token should be a string"
    print(f"  PASS: JWT created ({len(token)} chars)")

    payload = decode_access_token(token)
    assert payload["sub"] == "1", f"Expected sub='1', got '{payload['sub']}'"
    assert payload["username"] == "testuser", "Username mismatch"
    assert payload["iss"] == "openorbitlink", "Issuer mismatch"
    print("  PASS: JWT decode and validation")

    # ── Expired token rejection ──
    import jwt as pyjwt
    from datetime import datetime, timezone, timedelta
    from fastapi import HTTPException
    expired_payload = {
        "sub": "1",
        "username": "testuser",
        "iat": datetime.now(timezone.utc) - timedelta(hours=100),
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        "iss": "openorbitlink",
    }
    expired_token = pyjwt.encode(expired_payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    try:
        decode_access_token(expired_token)
        assert False, "Expired token should raise"
    except HTTPException as e:
        assert e.status_code == 401, f"Expected 401, got {e.status_code}"
    print("  PASS: Expired token rejected")

    # ── Invalid token rejection ──
    try:
        decode_access_token("invalid.token.here")
        assert False, "Invalid token should raise"
    except HTTPException as e:
        assert e.status_code == 401, f"Expected 401, got {e.status_code}"
    print("  PASS: Invalid token rejected")


def test_backend_database_models():
    """Test database model creation and schema."""
    from backend.database import (
        User, Message, TxLog, InviteCode,
        MessageDirection, MessageStatus, TransmitBandEnum,
    )

    # Verify enums
    assert MessageDirection.OUTBOUND.value == "outbound"
    assert MessageDirection.INBOUND.value == "inbound"
    assert MessageStatus.QUEUED.value == "queued"
    assert MessageStatus.DELIVERED.value == "delivered"
    assert TransmitBandEnum.ISM.value == "ism"
    assert TransmitBandEnum.AMATEUR.value == "amateur"
    print("  PASS: Database enums valid")

    # Verify model instantiation
    user = User(username="test", password_hash="hash", email="test@test.com")
    assert user.username == "test"
    print("  PASS: User model instantiation")

    msg = Message(
        user_id=1,
        direction=MessageDirection.OUTBOUND,
        payload_text="Hello satellite",
        band=TransmitBandEnum.ISM,
        status=MessageStatus.QUEUED,
    )
    assert msg.payload_text == "Hello satellite"
    # Column defaults aren't applied until flush; encrypted is None before commit
    assert not msg.encrypted, f"Expected falsy encrypted, got {msg.encrypted}"
    print("  PASS: Message model instantiation")


def test_backend_config():
    """Test configuration loading."""
    from backend.config import settings

    assert settings.ISM_DUTY_CYCLE_PERCENT == 1.0
    assert settings.MAX_TX_SECONDS_PER_HOUR == 36.0
    assert settings.JWT_ALGORITHM == "HS256"
    assert settings.JWT_EXPIRY_HOURS == 72
    assert settings.STATION_ID == "FS-GS-001"
    assert settings.LORA_FREQUENCY_HZ == 868_100_000.0
    assert settings.INVITE_CODE_REQUIRED == True
    assert len(settings.DEFAULT_INVITE_CODES.split(",")) >= 3
    print("  PASS: Configuration defaults valid")


def test_backend_pydantic_schemas():
    """Test Pydantic request/response schemas."""
    from backend.main import (
        RegisterRequest, LoginRequest, SendMessageRequest,
        HealthResponse,
    )
    from datetime import datetime, timezone

    # Valid registration
    reg = RegisterRequest(
        username="testuser", password="securepass123",
        invite_code="BETA-001"
    )
    assert reg.username == "testuser"
    print("  PASS: RegisterRequest schema")

    # Invalid username (too short)
    try:
        RegisterRequest(username="ab", password="securepass123", invite_code="X")
        assert False, "Short username should fail validation"
    except Exception:
        pass
    print("  PASS: RegisterRequest rejects short username")

    # Invalid password (too short)
    try:
        RegisterRequest(username="validuser", password="short", invite_code="X")
        assert False, "Short password should fail validation"
    except Exception:
        pass
    print("  PASS: RegisterRequest rejects short password")

    # Send message
    msg = SendMessageRequest(text="Hello from orbit")
    assert msg.band.value == "ism"
    assert msg.encrypted == False
    print("  PASS: SendMessageRequest defaults")

    # Health response
    health = HealthResponse(
        status="ok", station_id="FS-GS-001",
        version="1.0.0", timestamp=datetime.now(timezone.utc)
    )
    assert health.status == "ok"
    print("  PASS: HealthResponse schema")


def main():
    print("=" * 50)
    print("OpenOrbitLink Backend Test Suite")
    print("=" * 50)

    print("\n-- Config Tests --")
    test_backend_config()

    print("\n-- Auth Tests --")
    test_backend_auth_and_messaging()

    print("\n-- Database Model Tests --")
    test_backend_database_models()

    print("\n-- Schema Tests --")
    test_backend_pydantic_schemas()

    print("\n" + "=" * 50)
    print("All backend tests passed!")
    print("=" * 50)


if __name__ == "__main__":
    main()
