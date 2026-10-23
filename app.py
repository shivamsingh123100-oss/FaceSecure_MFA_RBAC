import os


from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for
)

from config import Config

from db import (
    close_db,
    create_user,
    get_all_users,
    get_dashboard_statistics,
    get_recent_activity,
    get_user_by_id,
    get_user_by_username,
    get_users_by_role,
    get_users_by_status,
    has_verified_admin,
    init_db,
    log_activity,
    reject_user,
    username_exists,
    verify_user
)

from face_service import (
    FaceServiceError,
    MultipleFacesDetectedError,
    NoFaceDetectedError,
    InvalidImageError,
    process_registration_face,
    verify_face
)

from security import (
    account_is_pending,
    account_is_rejected,
    account_is_verified,
    admin_required,
    get_current_role,
    get_current_user,
    get_current_user_id,
    get_current_username,
    get_client_ip,
    hash_password,
    is_logged_in,
    login_required,
    login_user,
    logout_user,
    user_required,
    verify_password
)


# ============================================================
# APPLICATION CONFIGURATION
# ============================================================

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static"
)

app.config.from_object(Config)


# ============================================================
# DATABASE CONNECTION CLEANUP
# ============================================================

app.teardown_appcontext(close_db)


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

with app.app_context():
    init_db()


# ============================================================
# TEMPLATE CONTEXT
# ============================================================

@app.context_processor
def inject_current_user():
    """
    Make authentication information available
    to every HTML template.
    """

    return {
        "current_user": get_current_user(),
        "current_role": get_current_role(),
        "logged_in": is_logged_in()
    }


# ============================================================
# HOME / PUBLIC ROUTES
# ============================================================

@app.route("/")
def index():
    """
    Main public landing page.
    """

    return render_template(
        "public/index.html"
    )


@app.route("/access")
def access():
    """
    User/Admin access selection page.
    """

    return render_template(
        "public/access.html"
    )


# ============================================================
# USER REGISTRATION
# ============================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def user_register():
    """
    User registration page.

    User provides:
        - full name
        - username
        - password
        - password confirmation
        - face image
    """

    if request.method == "GET":

        return render_template(
            "user/register.html"
        )

    full_name = request.form.get(
        "full_name",
        ""
    ).strip()

    username = request.form.get(
        "username",
        ""
    ).strip()

    password = request.form.get(
        "password",
        ""
    )

    confirm_password = request.form.get(
        "confirm_password",
        ""
    )

    face_image = request.form.get(
        "face_image",
        ""
    )

    # --------------------------------------------------------
    # BASIC VALIDATION
    # --------------------------------------------------------

    if not full_name:

        flash(
            "Full name is required.",
            "error"
        )

        return render_template(
            "user/register.html"
        )

    if not username:

        flash(
            "Username is required.",
            "error"
        )

        return render_template(
            "user/register.html"
        )

    if len(username) < 3:

        flash(
            "Username must contain at least 3 characters.",
            "error"
        )

        return render_template(
            "user/register.html"
        )

    if len(password) < 8:

        flash(
            "Password must contain at least 8 characters.",
            "error"
        )

        return render_template(
            "user/register.html"
        )

    if password != confirm_password:

        flash(
            "Passwords do not match.",
            "error"
        )

        return render_template(
            "user/register.html"
        )

    if username_exists(username):

        flash(
            "This username is already registered.",
            "error"
        )

        return render_template(
            "user/register.html"
        )

    if not face_image:

        flash(
            "Please capture your face before registering.",
            "error"
        )

        return render_template(
            "user/register.html"
        )

    # --------------------------------------------------------
    # FACE PROCESSING
    # --------------------------------------------------------

    try:

        face_result = process_registration_face(
            face_image,
            username
        )

    except NoFaceDetectedError:

        flash(
            "No face detected. Please capture your face again.",
            "error"
        )

        return render_template(
            "user/register.html"
        )

    except MultipleFacesDetectedError:

        flash(
            "Multiple faces detected. Only one face is allowed.",
            "error"
        )

        return render_template(
            "user/register.html"
        )

    except InvalidImageError:

        flash(
            "The captured image could not be processed.",
            "error"
        )

        return render_template(
            "user/register.html"
        )

    except FaceServiceError:

        flash(
            "Face processing failed. Please try again.",
            "error"
        )

        return render_template(
            "user/register.html"
        )

    # --------------------------------------------------------
    # CREATE USER
    # --------------------------------------------------------

    password_hash = hash_password(
        password
    )

    try:

        user_id = create_user(
            username=username,
            full_name=full_name,
            password_hash=password_hash,
            role="USER",
            status="PENDING",
            face_path=face_result["face_path"]
        )

        log_activity(
            username=username,
            role="USER",
            action="USER_REGISTRATION",
            status="SUCCESS",
            ip_address=get_client_ip(),
            user_id=user_id
        )

    except Exception:

        flash(
            "Registration could not be completed.",
            "error"
        )

        return render_template(
            "user/register.html"
        )

    flash(
        "Registration successful. Your account is waiting for admin verification.",
        "success"
    )

    return redirect(
        url_for("verification_status")
    )


