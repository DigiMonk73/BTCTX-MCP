#!/usr/bin/env python3
"""
backend/tests/test_password_migration.py

Comprehensive authentication tests for BitcoinTX.
Tests the bcrypt password hashing implementation after removing passlib dependency.

These tests verify:
1. Password hashing and verification works correctly
2. 72-byte bcrypt limit is enforced
3. Login/logout endpoints function properly
4. Session-based authentication works
5. Protected endpoints require authentication
6. Password hash format is valid bcrypt

Usage:
    pytest backend/tests/test_password_migration.py -v

    Or run directly:
    python backend/tests/test_password_migration.py
"""

from __future__ import annotations

import sys
import bcrypt
import pytest
from pathlib import Path

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.models.user import User


# =============================================================================
# UNIT TESTS - Password Hashing
# =============================================================================

class TestPasswordHashing:
    """Test the User model's password hashing methods."""

    def test_set_password_creates_valid_hash(self):
        """Verify set_password creates a valid bcrypt hash."""
        user = User(username="testuser")
        user.set_password("mysecretpassword")

        # Hash should start with bcrypt prefix
        assert user.password_hash.startswith("$2")
        # Hash should be proper length (60 chars for bcrypt)
        assert len(user.password_hash) == 60

    def test_verify_password_correct(self):
        """Verify correct password returns True."""
        user = User(username="testuser")
        user.set_password("correctpassword")

        assert user.verify_password("correctpassword") is True

    def test_verify_password_incorrect(self):
        """Verify incorrect password returns False."""
        user = User(username="testuser")
        user.set_password("correctpassword")

        assert user.verify_password("wrongpassword") is False

    def test_verify_password_empty(self):
        """Verify empty password returns False."""
        user = User(username="testuser")
        user.set_password("somepassword")

        assert user.verify_password("") is False

    def test_password_hash_is_unique(self):
        """Verify same password produces different hashes (salt)."""
        user1 = User(username="user1")
        user2 = User(username="user2")

        user1.set_password("samepassword")
        user2.set_password("samepassword")

        # Hashes should be different due to unique salt
        assert user1.password_hash != user2.password_hash

        # But both should verify correctly
        assert user1.verify_password("samepassword") is True
        assert user2.verify_password("samepassword") is True

    def test_password_with_special_characters(self):
        """Verify passwords with special characters work."""
        user = User(username="testuser")
        special_password = "p@$$w0rd!#$%^&*()_+-=[]{}|;':\",./<>?"

        user.set_password(special_password)
        assert user.verify_password(special_password) is True

    def test_password_with_unicode(self):
        """Verify passwords with unicode characters work."""
        user = User(username="testuser")
        unicode_password = "密码🔐パスワード"

        user.set_password(unicode_password)
        assert user.verify_password(unicode_password) is True

    def test_password_72_byte_limit_enforced(self):
        """Verify passwords over 72 bytes raise ValueError."""
        user = User(username="testuser")

        # Create a password that's exactly 73 bytes
        # ASCII characters are 1 byte each
        long_password = "a" * 73

        with pytest.raises(ValueError, match="72 bytes"):
            user.set_password(long_password)

    def test_password_exactly_72_bytes_allowed(self):
        """Verify passwords exactly 72 bytes work."""
        user = User(username="testuser")

        # Exactly 72 ASCII characters = 72 bytes
        exact_password = "a" * 72

        user.set_password(exact_password)
        assert user.verify_password(exact_password) is True

    def test_unicode_password_byte_limit(self):
        """Verify unicode passwords are measured in bytes, not characters."""
        user = User(username="testuser")

        # Each emoji is 4 bytes, so 18 emojis = 72 bytes (at limit)
        emoji_password = "🔐" * 18
        assert len(emoji_password.encode('utf-8')) == 72

        user.set_password(emoji_password)
        assert user.verify_password(emoji_password) is True

        # 19 emojis = 76 bytes (over limit)
        too_long = "🔐" * 19
        with pytest.raises(ValueError, match="72 bytes"):
            user.set_password(too_long)

    def test_bcrypt_hash_format(self):
        """Verify the hash format is valid bcrypt."""
        user = User(username="testuser")
        user.set_password("testpassword")

        # bcrypt hashes have format: $2a$XX$... or $2b$XX$...
        # where XX is the cost factor (default is usually 12)
        parts = user.password_hash.split("$")

        assert len(parts) == 4
        assert parts[0] == ""  # Empty before first $
        assert parts[1] in ("2a", "2b")  # bcrypt version
        assert parts[2].isdigit()  # Cost factor
        assert len(parts[3]) == 53  # Salt + hash (22 + 31)


# =============================================================================
# INTEGRATION TESTS - Auth Endpoints
# =============================================================================


