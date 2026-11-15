import secrets
from datetime import datetime, timezone
from functools import wraps
from math import isfinite

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from db import get_db, log_activity
from security import admin_required, get_current_user, get_current_user_id, login_required, user_required


results_bp = Blueprint("results", __name__)


def csrf_token():
    token = session.get("results_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["results_csrf"] = token
    return token


@results_bp.context_processor
def inject_results_csrf():
    return {"results_csrf_token": csrf_token}


def require_csrf(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if request.method == "POST":
            supplied = request.form.get("csrf_token", "")
            if not secrets.compare_digest(supplied, csrf_token()):
                abort(400)
        return view(*args, **kwargs)
    return wrapped


def grade_for(marks, maximum):
    percent = marks / maximum * 100
    if percent >= 90:
        return "A"
    if percent >= 80:
        return "B"
    if percent >= 70:
        return "C"
    if percent >= 60:
        return "D"
    return "F"


@results_bp.route("/results")
@login_required
def home():
    user = get_current_user()
    if user["role"] == "ADMIN":
        return redirect(url_for("results.admin_dashboard"))
    if user["university_role"] == "TEACHER":
        return redirect(url_for("results.teacher_dashboard"))
    return redirect(url_for("results.student_dashboard"))


@results_bp.route("/results/student")
@user_required
def student_dashboard():
    user = get_current_user()
    if user["university_role"] != "STUDENT":
        abort(403)
    results = get_db().execute(
        """
        SELECT c.code, c.name, c.term, r.marks, c.max_marks, r.grade, r.updated_at
        FROM results r JOIN courses c ON c.id = r.course_id
        WHERE r.student_id = ? AND r.status = 'PUBLISHED'
        ORDER BY c.term DESC, c.code
        """,
        (user["id"],),
    ).fetchall()
    return render_template("results/student.html", user=user, results=results)


@results_bp.route("/results/teacher")
@user_required
def teacher_dashboard():
    user = get_current_user()
    if user["university_role"] != "TEACHER":
        abort(403)
    courses = get_db().execute(
        """
        SELECT c.*, COUNT(e.student_id) AS student_count
        FROM courses c LEFT JOIN enrollments e ON e.course_id = c.id
        WHERE c.teacher_id = ? GROUP BY c.id ORDER BY c.term DESC, c.code
        """,
        (user["id"],),
    ).fetchall()
    return render_template("results/teacher.html", user=user, courses=courses)


@results_bp.route("/results/teacher/course/<int:course_id>", methods=["GET", "POST"])
@user_required
@require_csrf
def teacher_course(course_id):
    user = get_current_user()
    if user["university_role"] != "TEACHER":
        abort(403)
    db = get_db()
    course = db.execute(
        "SELECT * FROM courses WHERE id = ? AND teacher_id = ?",
        (course_id, user["id"]),
    ).fetchone()
    if course is None:
        abort(404)

    if request.method == "POST":
        roster = db.execute(
            """
            SELECT u.id, u.username, u.full_name, r.marks, r.grade, r.status
            FROM enrollments e JOIN users u ON u.id = e.student_id
            LEFT JOIN results r ON r.course_id = e.course_id AND r.student_id = e.student_id
            WHERE e.course_id = ? ORDER BY u.full_name
            """,
            (course_id,),
        ).fetchall()
        publish = request.form.get("action") == "publish"
        form_marks = {}
        updates = []
        for student in roster:
            raw = request.form.get(f"marks_{student['id']}", "").strip()
            form_marks[str(student["id"])] = raw
            if not raw:
                if publish:
                    flash(f"Enter a mark for every student before publishing. {student['full_name']} is missing a mark.", "error")
                    return render_template("results/course.html", user=user, course=course, roster=roster, form_marks=form_marks)
                continue
            try:
                marks = float(raw)
            except ValueError:
                flash(f"Enter a valid mark for {student['full_name']}.", "error")
                return render_template("results/course.html", user=user, course=course, roster=roster, form_marks=form_marks)
            if not isfinite(marks) or not 0 <= marks <= course["max_marks"]:
                flash(f"Marks for {student['full_name']} must be between 0 and {course['max_marks']:g}.", "error")
                return render_template("results/course.html", user=user, course=course, roster=roster, form_marks=form_marks)
            updates.append((marks, grade_for(marks, course["max_marks"]), "PUBLISHED" if publish else "DRAFT", datetime.now(timezone.utc).isoformat(), course_id, student["id"]))

        if not updates:
            flash("Enter at least one mark before saving.", "error")
            return render_template("results/course.html", user=user, course=course, roster=roster, form_marks=form_marks)

        try:
            db.execute("BEGIN")
            for marks, grade, status, updated_at, course_id, student_id in updates:
                db.execute(
                    """
                    INSERT INTO results (marks, grade, status, updated_at, course_id, student_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(course_id, student_id) DO UPDATE SET
                        marks = excluded.marks, grade = excluded.grade,
                        status = excluded.status, updated_at = excluded.updated_at
                    """,
                    (marks, grade, status, updated_at, course_id, student_id),
                )
            db.commit()
        except Exception:
            db.rollback()
            flash("The gradebook could not be saved. Please try again.", "error")
            return render_template("results/course.html", user=user, course=course, roster=roster, form_marks=form_marks)
        log_activity(
            username=user["username"], role=user["university_role"], action="RESULTS_PUBLISHED" if publish else "RESULTS_SAVED",
            status="SUCCESS", user_id=user["id"],
        )
        flash("Results published to students." if publish else "Draft results saved.", "success")
        return redirect(url_for("results.teacher_course", course_id=course_id))

    roster = db.execute(
        """
        SELECT u.id, u.username, u.full_name, r.marks, r.grade, r.status
        FROM enrollments e JOIN users u ON u.id = e.student_id
        LEFT JOIN results r ON r.course_id = e.course_id AND r.student_id = e.student_id
        WHERE e.course_id = ? ORDER BY u.full_name
        """,
        (course_id,),
    ).fetchall()
    return render_template("results/course.html", user=user, course=course, roster=roster)


@results_bp.route("/results/admin", methods=["GET", "POST"])
@login_required
@admin_required
def admin_dashboard():
    db = get_db()
    if request.method == "POST":
        supplied = request.form.get("csrf_token", "")
        if not secrets.compare_digest(supplied, csrf_token()):
            abort(400)
        action = request.form.get("action")
        if action == "course":
            code = request.form.get("code", "").strip().upper()
            name = request.form.get("name", "").strip()
            term = request.form.get("term", "").strip()
            teacher_id = request.form.get("teacher_id", type=int)
            max_marks = request.form.get("max_marks", type=float)
            teacher = db.execute(
                "SELECT id FROM users WHERE id = ? AND role = 'USER' AND university_role = 'TEACHER' AND status = 'VERIFIED'",
                (teacher_id,),
            ).fetchone()
            if not code or not name or not term or not teacher or max_marks is None or not isfinite(max_marks) or max_marks <= 0:
                flash("Enter valid course details and choose a verified teacher.", "error")
            else:
                try:
                    db.execute(
                        "INSERT INTO courses (code, name, term, teacher_id, max_marks, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (code, name, term, teacher_id, max_marks, datetime.now(timezone.utc).isoformat()),
                    )
                    db.commit()
                    admin = get_current_user()
                    log_activity(username=admin["username"], role="ADMIN", action="COURSE_CREATED", status="SUCCESS", user_id=admin["id"])
                    flash("Course created and assigned to the teacher.", "success")
                except Exception:
                    db.rollback()
                    flash("That course code is already in use.", "error")
        elif action == "enroll":
            course_id = request.form.get("course_id", type=int)
            student_id = request.form.get("student_id", type=int)
            student = db.execute(
                "SELECT id FROM users WHERE id = ? AND role = 'USER' AND university_role = 'STUDENT' AND status = 'VERIFIED'",
                (student_id,),
            ).fetchone()
            course = db.execute("SELECT id FROM courses WHERE id = ?", (course_id,)).fetchone()
            if not student or not course:
                flash("Choose a verified student and a valid course.", "error")
            else:
                db.execute(
                    "INSERT OR IGNORE INTO enrollments (course_id, student_id, created_at) VALUES (?, ?, ?)",
                    (course_id, student_id, datetime.now(timezone.utc).isoformat()),
                )
                db.commit()
                admin = get_current_user()
                log_activity(username=admin["username"], role="ADMIN", action="STUDENT_ENROLLED", status="SUCCESS", user_id=admin["id"])
                flash("Student enrolled in the course.", "success")
        return redirect(url_for("results.admin_dashboard"))

    teachers = db.execute(
        "SELECT id, username, full_name FROM users WHERE role = 'USER' AND university_role = 'TEACHER' AND status = 'VERIFIED' ORDER BY full_name"
    ).fetchall()
    students = db.execute(
        "SELECT id, username, full_name FROM users WHERE role = 'USER' AND university_role = 'STUDENT' AND status = 'VERIFIED' ORDER BY full_name"
    ).fetchall()
    courses = db.execute(
        "SELECT c.*, u.full_name AS teacher_name, COUNT(e.student_id) AS student_count FROM courses c JOIN users u ON u.id = c.teacher_id LEFT JOIN enrollments e ON e.course_id = c.id GROUP BY c.id ORDER BY c.term DESC, c.code"
    ).fetchall()
    return render_template("results/admin.html", user=get_current_user(), teachers=teachers, students=students, courses=courses)