# ============================================================
# USER LOGIN
# ============================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def user_login():
    """
    User MFA login.

    Factor 1:
        Username + Password

    Factor 2:
        Face
    """

    if request.method == "GET":

        return render_template(
            "user/login.html"
        )

    username = request.form.get(
        "username",
        ""
    ).strip()

    password = request.form.get(
        "password",
        ""
    ).strip()

    face_image = request.form.get(
        "face_image",
        ""
    )

    # --------------------------------------------------------
    # FIND USER
    # --------------------------------------------------------

    user = get_user_by_username(
        username
    )

    if user is None:

        log_activity(
            username=username or "UNKNOWN",
            role="USER",
            action="USER_LOGIN",
            status="FAILED_USERNAME",
            ip_address=get_client_ip()
        )

        flash(
            "Invalid username or password.",
            "error"
        )

        return render_template(
            "user/login.html"
        )

    # --------------------------------------------------------
    # PASSWORD FACTOR
    # --------------------------------------------------------

    if not verify_password(
        user["password_hash"],
        password
    ):

        log_activity(
            username=user["username"],
            role=user["role"],
            action="USER_LOGIN",
            status="FAILED_PASSWORD",
            ip_address=get_client_ip(),
            user_id=user["id"]
        )

        flash(
            "Invalid username or password.",
            "error"
        )

        return render_template(
            "user/login.html"
        )

    # --------------------------------------------------------
    # ACCOUNT STATUS
    # --------------------------------------------------------

    if account_is_pending(user):

        log_activity(
            username=user["username"],
            role=user["role"],
            action="USER_LOGIN",
            status="FAILED_PENDING",
            ip_address=get_client_ip(),
            user_id=user["id"]
        )

        flash(
            "Your account is waiting for admin verification.",
            "warning"
        )

        return redirect(
            url_for("verification_status")
        )

    if account_is_rejected(user):

        log_activity(
            username=user["username"],
            role=user["role"],
            action="USER_LOGIN",
            status="FAILED_REJECTED",
            ip_address=get_client_ip(),
            user_id=user["id"]
        )

        flash(
            "Your account has been rejected.",
            "error"
        )

        return render_template(
            "user/login.html"
        )

    if not account_is_verified(user):

        flash(
            "Your account cannot currently be authenticated.",
            "error"
        )

        return render_template(
            "user/login.html"
        )

    # --------------------------------------------------------
    # FACE FACTOR
    # --------------------------------------------------------

    if not face_image:

        flash(
            "Please capture your face.",
            "error"
        )

        return render_template(
            "user/login.html"
        )

    try:

        face_result = verify_face(
            image_data=face_image,
            registered_face_path=user["face_path"]
        )

    except NoFaceDetectedError:

        log_activity(
            username=user["username"],
            role=user["role"],
            action="USER_LOGIN",
            status="FAILED_NO_FACE",
            ip_address=get_client_ip(),
            user_id=user["id"]
        )

        flash(
            "No face detected. Please try again.",
            "error"
        )

        return render_template(
            "user/login.html"
        )

    except MultipleFacesDetectedError:

        log_activity(
            username=user["username"],
            role=user["role"],
            action="USER_LOGIN",
            status="FAILED_MULTIPLE_FACES",
            ip_address=get_client_ip(),
            user_id=user["id"]
        )

        flash(
            "Multiple faces detected. Only one face is allowed.",
            "error"
        )

        return render_template(
            "user/login.html"
        )

    except FaceServiceError:

        log_activity(
            username=user["username"],
            role=user["role"],
            action="USER_LOGIN",
            status="FAILED_FACE_PROCESSING",
            ip_address=get_client_ip(),
            user_id=user["id"]
        )

        flash(
            "Face verification could not be completed.",
            "error"
        )

        return render_template(
            "user/login.html"
        )

    # --------------------------------------------------------
    # FACE MATCH RESULT
    # --------------------------------------------------------

    if not face_result["matched"]:

        log_activity(
            username=user["username"],
            role=user["role"],
            action="USER_LOGIN",
            status="FAILED_FACE",
            ip_address=get_client_ip(),
            user_id=user["id"]
        )

        flash(
            "Face verification failed.",
            "error"
        )

        return render_template(
            "user/login.html"
        )

    # --------------------------------------------------------
    # BOTH FACTORS SUCCESSFUL
    # --------------------------------------------------------

    login_user(user)

    log_activity(
        username=user["username"],
        role=user["role"],
        action="USER_LOGIN",
        status="SUCCESS",
        ip_address=get_client_ip(),
        user_id=user["id"]
    )

    flash(
        "Authentication successful.",
        "success"
    )

    return redirect(
        url_for("user_dashboard")
    )


