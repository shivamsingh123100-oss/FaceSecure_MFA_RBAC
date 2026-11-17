import secrets
from datetime import date, datetime, timezone
from functools import wraps
from io import BytesIO
from math import isfinite
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, flash, make_response, redirect, render_template, request, session, url_for

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


def attendance_summary(db, course_id, student_id):
    row = db.execute(
        """
        SELECT
            SUM(CASE WHEN status IN ('PRESENT', 'LATE') THEN 1 ELSE 0 END) AS attended,
            SUM(CASE WHEN status = 'ABSENT' THEN 1 ELSE 0 END) AS absent,
            SUM(CASE WHEN status = 'EXCUSED' THEN 1 ELSE 0 END) AS excused
        FROM attendance_records
        WHERE course_id = ? AND student_id = ?
        """,
        (course_id, student_id),
    ).fetchone()
    attended = row["attended"] or 0
    absent = row["absent"] or 0
    excused = row["excused"] or 0
    counted = attended + absent
    return {
        "attended": attended,
        "absent": absent,
        "excused": excused,
        "sessions": counted + excused,
        "rate": round(attended * 100 / counted) if counted else None,
    }


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
        SELECT c.id AS course_id, c.code, c.name, c.term, r.marks, c.max_marks, r.grade, r.updated_at
        FROM results r JOIN courses c ON c.id = r.course_id
        WHERE r.student_id = ? AND r.status = 'PUBLISHED'
        ORDER BY c.term DESC, c.code
        """,
        (user["id"],),
    ).fetchall()
    db = get_db()
    enrolled_count = db.execute(
        "SELECT COUNT(*) FROM enrollments WHERE student_id = ?",
        (user["id"],),
    ).fetchone()[0]
    waiting_count = db.execute(
        "SELECT COUNT(*) FROM results WHERE student_id = ? AND status = 'DRAFT'",
        (user["id"],),
    ).fetchone()[0]
    attendance = db.execute(
        """
        SELECT c.id, c.code, c.name, c.term,
            SUM(CASE WHEN ar.status IN ('PRESENT', 'LATE') THEN 1 ELSE 0 END) AS attended,
            SUM(CASE WHEN ar.status = 'ABSENT' THEN 1 ELSE 0 END) AS absent,
            SUM(CASE WHEN ar.status = 'EXCUSED' THEN 1 ELSE 0 END) AS excused
        FROM enrollments e
        JOIN courses c ON c.id = e.course_id
        LEFT JOIN attendance_records ar
            ON ar.course_id = e.course_id AND ar.student_id = e.student_id
        WHERE e.student_id = ?
        GROUP BY c.id
        ORDER BY c.term DESC, c.code
        """,
        (user["id"],),
    ).fetchall()
    attendance = [
        {
            **dict(row),
            "attended": row["attended"] or 0,
            "absent": row["absent"] or 0,
            "excused": row["excused"] or 0,
        }
        for row in attendance
    ]
    for item in attendance:
        counted = item["attended"] + item["absent"]
        item["rate"] = round(item["attended"] * 100 / counted) if counted else None
    return render_template(
        "results/student.html",
        user=user,
        results=results,
        enrolled_count=enrolled_count,
        waiting_count=waiting_count,
        attendance=attendance,
    )


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
    db = get_db()
    analyses = []
    for course in courses:
        roster = db.execute(
            """
            SELECT u.id, u.full_name, u.username, r.marks, r.status,
                (SELECT SUM(CASE WHEN ar.status IN ('PRESENT', 'LATE') THEN 1 ELSE 0 END)
                 FROM attendance_records ar WHERE ar.course_id = e.course_id AND ar.student_id = e.student_id) AS attended,
                (SELECT SUM(CASE WHEN ar.status = 'ABSENT' THEN 1 ELSE 0 END)
                 FROM attendance_records ar WHERE ar.course_id = e.course_id AND ar.student_id = e.student_id) AS absent
            FROM enrollments e
            JOIN users u ON u.id = e.student_id
            LEFT JOIN results r ON r.course_id = e.course_id AND r.student_id = e.student_id
            WHERE e.course_id = ?
            ORDER BY u.full_name
            """,
            (course["id"],),
        ).fetchall()
        learners = []
        scores = []
        attendance_rates = []
        for student in roster:
            mark_rate = round(student["marks"] * 100 / course["max_marks"]) if student["marks"] is not None else None
            attended = student["attended"] or 0
            absent = student["absent"] or 0
            attendance_rate = round(attended * 100 / (attended + absent)) if attended + absent else None
            needs_support = (mark_rate is not None and mark_rate < 60) or (attendance_rate is not None and attendance_rate < 75)
            if mark_rate is not None:
                scores.append(mark_rate)
            if attendance_rate is not None:
                attendance_rates.append(attendance_rate)
            if mark_rate is not None and mark_rate < 60:
                suggestion = "Review core topics together and set a short follow-up goal."
            elif attendance_rate is not None and attendance_rate < 75:
                suggestion = "Reconnect the student with missed lessons and agree on an attendance plan."
            else:
                suggestion = "Keep building on current strengths with a focused next-step goal."
            learners.append({
                "id": student["id"],
                "name": student["full_name"],
                "username": student["username"],
                "mark_rate": mark_rate,
                "attendance_rate": attendance_rate,
                "needs_support": needs_support,
                "suggestion": suggestion,
            })
        passing = [score for score in scores if score >= 60]
        analyses.append({
            "course": course,
            "students": learners,
            "average": round(sum(scores) / len(scores)) if scores else None,
            "pass_rate": round(len(passing) * 100 / len(scores)) if scores else None,
            "attendance_average": round(sum(attendance_rates) / len(attendance_rates)) if attendance_rates else None,
            "support_count": sum(1 for learner in learners if learner["needs_support"]),
            "graded_count": len(scores),
        })
    return render_template("results/teacher.html", user=user, courses=courses, analyses=analyses)


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


@results_bp.route("/results/teacher/course/<int:course_id>/attendance", methods=["GET", "POST"])
@user_required
@require_csrf
def teacher_attendance(course_id):
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

    today = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
    session_date = request.values.get("session_date", today)
    try:
        parsed_date = date.fromisoformat(session_date)
    except ValueError:
        abort(400)
    if parsed_date > date.fromisoformat(today):
        flash("Attendance can only be recorded for today or an earlier date.", "error")
        if request.method == "POST":
            return redirect(url_for("results.teacher_attendance", course_id=course_id, session_date=today))
        session_date = today

    roster = db.execute(
        """
        SELECT u.id, u.username, u.full_name, ar.status, ar.note
        FROM enrollments e
        JOIN users u ON u.id = e.student_id
        LEFT JOIN attendance_sessions s
            ON s.course_id = e.course_id AND s.session_date = ?
        LEFT JOIN attendance_records ar
            ON ar.session_id = s.id AND ar.student_id = e.student_id
        WHERE e.course_id = ?
        ORDER BY u.full_name
        """,
        (session_date, course_id),
    ).fetchall()

    if request.method == "POST":
        topic = request.form.get("topic", "").strip()
        if len(topic) > 120:
            flash("Keep the lesson topic under 120 characters.", "error")
        elif not roster:
            flash("Enroll students before recording attendance.", "error")
        else:
            statuses = {}
            invalid_student = None
            for student in roster:
                status = request.form.get(f"status_{student['id']}", "").upper()
                if status not in {"PRESENT", "ABSENT", "LATE", "EXCUSED"}:
                    invalid_student = student["full_name"]
                    break
                statuses[student["id"]] = status
            if invalid_student:
                flash(f"Choose an attendance status for {invalid_student}.", "error")
            else:
                timestamp = datetime.now(timezone.utc).isoformat()
                current = db.execute(
                    "SELECT id FROM attendance_sessions WHERE course_id = ? AND session_date = ?",
                    (course_id, session_date),
                ).fetchone()
                if current:
                    session_id = current["id"]
                    db.execute(
                        "UPDATE attendance_sessions SET topic = ?, created_by = ?, created_at = ? WHERE id = ?",
                        (topic, user["id"], timestamp, session_id),
                    )
                else:
                    db.execute(
                        "INSERT INTO attendance_sessions (course_id, session_date, topic, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
                        (course_id, session_date, topic, user["id"], timestamp),
                    )
                    session_id = db.execute(
                        "SELECT id FROM attendance_sessions WHERE course_id = ? AND session_date = ?",
                        (course_id, session_date),
                    ).fetchone()["id"]
                for student in roster:
                    note = request.form.get(f"note_{student['id']}", "").strip()[:240]
                    db.execute(
                        """
                        INSERT INTO attendance_records (session_id, course_id, student_id, status, note, marked_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(session_id, student_id) DO UPDATE SET
                            status = excluded.status, note = excluded.note, marked_at = excluded.marked_at
                        """,
                        (session_id, course_id, student["id"], statuses[student["id"]], note, timestamp),
                    )
                db.commit()
                log_activity(
                    username=user["username"], role=user["university_role"],
                    action="ATTENDANCE_RECORDED", status="SUCCESS", user_id=user["id"],
                )
                flash("Attendance saved for this course and date.", "success")
                return redirect(url_for("results.teacher_attendance", course_id=course_id, session_date=session_date))

    history = db.execute(
        """
        SELECT s.id, s.session_date, s.topic, COUNT(ar.id) AS marked_count,
            SUM(CASE WHEN ar.status IN ('PRESENT', 'LATE') THEN 1 ELSE 0 END) AS attended_count
        FROM attendance_sessions s
        LEFT JOIN attendance_records ar ON ar.session_id = s.id
        WHERE s.course_id = ?
        GROUP BY s.id
        ORDER BY s.session_date DESC
        """,
        (course_id,),
    ).fetchall()
    current_session = db.execute(
        "SELECT topic FROM attendance_sessions WHERE course_id = ? AND session_date = ?",
        (course_id, session_date),
    ).fetchone()
    return render_template(
        "results/attendance.html", user=user, course=course,
        roster=roster, history=history, session_date=session_date, today=today,
        current_topic=current_session["topic"] if current_session else "",
    )


@results_bp.route("/results/student/report.pdf")
@user_required
def student_report_pdf():
    user = get_current_user()
    if user["university_role"] != "STUDENT":
        abort(403)
    db = get_db()
    courses = db.execute(
        """
        SELECT c.id, c.code, c.name, c.term, c.max_marks,
            r.marks, r.grade, r.status, r.updated_at
        FROM enrollments e
        JOIN courses c ON c.id = e.course_id
        LEFT JOIN results r ON r.course_id = e.course_id AND r.student_id = e.student_id
        WHERE e.student_id = ?
        ORDER BY c.term DESC, c.code
        """,
        (user["id"],),
    ).fetchall()

    from html import escape
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=letter, rightMargin=.6 * inch, leftMargin=.6 * inch,
        topMargin=.6 * inch, bottomMargin=.6 * inch,
        title="Student Academic Performance Report",
        author="FaceSecure University Portal",
    )
    palette = {
        "navy": colors.HexColor("#17345f"),
        "blue": colors.HexColor("#4268d5"),
        "light": colors.HexColor("#eef3ff"),
        "line": colors.HexColor("#dce4f0"),
        "muted": colors.HexColor("#64748b"),
    }
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ReportTitle", parent=styles["Title"], alignment=TA_CENTER, textColor=palette["navy"], fontSize=20, leading=24, spaceAfter=4)
    small_style = ParagraphStyle("ReportSmall", parent=styles["Normal"], textColor=palette["muted"], fontSize=9, leading=13)
    section_style = ParagraphStyle("ReportSection", parent=styles["Heading2"], textColor=palette["navy"], fontSize=12, leading=16, spaceBefore=14, spaceAfter=7)
    story = [
        Paragraph("FaceSecure University", title_style),
        Paragraph("ACADEMIC PERFORMANCE REPORT · CONFIDENTIAL", ParagraphStyle("ReportLabel", parent=small_style, alignment=TA_CENTER, textColor=palette["blue"])),
        Spacer(1, 16),
    ]
    identity = [
        ["Student", escape(str(user["full_name"])), "Username", escape(str(user["username"]))],
        ["Generated", datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC"), "Courses", str(len(courses))],
    ]
    identity_table = Table(identity, colWidths=[.85 * inch, 2.35 * inch, .85 * inch, 2.4 * inch])
    identity_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), palette["light"]),
        ("BACKGROUND", (2, 0), (2, -1), palette["light"]),
        ("TEXTCOLOR", (0, 0), (0, -1), palette["navy"]),
        ("TEXTCOLOR", (2, 0), (2, -1), palette["navy"]),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), .5, palette["line"]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    story.extend([identity_table, Paragraph("Course results", section_style)])
    grade_rows = [["Course", "Term", "Score", "Grade", "Status"]]
    attendance_rows = [["Course", "Sessions", "Attended", "Absent", "Excused", "Rate"]]
    for course in courses:
        is_published = course["status"] == "PUBLISHED"
        score = f"{course['marks']:.1f} / {course['max_marks']:.1f}" if is_published else "Not released"
        grade_rows.append([escape(str(course["code"])), escape(str(course["term"])), score, course["grade"] if is_published else "—", "Published" if is_published else "Awaiting release"])
        summary = attendance_summary(db, course["id"], user["id"])
        attendance_rows.append([
            escape(str(course["code"])), str(summary["sessions"]), str(summary["attended"]),
            str(summary["absent"]), str(summary["excused"]),
            f"{summary['rate']}%" if summary["rate"] is not None else "—",
        ])
    attendance_details = db.execute(
        """
        SELECT c.code, s.session_date, s.topic, ar.status, ar.note
        FROM attendance_records ar
        JOIN attendance_sessions s ON s.id = ar.session_id
        JOIN courses c ON c.id = ar.course_id
        WHERE ar.student_id = ?
        ORDER BY s.session_date, c.code
        """,
        (user["id"],),
    ).fetchall()
    grid_style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), palette["navy"]),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), .45, palette["line"]),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8faff")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ])
    grade_table = Table(grade_rows, repeatRows=1, colWidths=[1.25 * inch, 1.0 * inch, 1.2 * inch, .65 * inch, 2.1 * inch])
    grade_table.setStyle(grid_style)
    story.append(grade_table)
    story.append(Paragraph("Attendance summary", section_style))
    attendance_table = Table(attendance_rows, repeatRows=1, colWidths=[1.25 * inch, .78 * inch, .85 * inch, .75 * inch, .8 * inch, .75 * inch])
    attendance_table.setStyle(grid_style)
    story.append(attendance_table)
    story.append(Paragraph("Attendance by class date", section_style))
    detail_rows = [["Course", "Date", "Lesson", "Status", "Note"]]
    for entry in attendance_details:
        detail_rows.append([
            escape(str(entry["code"])),
            escape(str(entry["session_date"])),
            escape(str(entry["topic"] or "Class session")),
            escape(str(entry["status"].title())),
            escape(str(entry["note"] or "—")),
        ])
    if len(detail_rows) == 1:
        detail_rows.append(["—", "—", "No attendance recorded", "—", "—"])
    detail_table = Table(detail_rows, repeatRows=1, colWidths=[.8 * inch, .83 * inch, 1.85 * inch, .75 * inch, 2.47 * inch])
    detail_table.setStyle(grid_style)
    story.append(detail_table)
    story.extend([
        Paragraph("Teacher / advisor feedback", section_style),
        Paragraph("Use the space below for feedback when this report is shared.", small_style),
        Spacer(1, 8),
    ])
    feedback = Table([[" "], [" "], [" "]], colWidths=[6.7 * inch], rowHeights=[.34 * inch, .34 * inch, .34 * inch])
    feedback.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), .7, palette["line"]), ("INNERGRID", (0, 0), (-1, -1), .45, palette["line"])]))
    story.extend([feedback, Spacer(1, 10), Paragraph("Attendance rate counts present and late marks over sessions that were not excused. Draft marks are excluded from this student report.", small_style)])
    document.build(story)
    response = make_response(buffer.getvalue())
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f"attachment; filename=academic-report-{user['id']}.pdf"
    response.headers["Cache-Control"] = "private, no-store"
    return response


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
                cursor = db.execute(
                    "INSERT OR IGNORE INTO enrollments (course_id, student_id, created_at) VALUES (?, ?, ?)",
                    (course_id, student_id, datetime.now(timezone.utc).isoformat()),
                )
                db.commit()
                if cursor.rowcount:
                    admin = get_current_user()
                    log_activity(username=admin["username"], role="ADMIN", action="STUDENT_ENROLLED", status="SUCCESS", user_id=admin["id"])
                    flash("Student enrolled in the course.", "success")
                else:
                    flash("That student is already enrolled in this course.", "info")
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