class TestAuthEndpoints:
    """Test the authentication API endpoints."""

    @pytest.fixture
    def session(self, auth_client):
        """
        A fresh, logged-out client (own cookie jar) against the isolated test
        app — no live server on :8000 needed. auth_client ensures the temp-DB
        override and seeded admin user are in place.
        """
        from fastapi.testclient import TestClient
        from backend.main import app
        return TestClient(app)

    def test_login_success(self, session):
        """Test successful login with correct credentials."""
        response = session.post(
            "/api/login",
            json={"username": "admin", "password": "password"}
        )

        assert response.status_code == 200
        data = response.json()
        # API returns {"detail": "Logged in as <username>"}
        assert "Logged in" in data.get("detail", "")

    def test_login_wrong_password(self, session):
        """Test login with wrong password."""
        response = session.post(
            "/api/login",
            json={"username": "admin", "password": "wrongpassword"}
        )

        assert response.status_code == 401

    def test_login_nonexistent_user(self, session):
        """Test login with non-existent username."""
        response = session.post(
            "/api/login",
            json={"username": "nonexistent", "password": "password"}
        )

        assert response.status_code == 401

    def test_logout_clears_session(self, session):
        """Test that logout clears the session."""
        # First login
        login_response = session.post(
            "/api/login",
            json={"username": "admin", "password": "password"}
        )
        assert login_response.status_code == 200

        # Access protected endpoint (should work)
        protected_response = session.get("/api/backup/csv")
        assert protected_response.status_code == 200

        # Logout
        logout_response = session.post("/api/logout")
        assert logout_response.status_code == 200

        # Access protected endpoint again (should fail)
        protected_response = session.get("/api/backup/csv")
        assert protected_response.status_code == 401

    def test_session_persistence(self, session):
        """Test that session persists across requests."""
        # Login
        session.post(
            "/api/login",
            json={"username": "admin", "password": "password"}
        )

        # Multiple requests should maintain auth
        for _ in range(3):
            response = session.get("/api/backup/csv")
            assert response.status_code == 200

    def test_protected_endpoint_without_auth(self, session):
        """Test that protected endpoints require authentication."""
        # Fresh session without login
        response = session.get("/api/backup/csv")
        assert response.status_code == 401

    def test_protected_endpoint_with_auth(self, session):
        """Test that protected endpoints work with authentication."""
        # Login first
        session.post(
            "/api/login",
            json={"username": "admin", "password": "password"}
        )

        # Now access protected endpoint
        response = session.get("/api/backup/csv")
        assert response.status_code == 200


# =============================================================================
# BACKWARD COMPATIBILITY TESTS
# =============================================================================

class TestBackwardCompatibility:
    """Test backward compatibility with existing password hashes."""

    def test_verify_existing_bcrypt_hash(self):
        """Verify we can validate passwords against existing bcrypt hashes."""
        # Simulate an existing hash from the database
        # This is a bcrypt hash of "password"
        existing_hash = bcrypt.hashpw(b"password", bcrypt.gensalt()).decode('utf-8')

        user = User(username="existing_user")
        user.password_hash = existing_hash

        assert user.verify_password("password") is True
        assert user.verify_password("wrongpassword") is False

    def test_different_bcrypt_cost_factors(self):
        """Verify we can validate hashes with different cost factors."""
        user = User(username="testuser")

        # Test with low cost factor (faster for testing)
        low_cost_hash = bcrypt.hashpw(
            b"testpassword",
            bcrypt.gensalt(rounds=4)
        ).decode('utf-8')

        user.password_hash = low_cost_hash
        assert user.verify_password("testpassword") is True

        # Test with default cost factor
        default_cost_hash = bcrypt.hashpw(
            b"testpassword",
            bcrypt.gensalt()  # Default is typically 12
        ).decode('utf-8')

        user.password_hash = default_cost_hash
        assert user.verify_password("testpassword") is True


# =============================================================================
# SECURITY TESTS
# =============================================================================

class TestSecurityProperties:
    """Test security properties of the password system."""

    def test_timing_attack_resistance(self):
        """Verify bcrypt's constant-time comparison is used."""
        user = User(username="testuser")
        user.set_password("correctpassword")

        # bcrypt.checkpw uses constant-time comparison internally
        # We just verify it works correctly with various inputs
        assert user.verify_password("correctpassword") is True
        assert user.verify_password("c") is False
        assert user.verify_password("correctpassword" + "x") is False
        assert user.verify_password("") is False

    def test_hash_not_reversible(self):
        """Verify the password cannot be extracted from the hash."""
        user = User(username="testuser")
        user.set_password("secretpassword")

        # The hash should not contain the plaintext password
        assert "secretpassword" not in user.password_hash
        assert "secret" not in user.password_hash

    def test_null_byte_handling(self):
        """Verify null bytes in passwords are handled safely."""
        user = User(username="testuser")

        # Password with null byte
        password_with_null = "before\x00after"
        user.set_password(password_with_null)

        # Should verify correctly
        assert user.verify_password(password_with_null) is True
        # Should not match truncated version
        assert user.verify_password("before") is False


# =============================================================================
# MAIN - Run tests directly
# =============================================================================

def run_tests():
    """Run all tests and print results."""
    import subprocess
    result = subprocess.run(
        ["pytest", __file__, "-v", "--tb=short"],
        capture_output=False
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(run_tests())