# ============================================================
# USER FACE CAPTURE PAGE
# ============================================================

@app.route("/face-capture")
@login_required
def face_capture():

    if get_current_role() != "USER":

        return redirect(
            url_for("admin_dashboard")
        )

    return render_template(
        "user/face_capture.html"
    )


# ============================================================
# USER VERIFICATION STATUS
# ============================================================

@app.route("/verification-status")
def verification_status():

    if not is_logged_in():

        return render_template(
            "user/verification_status.html",
            user=None
        )

    user = get_current_user()

    return render_template(
        "user/verification_status.html",
        user=user
    )


# ============================================================
# USER DASHBOARD
# ============================================================

@app.route("/user/dashboard")
@user_required
def user_dashboard():

    user = get_current_user()

    return render_template(
        "user/dashboard.html",
        user=user
    )


# ============================================================
# USER PROFILE
# ============================================================

@app.route("/user/profile")
@user_required
def user_profile():

    user = get_current_user()

    return render_template(
        "user/profile.html",
        user=user
    )


# ============================================================
# ADMIN REGISTRATION
# ============================================================

@app.route(
    "/admin/register",
    methods=["GET", "POST"]
)
def admin_register():
    """
    Admin registration.

    The first admin is automatically verified so the
    system can be initialized.

    Subsequent admin accounts require verification
    by an existing verified admin.
    """

    if request.method == "GET":

        return render_template(
            "admin/register.html"
        )

    full_name = request.form.get(
        "full_name",
        ""
    ).strip()

    username = request.form.get(
        "username",
        ""
    ).strip()

    password = request.form.get(
        "password",
        ""
    )

    confirm_password = request.form.get(
        "confirm_password",
        ""
    )

    face_image = request.form.get(
        "face_image",
        ""
    )

    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    if not full_name:

        flash(
            "Full name is required.",
            "error"
        )

        return render_template(
            "admin/register.html"
        )

    if not username:

        flash(
            "Username is required.",
            "error"
        )

        return render_template(
            "admin/register.html"
        )

    if len(username) < 3:

        flash(
            "Username must contain at least 3 characters.",
            "error"
        )

        return render_template(
            "admin/register.html"
        )

    if len(password) < 8:

        flash(
            "Password must contain at least 8 characters.",
            "error"
        )

        return render_template(
            "admin/register.html"
        )

    if password != confirm_password:

        flash(
            "Passwords do not match.",
            "error"
        )

        return render_template(
            "admin/register.html"
        )

    if username_exists(username):

        flash(
            "This username is already registered.",
            "error"
        )

        return render_template(
            "admin/register.html"
        )

    if not face_image:

        flash(
            "Please capture your face before registering.",
            "error"
        )

        return render_template(
            "admin/register.html"
        )

    # --------------------------------------------------------
    # FACE PROCESSING
    # --------------------------------------------------------

    try:

        face_result = process_registration_face(
            face_image,
            username
        )

    except NoFaceDetectedError:

        flash(
            "No face detected. Please capture your face again.",
            "error"
        )

        return render_template(
            "admin/register.html"
        )

    except MultipleFacesDetectedError:

        flash(
            "Multiple faces detected. Only one face is allowed.",
            "error"
        )

        return render_template(
            "admin/register.html"
        )

    except FaceServiceError:

        flash(
            "Face processing failed. Please try again.",
            "error"
        )

        return render_template(
            "admin/register.html"
        )

    # --------------------------------------------------------
    # FIRST ADMIN BOOTSTRAP
    # --------------------------------------------------------

    first_admin = not has_verified_admin()

    status = (
        "VERIFIED"
        if first_admin
        else "PENDING"
    )

    password_hash = hash_password(
        password
    )

    try:

        admin_id = create_user(
            username=username,
            full_name=full_name,
            password_hash=password_hash,
            role="ADMIN",
            status=status,
            face_path=face_result["face_path"]
        )

        log_activity(
            username=username,
            role="ADMIN",
            action="ADMIN_REGISTRATION",
            status="SUCCESS",
            ip_address=get_client_ip(),
            user_id=admin_id
        )

    except Exception:

        flash(
            "Admin registration could not be completed.",
            "error"
        )

        return render_template(
            "admin/register.html"
        )

    if first_admin:

        flash(
            "First administrator created successfully. You can now log in.",
            "success"
        )

        return redirect(
            url_for("admin_login")
        )

    flash(
        "Admin registration successful. The account is waiting for verification.",
        "success"
    )

    return redirect(
        url_for("verification_status")
    )


