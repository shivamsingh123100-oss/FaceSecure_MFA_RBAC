from functools import wraps

from flask import (
    abort,
    flash,
    redirect,
    request,
    session,
    url_for
)

from werkzeug.security import (
    check_password_hash,
    generate_password_hash
)

from db import get_user_by_id


# ============================================================
# PASSWORD SECURITY
# ============================================================

def hash_password(password):
    """
    Generate a secure password hash.

    The plaintext password is never stored in the database.
    """

    return generate_password_hash(password)


def verify_password(password_hash, password):
    """
    Verify a plaintext password against its stored hash.
    """

    if not password_hash or not password:
        return False

    return check_password_hash(
        password_hash,
        password
    )


# ============================================================
# SESSION MANAGEMENT
# ============================================================

def login_user(user):
    """
    Create the authenticated user's session.
    """

    session.clear()

    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = user["role"]

    session.permanent = True


def logout_user():
    """
    Completely remove the current authentication session.
    """

    session.clear()


def is_logged_in():
    """
    Return True if an authenticated user exists in the session.
    """

    return "user_id" in session


# ============================================================
# CURRENT USER
# ============================================================

def get_current_user():
    """
    Return the database record for the currently
    authenticated user.
    """

    user_id = session.get("user_id")

    if not user_id:
        return None

    return get_user_by_id(user_id)


def get_current_user_id():
    """
    Return the current user's database ID.
    """

    return session.get("user_id")


def get_current_username():
    """
    Return the current username.
    """

    return session.get("username")


def get_current_role():
    """
    Return the current user's role.
    """

    return session.get("role")


# ============================================================
# ROLE CHECKS
# ============================================================

def is_user():
    """
    Return True when the authenticated account
    has USER role.
    """

    return (
        is_logged_in()
        and get_current_role() == "USER"
    )


def is_admin():
    """
    Return True when the authenticated account
    has ADMIN role.
    """

    return (
        is_logged_in()
        and get_current_role() == "ADMIN"
    )


# ============================================================
# AUTHENTICATION DECORATOR
# ============================================================

def login_required(view_function):
    """
    Protect a route from unauthenticated access.
    """

    @wraps(view_function)
    def wrapped_view(*args, **kwargs):

        if not is_logged_in():

            flash(
                "Please log in to continue.",
                "warning"
            )

            return redirect(
                url_for("user_login")
            )

        # Make sure the session still refers
        # to an existing database account.
        user = get_current_user()

        if user is None:

            logout_user()

            flash(
                "Your session is no longer valid. Please log in again.",
                "warning"
            )

            return redirect(
                url_for("user_login")
            )

        return view_function(*args, **kwargs)

    return wrapped_view


# ============================================================
# USER ROLE DECORATOR
# ============================================================

def user_required(view_function):
    """
    Protect a route so that only USER accounts
    can access it.
    """

    @wraps(view_function)
    def wrapped_view(*args, **kwargs):

        if not is_logged_in():

            flash(
                "Please log in to continue.",
                "warning"
            )

            return redirect(
                url_for("user_login")
            )

        if get_current_role() != "USER":

            abort(403)

        user = get_current_user()

        if user is None:

            logout_user()

            return redirect(
                url_for("user_login")
            )

        return view_function(*args, **kwargs)

    return wrapped_view


# ============================================================
# ADMIN ROLE DECORATOR
# ============================================================

def admin_required(view_function):
    """
    Protect a route so that only ADMIN accounts
    can access it.
    """

    @wraps(view_function)
    def wrapped_view(*args, **kwargs):

        if not is_logged_in():

            flash(
                "Please log in to continue.",
                "warning"
            )

            return redirect(
                url_for("admin_login")
            )

        if get_current_role() != "ADMIN":

            abort(403)

        user = get_current_user()

        if user is None:

            logout_user()

            return redirect(
                url_for("admin_login")
            )

        return view_function(*args, **kwargs)

    return wrapped_view


# ============================================================
# ROLE-BASED ACCESS DECORATOR
# ============================================================

def role_required(*allowed_roles):
    """
    Protect a route using one or more allowed roles.

    Example:

        @role_required("ADMIN")

    or:

        @role_required("USER", "ADMIN")
    """

    normalized_roles = {
        role.upper()
        for role in allowed_roles
    }

    def decorator(view_function):

        @wraps(view_function)
        def wrapped_view(*args, **kwargs):

            if not is_logged_in():

                flash(
                    "Please log in to continue.",
                    "warning"
                )

                return redirect(
                    url_for("user_login")
                )

            current_role = get_current_role()

            if current_role not in normalized_roles:

                abort(403)

            user = get_current_user()

            if user is None:

                logout_user()

                return redirect(
                    url_for("user_login")
                )

            return view_function(
                *args,
                **kwargs
            )

        return wrapped_view

    return decorator


# ============================================================
# ACCOUNT STATUS CHECK
# ============================================================

def account_is_verified(user):
    """
    Check whether an account has been verified.
    """

    if user is None:
        return False

    return user["status"] == "VERIFIED"


def account_is_pending(user):
    """
    Check whether an account is awaiting verification.
    """

    if user is None:
        return False

    return user["status"] == "PENDING"


def account_is_rejected(user):
    """
    Check whether an account has been rejected.
    """

    if user is None:
        return False

    return user["status"] == "REJECTED"


# ============================================================
# LOGIN VALIDATION
# ============================================================

def can_login(user):
    """
    Determine whether an account is allowed to proceed
    to MFA authentication.
    """

    if user is None:
        return False

    return user["status"] == "VERIFIED"


# ============================================================
# REQUEST INFORMATION
# ============================================================

def get_client_ip():
    """
    Return the client's apparent IP address.

    This is used for activity logging.
    """

    forwarded_for = request.headers.get(
        "X-Forwarded-For"
    )

    if forwarded_for:

        return forwarded_for.split(",")[0].strip()

    return request.remote_addr or "UNKNOWN"