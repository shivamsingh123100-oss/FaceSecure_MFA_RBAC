import sqlite3
from datetime import datetime, timezone

from flask import current_app, g


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_db():
    """
    Create or reuse the SQLite connection for the current request.
    """

    if "db" not in g:

        g.db = sqlite3.connect(
            current_app.config["DATABASE_PATH"]
        )

        g.db.row_factory = sqlite3.Row

        # Enable foreign-key support.
        g.db.execute("PRAGMA foreign_keys = ON")

    return g.db


def close_db(error=None):
    """
    Close the database connection after the request finishes.
    """

    db = g.pop("db", None)

    if db is not None:
        db.close()


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_db():
    """
    Create all required database tables.

    Also upgrades an existing database by adding any missing
    columns to activity_logs.
    """

    db = get_db()

    # ========================================================
    # USERS TABLE
    # ========================================================

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS users (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            username TEXT NOT NULL UNIQUE,

            full_name TEXT NOT NULL,

            password_hash TEXT NOT NULL,

            role TEXT NOT NULL
                CHECK (
                    role IN ('USER', 'ADMIN')
                ),

            status TEXT NOT NULL
                CHECK (
                    status IN (
                        'PENDING',
                        'VERIFIED',
                        'REJECTED'
                    )
                ),

            face_path TEXT,

            created_at TEXT NOT NULL,

            verified_at TEXT,

            verified_by INTEGER,

            FOREIGN KEY (verified_by)
                REFERENCES users(id)
                ON DELETE SET NULL
        )
        """
    )

    # ========================================================
    # ACTIVITY LOGS TABLE
    # ========================================================

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS activity_logs (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER,

            username TEXT,

            role TEXT,

            action TEXT NOT NULL,

            status TEXT,

            ip_address TEXT,

            details TEXT,

            created_at TEXT NOT NULL,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE SET NULL
        )
        """
    )

    # ========================================================
    # CHECK EXISTING ACTIVITY_LOGS COLUMNS
    # ========================================================

    existing_columns = {
        row["name"]
        for row in db.execute(
            "PRAGMA table_info(activity_logs)"
        ).fetchall()
    }

    # ========================================================
    # ADD MISSING COLUMNS
    # ========================================================

    columns_to_add = {

        "user_id": "INTEGER",

        "username": "TEXT",

        "role": "TEXT",

        "status": "TEXT",

        "ip_address": "TEXT",

        "details": "TEXT",

        "created_at": "TEXT"
    }

    for column_name, column_type in columns_to_add.items():

        if column_name not in existing_columns:

            db.execute(
                f"""
                ALTER TABLE activity_logs
                ADD COLUMN {column_name} {column_type}
                """
            )

    # ========================================================
    # COMMIT DATABASE CHANGES
    # ========================================================

    db.commit()


# ============================================================
# DATABASE HELPERS
# ============================================================

def get_current_timestamp():
    """
    Return the current UTC timestamp in ISO format.
    """

    return datetime.now(
        timezone.utc
    ).isoformat()


# ============================================================
# USER QUERIES
# ============================================================