# ============================================================
# ADMIN LOGIN
# ============================================================

@app.route(
    "/admin/login",
    methods=["GET", "POST"]
)
def admin_login():
    """
    Admin MFA login.

    Factor 1:
        Username + Password

    Factor 2:
        Face
    """

    if request.method == "GET":

        return render_template(
            "admin/login.html"
        )

    username = request.form.get(
        "username",
        ""
    ).strip()

    password = request.form.get(
        "password",
        ""
    )

    face_image = request.form.get(
        "face_image",
        ""
    ).strip()

    admin = get_user_by_username(
        username
    )

    if admin is None:

        log_activity(
            username=username or "UNKNOWN",
            role="ADMIN",
            action="ADMIN_LOGIN",
            status="FAILED_USERNAME",
            ip_address=get_client_ip()
        )

        flash(
            "Invalid administrator credentials.",
            "error"
        )

        return render_template(
            "admin/login.html"
        )

    if admin["role"] != "ADMIN":

        log_activity(
            username=admin["username"],
            role=admin["role"],
            action="ADMIN_LOGIN",
            status="FAILED_ROLE",
            ip_address=get_client_ip(),
            user_id=admin["id"]
        )

        flash(
            "This account is not an administrator account.",
            "error"
        )

        return render_template(
            "admin/login.html"
        )
    # --------------------------------------------------------
    # PASSWORD FACTOR
    # --------------------------------------------------------

    if not verify_password(
        admin["password_hash"],
        password
    ):

        log_activity(
            username=admin["username"],
            role="ADMIN",
            action="ADMIN_LOGIN",
            status="FAILED_PASSWORD",
            ip_address=get_client_ip(),
            user_id=admin["id"]
        )

        flash(
            "Invalid administrator credentials.",
            "error"
        )

        return render_template(
            "admin/login.html"
        )

    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    if not account_is_verified(admin):

        log_activity(
            username=admin["username"],
            role="ADMIN",
            action="ADMIN_LOGIN",
            status=f"FAILED_{admin['status']}",
            ip_address=get_client_ip(),
            user_id=admin["id"]
        )

        flash(
            f"Administrator account status: {admin['status']}.",
            "warning"
        )

        return render_template(
            "admin/login.html"
        )

    # --------------------------------------------------------
    # FACE FACTOR
    # --------------------------------------------------------

    if not face_image:

        flash(
            "Please capture your face.",
            "error"
        )

        return render_template(
            "admin/login.html"
        )

    # --------------------------------------------------------
    # FACE VERIFICATION
    # --------------------------------------------------------

    try:

        print("\n" + "=" * 70)
        print("ADMIN FACE LOGIN DEBUG")
        print("=" * 70)
        print("Username:", username)
        print("Face image received:", bool(face_image))

        if face_image:
            print("Face image length:", len(face_image))
        else:
            print("Face image length: 0")

        print("Registered face path:", admin["face_path"])
        print("=" * 70)

        face_result = verify_face(
            image_data=face_image,
            registered_face_path=admin["face_path"]
        )

        print("\n" + "=" * 70)
        print("FACE VERIFICATION RESULT")
        print("=" * 70)
        print("Result:", face_result)
        print("=" * 70)

    except NoFaceDetectedError:

        log_activity(
            username=admin["username"],
            role="ADMIN",
            action="ADMIN_LOGIN",
            status="FAILED_NO_FACE",
            ip_address=get_client_ip(),
            user_id=admin["id"]
        )

        flash(
            "No face detected. Please try again.",
            "error"
        )

        return render_template(
            "admin/login.html"
        )

    except MultipleFacesDetectedError:

        log_activity(
            username=admin["username"],
            role="ADMIN",
            action="ADMIN_LOGIN",
            status="FAILED_MULTIPLE_FACES",
            ip_address=get_client_ip(),
            user_id=admin["id"]
        )

        flash(
            "Multiple faces detected. Only one face is allowed.",
            "error"
        )

        return render_template(
            "admin/login.html"
        )

    except InvalidImageError:

        log_activity(
            username=admin["username"],
            role="ADMIN",
            action="ADMIN_LOGIN",
            status="FAILED_INVALID_IMAGE",
            ip_address=get_client_ip(),
            user_id=admin["id"]
        )

        flash(
            "The captured face image could not be processed. Please capture it again.",
            "error"
        )

        return render_template(
            "admin/login.html"
        )

    except FaceServiceError as e:

        print("\n" + "=" * 70)
        print("FACE SERVICE ERROR")
        print("=" * 70)
        print("ERROR TYPE:", type(e).__name__)
        print("ERROR:", str(e))
        print("=" * 70)

        log_activity(
            username=admin["username"],
            role="ADMIN",
            action="ADMIN_LOGIN",
            status="FAILED_FACE_PROCESSING",
            ip_address=get_client_ip(),
            user_id=admin["id"]
        )

        flash(
            "Face verification could not be completed.",
            "error"
        )

        return render_template(
            "admin/login.html"
        )

    # --------------------------------------------------------
    # FACE MATCH
    # --------------------------------------------------------

    if not face_result.get("matched", False):

        distance = face_result.get("distance")

        print("FACE MATCH FAILED")
        print("Face distance:", distance)

        log_activity(
            username=admin["username"],
            role="ADMIN",
            action="ADMIN_LOGIN",
            status="FAILED_FACE",
            ip_address=get_client_ip(),
            user_id=admin["id"]
        )

        flash(
            "Face verification failed. Please capture your face again.",
            "error"
        )

        return render_template(
            "admin/login.html"
        )

    # --------------------------------------------------------
    # ADMIN AUTHENTICATED
    # --------------------------------------------------------

    login_user(admin)

    log_activity(
        username=admin["username"],
        role="ADMIN",
        action="ADMIN_LOGIN",
        status="SUCCESS",
        ip_address=get_client_ip(),
        user_id=admin["id"]
    )

    flash(
        "Administrator authentication successful.",
        "success"
    )

    return redirect(
        url_for("admin_dashboard")
    )

