import os
from pathlib import Path


# =========================================================
# BASE DIRECTORY
# =========================================================

BASE_DIR = Path(__file__).resolve().parent


# =========================================================
# ENVIRONMENT SETTINGS
# =========================================================

APP_ENV = os.getenv("APP_ENV", "development").lower()

DEBUG = APP_ENV == "development"


# =========================================================
# FLASK CONFIGURATION
# =========================================================

class Config:

    # Application security
    SECRET_KEY = os.getenv("SECRET_KEY")

    if not SECRET_KEY:
        if APP_ENV == "production":
            raise RuntimeError(
                "SECRET_KEY must be configured in production."
            )

        SECRET_KEY = "dev-only-change-this-secret-key"

    DEBUG = DEBUG

    # Prevent browsers from accessing session cookies through JavaScript
    SESSION_COOKIE_HTTPONLY = True

    # Send session cookies only over HTTPS in production
    SESSION_COOKIE_SECURE = APP_ENV == "production"

    # Restrict cross-site cookie sending
    SESSION_COOKIE_SAMESITE = "Lax"

    # Session lifetime: 30 minutes
    PERMANENT_SESSION_LIFETIME = 1800


    # =====================================================
    # DATABASE CONFIGURATION
    # =====================================================

    DATABASE_PATH = Path(
        os.getenv(
            "DATABASE_PATH",
            str(BASE_DIR / "facesecure.db")
        )
    )


    # =====================================================
    # FACE RECOGNITION CONFIGURATION
    # =====================================================

    FACE_DIRECTORY = Path(
        os.getenv(
            "FACE_DIRECTORY",
            str(BASE_DIR / "data" / "faces")
        )
    )

    # Face matching tolerance
    # Lower values generally mean stricter matching
    FACE_TOLERANCE = float(
        os.getenv("FACE_TOLERANCE", "0.50")
    )


    # =====================================================
    # UPLOAD CONFIGURATION
    # =====================================================

    # Maximum request size: 5 MB
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024


    # =====================================================
    # AUTHENTICATION CONFIGURATION
    # =====================================================

    # Maximum failed login attempts before additional protection
    MAX_LOGIN_ATTEMPTS = 5

    # Login lockout duration in seconds (15 minutes)
    LOGIN_LOCKOUT_SECONDS = 900


    # =====================================================
    # DIRECTORY INITIALIZATION
    # =====================================================

    @staticmethod
    def initialize_directories():
        """
        Create required directories if they do not exist.
        """
        Config.DATABASE_PATH.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        Config.FACE_DIRECTORY.mkdir(
            parents=True,
            exist_ok=True
        )