def create_user(
    username,
    full_name,
    password_hash,
    role,
    status,
    face_path
):
    """
    Create a new user or administrator account.
    """

    db = get_db()

    cursor = db.execute(
        """
        INSERT INTO users (
            username,
            full_name,
            password_hash,
            role,
            status,
            face_path,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            username,
            full_name,
            password_hash,
            role,
            status,
            face_path,
            get_current_timestamp()
        )
    )

    db.commit()

    return cursor.lastrowid


def get_user_by_id(user_id):
    """
    Get a user using their ID.
    """

    db = get_db()

    return db.execute(
        """
        SELECT *
        FROM users
        WHERE id = ?
        """,
        (user_id,)
    ).fetchone()


def get_user_by_username(username):
    """
    Get a user using their username.
    """

    db = get_db()

    return db.execute(
        """
        SELECT *
        FROM users
        WHERE username = ?
        """,
        (username,)
    ).fetchone()


def username_exists(username):
    """
    Check whether a username already exists.
    """

    db = get_db()

    result = db.execute(
        """
        SELECT id
        FROM users
        WHERE username = ?
        LIMIT 1
        """,
        (username,)
    ).fetchone()

    return result is not None


# ============================================================
# ADMIN BOOTSTRAP
# ============================================================

def has_verified_admin():
    """
    Check whether at least one verified administrator exists.
    """

    db = get_db()

    result = db.execute(
        """
        SELECT id
        FROM users
        WHERE role = 'ADMIN'
        AND status = 'VERIFIED'
        LIMIT 1
        """
    ).fetchone()

    return result is not None


def count_admins():
    """
    Count all administrator accounts.
    """

    db = get_db()

    result = db.execute(
        """
        SELECT COUNT(*) AS total
        FROM users
        WHERE role = 'ADMIN'
        """
    ).fetchone()

    return result["total"]


# ============================================================
# USER STATUS MANAGEMENT
# ============================================================

def verify_user(user_id, verified_by):
    """
    Change a pending user account to VERIFIED.
    """

    db = get_db()

    cursor = db.execute(
        """
        UPDATE users

        SET
            status = 'VERIFIED',
            verified_at = ?,
            verified_by = ?

        WHERE id = ?
        AND status = 'PENDING'
        """,
        (
            get_current_timestamp(),
            verified_by,
            user_id
        )
    )

    db.commit()

    return cursor.rowcount > 0


def reject_user(user_id, verified_by):
    """
    Change a pending user account to REJECTED.
    """

    db = get_db()

    cursor = db.execute(
        """
        UPDATE users

        SET
            status = 'REJECTED',
            verified_at = ?,
            verified_by = ?

        WHERE id = ?
        AND status = 'PENDING'
        """,
        (
            get_current_timestamp(),
            verified_by,
            user_id
        )
    )

    db.commit()

    return cursor.rowcount > 0


# ============================================================
# USER LISTS
# ============================================================

def get_all_users():
    """
    Return all user accounts.
    """

    db = get_db()

    return db.execute(
        """
        SELECT
            id,
            username,
            full_name,
            role,
            status,
            face_path,
            created_at,
            verified_at,
            verified_by

        FROM users

        ORDER BY created_at DESC
        """
    ).fetchall()


def get_users_by_status(status):
    """
    Return users having a particular status.
    """

    db = get_db()

    return db.execute(
        """
        SELECT
            id,
            username,
            full_name,
            role,
            status,
            face_path,
            created_at,
            verified_at,
            verified_by

        FROM users

        WHERE status = ?

        ORDER BY created_at DESC
        """,
        (status,)
    ).fetchall()


def get_users_by_role(role):
    """
    Return users having a particular role.
    """

    db = get_db()

    return db.execute(
        """
        SELECT
            id,
            username,
            full_name,
            role,
            status,
            face_path,
            created_at,
            verified_at,
            verified_by

        FROM users

        WHERE role = ?

        ORDER BY created_at DESC
        """,
        (role,)
    ).fetchall()


# ============================================================
# DASHBOARD STATISTICS
# ============================================================
def get_dashboard_statistics():
    db = get_db()

    total_users = db.execute(
        "SELECT COUNT(*) FROM users WHERE role = 'USER'"
    ).fetchone()[0]

    pending_users = db.execute(
        "SELECT COUNT(*) FROM users WHERE role = 'USER' AND status = 'PENDING'"
    ).fetchone()[0]

    verified_users = db.execute(
        "SELECT COUNT(*) FROM users WHERE role = 'USER' AND status = 'VERIFIED'"
    ).fetchone()[0]

    rejected_users = db.execute(
        "SELECT COUNT(*) FROM users WHERE role = 'USER' AND status = 'REJECTED'"
    ).fetchone()[0]

    total_admins = db.execute(
        "SELECT COUNT(*) FROM users WHERE role = 'ADMIN'"
    ).fetchone()[0]

    return {
        "total_users": total_users,
        "pending_users": pending_users,
        "verified_users": verified_users,
        "rejected_users": rejected_users,
        "total_admins": total_admins,
        "total": total_users,
        "pending": pending_users,
        "verified": verified_users,
        "rejected": rejected_users,
        "users": total_users,
        "admins": total_admins
    }

# ============================================================
# ACTIVITY LOGGING
# ============================================================

def log_activity(
    username,
    role,
    action,
    status,
    ip_address=None,
    user_id=None
):
    """
    Store an authentication or account activity event.
    """

    db = get_db()

    db.execute(
        """
        INSERT INTO activity_logs (

            user_id,

            username,

            role,

            action,

            status,

            ip_address,

            created_at

        )

        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            username,
            role,
            action,
            status,
            ip_address,
            get_current_timestamp()
        )
    )

    db.commit()


def get_recent_activity(limit=100):
    """
    Return recent activity records.
    """

    db = get_db()

    return db.execute(
        """
        SELECT

            id,

            user_id,

            username,

            role,

            action,

            status,

            ip_address,

            created_at

        FROM activity_logs

        ORDER BY id DESC

        LIMIT ?
        """,
        (limit,)
    ).fetchall()


def get_user_activity(user_id, limit=50):
    """
    Return activity belonging to one user.
    """

    db = get_db()

    return db.execute(
        """
        SELECT

            id,

            username,

            role,

            action,

            status,

            ip_address,

            created_at

        FROM activity_logs

        WHERE user_id = ?

        ORDER BY id DESC

        LIMIT ?
        """,
        (
            user_id,
            limit
        )
    ).fetchall()


# ============================================================
# DATABASE RESET
# ============================================================

def reset_database():
    """
    Development-only helper to remove all application tables.
    """

    db = get_db()

    db.execute(
        "DROP TABLE IF EXISTS activity_logs"
    )

    db.execute(
        "DROP TABLE IF EXISTS users"
    )

    db.commit()

    init_db()