@app.route("/admin/dashboard")
@login_required
@admin_required
def admin_dashboard():

    # --------------------------------------------------------
    # GET LOGGED-IN ADMIN
    # --------------------------------------------------------

    admin = get_user_by_id(
        session.get("user_id")
    )

    if admin is None:
        flash(
            "Administrator session is invalid. Please login again.",
            "error"
        )

        return redirect(
            url_for("admin_login")
        )

    # --------------------------------------------------------
    # DASHBOARD STATISTICS
    # --------------------------------------------------------

    try:

        statistics = get_dashboard_statistics()

    except Exception as e:

        print(
            "DASHBOARD STATISTICS ERROR:",
            repr(e)
        )

        statistics = {
    "total_users": 0,
    "pending_users": 0,
    "verified_users": 0,
    "rejected_users": 0,
    "total_admins": 0,
    "total": 0,
    "pending": 0,
    "verified": 0,
    "rejected": 0,
    "users": 0,
    "admins": 0
}

    # --------------------------------------------------------
    # RECENT ACTIVITY
    # --------------------------------------------------------

    try:

        recent_activity = get_recent_activity(
            limit=10
        )

    except Exception as e:

        print(
            "RECENT ACTIVITY ERROR:",
            repr(e)
        )

        recent_activity = []

    # --------------------------------------------------------
    # RENDER DASHBOARD
    # --------------------------------------------------------

    return render_template(
        "admin/dashboard.html",
        user=admin,
        statistics=statistics,
        recent_activity=recent_activity
    )

# ============================================================
# ALL USERS
# ============================================================

@app.route("/admin/users")
@admin_required
def admin_users():

    users = get_all_users()

    return render_template(
        "admin/users.html",
        users=users
    )


# ============================================================
# PENDING USERS
# ============================================================

@app.route("/admin/users/pending")
@admin_required
def admin_pending_users():

    users = get_users_by_status(
        "PENDING"
    )

    return render_template(
        "admin/pending_users.html",
        users=users
    )


