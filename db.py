import sqlite3
from datetime import datetime, timezone

from flask import current_app, g


class DatabaseHandle:
    """Small SQLite/PostgreSQL adapter used by the request handlers."""

    def __init__(self, connection, is_postgres=False):
        self.connection = connection
        self.is_postgres = is_postgres

    def execute(self, statement, parameters=()):
        if not self.is_postgres:
            return self.connection.execute(statement, parameters)

        sql = statement.strip()
        if sql.upper() == "BEGIN":
            # psycopg starts a transaction automatically on the first query.
            return self.connection.cursor()

        if sql.upper().startswith("INSERT OR IGNORE INTO "):
            sql = sql.replace("INSERT OR IGNORE INTO ", "INSERT INTO ", 1)
            if "ON CONFLICT" not in sql.upper():
                sql = sql.rstrip("; ") + " ON CONFLICT DO NOTHING"

        sql = sql.replace("COLLATE NOCASE", "")
        sql = sql.replace("?", "%s")

        from psycopg2.extras import DictCursor

        cursor = self.connection.cursor(cursor_factory=DictCursor)
        cursor.execute(sql, parameters)
        return cursor

    def commit(self):
        return self.connection.commit()

    def rollback(self):
        return self.connection.rollback()

    def close(self):
        return self.connection.close()


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_db():
    """
    Create or reuse the SQLite connection for the current request.
    """

    if "db" not in g:
        database_url = current_app.config.get("DATABASE_URL")
        if database_url:
            import psycopg2

            connection = psycopg2.connect(database_url, sslmode="require")
            g.db = DatabaseHandle(connection, is_postgres=True)
        else:
            connection = sqlite3.connect(current_app.config["DATABASE_PATH"])
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            g.db = DatabaseHandle(connection)

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
    id_column = "SERIAL PRIMARY KEY" if db.is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"

    # ========================================================
    # USERS TABLE
    # ========================================================

    db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS users (

            id {id_column},

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

            university_role TEXT NOT NULL DEFAULT 'STUDENT'
                CHECK (university_role IN ('STUDENT', 'TEACHER')),

            registration_number TEXT,

            face_path TEXT,

            face_encoding TEXT,

            created_at TEXT NOT NULL,

            verified_at TEXT,

            verified_by INTEGER,

            FOREIGN KEY (verified_by)
                REFERENCES users(id)
                ON DELETE SET NULL
        )
        """
    )

    if db.is_postgres:
        user_columns = {
            row["name"] for row in db.execute(
                "SELECT column_name AS name FROM information_schema.columns WHERE table_name = 'users'"
            ).fetchall()
        }
    else:
        user_columns = {
            row["name"] for row in db.execute("PRAGMA table_info(users)").fetchall()
        }
    if "university_role" not in user_columns:
        db.execute(
            "ALTER TABLE users ADD COLUMN university_role TEXT NOT NULL DEFAULT 'STUDENT' "
            "CHECK (university_role IN ('STUDENT', 'TEACHER'))"
        )
    if "face_encoding" not in user_columns:
        db.execute("ALTER TABLE users ADD COLUMN face_encoding TEXT")
    if "registration_number" not in user_columns:
        db.execute("ALTER TABLE users ADD COLUMN registration_number TEXT")
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS users_registration_number_unique "
        "ON users(LOWER(registration_number)) WHERE registration_number IS NOT NULL"
    )

    db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS courses (
            id {id_column},
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            term TEXT NOT NULL,
            teacher_id INTEGER NOT NULL,
            max_marks REAL NOT NULL DEFAULT 100,
            created_at TEXT NOT NULL,
            FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE RESTRICT
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS enrollments (
            course_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (course_id, student_id),
            FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS results (
            id {id_column},
            course_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            marks REAL NOT NULL,
            grade TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'PUBLISHED')),
            updated_at TEXT NOT NULL,
            UNIQUE (course_id, student_id),
            FOREIGN KEY (course_id, student_id)
                REFERENCES enrollments(course_id, student_id) ON DELETE CASCADE
        )
        """
    )

    db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS attendance_sessions (
            id {id_column},
            course_id INTEGER NOT NULL,
            session_date TEXT NOT NULL,
            topic TEXT NOT NULL DEFAULT '',
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (course_id, session_date),
            FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT
        )
        """
    )
    db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS attendance_records (
            id {id_column},
            session_id INTEGER NOT NULL,
            course_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('PRESENT', 'ABSENT', 'LATE', 'EXCUSED')),
            note TEXT NOT NULL DEFAULT '',
            marked_at TEXT NOT NULL,
            UNIQUE (session_id, student_id),
            FOREIGN KEY (session_id) REFERENCES attendance_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY (course_id, student_id)
                REFERENCES enrollments(course_id, student_id) ON DELETE CASCADE
        )
        """
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS attendance_records_student_idx ON attendance_records(student_id, course_id)"
    )

    # ========================================================
    # ACTIVITY LOGS TABLE
    # ========================================================

    db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS activity_logs (

            id {id_column},

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

    if db.is_postgres:
        existing_columns = {
            row["name"] for row in db.execute(
                "SELECT column_name AS name FROM information_schema.columns WHERE table_name = 'activity_logs'"
            ).fetchall()
        }
    else:
        existing_columns = {
            row["name"] for row in db.execute(
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
    face_path,
    university_role="STUDENT",
    face_encoding=None,
    registration_number=None,
):
    """
    Create a new user or administrator account.
    """

    db = get_db()

    cursor = db.execute(
        f"""
        INSERT INTO users (
            username,
            full_name,
            password_hash,
            role,
            status,
            university_role,
            registration_number,
            face_path,
            face_encoding,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        {"RETURNING id" if db.is_postgres else ""}
        """,
        (
            username,
            full_name,
            password_hash,
            role,
            status,
            university_role,
            registration_number,
            face_path,
            face_encoding,
            get_current_timestamp()
        )
    )

    if db.is_postgres:
        user_id = cursor.fetchone()["id"]
    else:
        user_id = cursor.lastrowid
    db.commit()
    return user_id


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
        WHERE LOWER(username) = LOWER(?)
        """,
        (username,)
    ).fetchone()


def get_user_by_registration_number(registration_number):
    """Find a student by their case-insensitive university ID."""
    return get_db().execute(
        """
        SELECT * FROM users
        WHERE LOWER(registration_number) = LOWER(?)
          AND role = 'USER' AND university_role = 'STUDENT'
        """,
        (registration_number,),
    ).fetchone()


def registration_number_exists(registration_number, exclude_user_id=None):
    """Check whether a student ID is already assigned."""
    query = "SELECT id FROM users WHERE LOWER(registration_number) = LOWER(?)"
    parameters = [registration_number]
    if exclude_user_id is not None:
        query += " AND id <> ?"
        parameters.append(exclude_user_id)
    return get_db().execute(query + " LIMIT 1", tuple(parameters)).fetchone() is not None


def update_student_registration_number(user_id, registration_number):
    """Set a student account's university ID."""
    cursor = get_db().execute(
        "UPDATE users SET registration_number = ? "
        "WHERE id = ? AND role = 'USER' AND university_role = 'STUDENT'",
        (registration_number, user_id),
    )
    get_db().commit()
    return cursor.rowcount > 0


def username_exists(username):
    """
    Check whether a username already exists.
    """

    db = get_db()

    result = db.execute(
        """
        SELECT id
        FROM users
        WHERE LOWER(username) = LOWER(?)
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
            university_role,
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
            university_role,
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
            university_role,
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