# ============================================================
# VERIFIED USERS
# ============================================================

@app.route("/admin/users/verified")
@admin_required
def admin_verified_users():

    users = get_users_by_status(
        "VERIFIED"
    )

    return render_template(
        "admin/verified_users.html",
        users=users
    )


# ============================================================
# REJECTED USERS
# ============================================================

@app.route("/admin/users/rejected")
@admin_required
def admin_rejected_users():

    users = get_users_by_status(
        "REJECTED"
    )

    return render_template(
        "admin/rejected_users.html",
        users=users
    )


# ============================================================
# VERIFY USER
# ============================================================

@app.post(
    "/admin/users/<int:user_id>/verify"
)
@admin_required
def admin_verify_user(user_id):

    target_user = get_user_by_id(
        user_id
    )

    if target_user is None:

        flash(
            "User account not found.",
            "error"
        )

        return redirect(
            url_for("admin_users")
        )

    if target_user["status"] != "PENDING":

        flash(
            "Only pending accounts can be verified.",
            "warning"
        )

        return redirect(
            url_for("admin_users")
        )

    success = verify_user(
        user_id=user_id,
        verified_by=get_current_user_id()
    )

    if success:

        log_activity(
            username=target_user["username"],
            role=target_user["role"],
            action="ACCOUNT_VERIFICATION",
            status="SUCCESS",
            ip_address=get_client_ip(),
            user_id=user_id
        )

        flash(
            f"{target_user['username']} has been verified.",
            "success"
        )

    else:

        flash(
            "Account verification could not be completed.",
            "error"
        )

    return redirect(
        url_for("admin_users")
    )


# ============================================================
# REJECT USER
# ============================================================

@app.post(
    "/admin/users/<int:user_id>/reject"
)
@admin_required
def admin_reject_user(user_id):

    target_user = get_user_by_id(
        user_id
    )

    if target_user is None:

        flash(
            "User account not found.",
            "error"
        )

        return redirect(
            url_for("admin_users")
        )

    if target_user["status"] != "PENDING":

        flash(
            "Only pending accounts can be rejected.",
            "warning"
        )

        return redirect(
            url_for("admin_users")
        )

    # --------------------------------------------------------
    # Prevent rejecting the only verified admin.
    # --------------------------------------------------------

    if (
        target_user["role"] == "ADMIN"
        and target_user["id"] == get_current_user_id()
    ):

        flash(
            "You cannot reject your own administrator account.",
            "error"
        )

        return redirect(
            url_for("admin_users")
        )

    success = reject_user(
        user_id=user_id,
        verified_by=get_current_user_id()
    )

    if success:

        log_activity(
            username=target_user["username"],
            role=target_user["role"],
            action="ACCOUNT_REJECTION",
            status="SUCCESS",
            ip_address=get_client_ip(),
            user_id=user_id
        )

        flash(
            f"{target_user['username']} has been rejected.",
            "success"
        )

    else:

        flash(
            "Account rejection could not be completed.",
            "error"
        )

    return redirect(
        url_for("admin_users")
    )


# ============================================================
# ADMIN ACTIVITY
# ============================================================

@app.route("/admin/activity")
@admin_required
def admin_activity():

    activities = get_recent_activity(
        limit=100
    )

    return render_template(
        "admin/activity.html",
        activities=activities
    )


# ============================================================
# ADMIN PROFILE
# ============================================================

@app.route("/admin/profile")
@admin_required
def admin_profile():

    admin = get_current_user()

    return render_template(
        "admin/profile.html",
        admin=admin
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
@login_required
def logout():

    user_id = get_current_user_id()
    username = get_current_username()
    role = get_current_role()

    log_activity(
        username=username or "UNKNOWN",
        role=role or "UNKNOWN",
        action="LOGOUT",
        status="SUCCESS",
        ip_address=get_client_ip(),
        user_id=user_id
    )

    logout_user()

    flash(
        "You have been logged out successfully.",
        "success"
    )

    return redirect(
        url_for("index")
    )


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(401)
def unauthorized(error):

    return render_template(
        "errors/401.html"
    ), 401


@app.errorhandler(403)
def forbidden(error):

    return render_template(
        "errors/403.html"
    ), 403


@app.errorhandler(404)
def not_found(error):

    return render_template(
        "errors/404.html"
    ), 404


# ============================================================
# APPLICATION ENTRY POINT
# ============================================================

if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )