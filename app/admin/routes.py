from functools import wraps
from datetime import datetime
import csv
import io
import json
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, jsonify, Response
from flask_login import login_required, current_user
from flask_babel import _
from app.extensions import db, bcrypt
from app.models import (User, TeacherProfile, Subject, GradeGroup, GradeGroupSubject,
                        TeacherSubjectGrade, StudentProfile, GuardianStudent,
                        ConferenceEvent, ConferenceDay, Slot, Booking, EmailNotification,
                        TeacherDayAbsence, StudentSubjectExclusion)
from app.admin.forms import (GradeGroupForm, SubjectForm, TeacherForm, StudentForm,
                              GuardianForm, AdminForm, ConferenceEventForm, NotifyForm)
from app.utils import generate_token, send_invite_email, send_conference_info_email, send_reset_email, generate_slots_for_day

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ── Dashboard ─────────────────────────────────────────────────────────────────

@admin_bp.route("/")
@login_required
@admin_required
def dashboard():
    total_students = User.query.filter_by(role="student").count()
    total_teachers = User.query.filter_by(role="teacher").count()
    total_guardians = User.query.filter_by(role="guardian").count()
    active_events = ConferenceEvent.query.filter_by(status="published").order_by(ConferenceEvent.created_at.desc()).all()
    events_stats = []
    for ev in active_events:
        total_slots = Slot.query.join(ConferenceDay).filter(ConferenceDay.event_id == ev.id).count()
        booked = Slot.query.join(ConferenceDay).filter(
            ConferenceDay.event_id == ev.id, Slot.is_booked == True).count()
        events_stats.append({"event": ev, "total_slots": total_slots, "booked": booked})
    recent_emails = EmailNotification.query.order_by(EmailNotification.sent_at.desc()).limit(10).all()
    return render_template("admin/dashboard.html",
                           total_students=total_students,
                           total_teachers=total_teachers,
                           total_guardians=total_guardians,
                           events_stats=events_stats,
                           recent_emails=recent_emails)


# ── Grade Groups ───────────────────────────────────────────────────────────────

@admin_bp.route("/grades", methods=["GET", "POST"])
@login_required
@admin_required
def grades():
    grade_form   = GradeGroupForm(prefix="grade")
    subject_form = SubjectForm(prefix="subject")

    if grade_form.submit.data and grade_form.validate():
        if GradeGroup.query.filter_by(name=grade_form.name.data).first():
            flash(_("Turma já existe."), "warning")
        else:
            db.session.add(GradeGroup(name=grade_form.name.data))
            db.session.commit()
            flash(_("Turma adicionada."), "success")
        return redirect(url_for("admin.grades"))

    if subject_form.submit.data and subject_form.validate():
        if Subject.query.filter_by(name=subject_form.name.data).first():
            flash(_("Disciplina já existe."), "warning")
        else:
            db.session.add(Subject(name=subject_form.name.data))
            db.session.commit()
            flash(_("Disciplina adicionada."), "success")
        return redirect(url_for("admin.grades"))

    all_grades   = GradeGroup.query.order_by(GradeGroup.name).all()
    all_subjects = Subject.query.order_by(Subject.name).all()
    active = {(gs.grade_group_id, gs.subject_id) for gs in GradeGroupSubject.query.all()}
    return render_template("admin/grades.html",
                           grade_form=grade_form, subject_form=subject_form,
                           grades=all_grades, all_subjects=all_subjects, active=active)


@admin_bp.route("/grades/<int:grade_id>/subjects/<int:subject_id>/toggle", methods=["POST"])
@login_required
@admin_required
def toggle_grade_subject(grade_id, subject_id):
    GradeGroup.query.get_or_404(grade_id)
    Subject.query.get_or_404(subject_id)
    existing = GradeGroupSubject.query.filter_by(
        grade_group_id=grade_id, subject_id=subject_id).first()
    if existing:
        db.session.delete(existing)
        # Cascade: remove this subject-grade pair from all teacher assignments
        TeacherSubjectGrade.query.filter_by(
            grade_group_id=grade_id, subject_id=subject_id
        ).delete(synchronize_session=False)
    else:
        db.session.add(GradeGroupSubject(grade_group_id=grade_id, subject_id=subject_id))
    db.session.commit()
    return redirect(url_for("admin.grades"))


@admin_bp.route("/grades/<int:id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_grade(id):
    grade = GradeGroup.query.get_or_404(id)
    db.session.delete(grade)
    db.session.commit()
    flash(_("Turma excluída."), "success")
    return redirect(url_for("admin.grades"))


# ── Subjects (kept for URL compatibility – all logic now lives in grades()) ───

@admin_bp.route("/subjects")
@login_required
@admin_required
def subjects():
    return redirect(url_for("admin.grades"))


@admin_bp.route("/subjects/<int:id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_subject(id):
    subject = Subject.query.get_or_404(id)
    db.session.delete(subject)
    db.session.commit()
    flash(_("Disciplina excluída."), "success")
    return redirect(url_for("admin.grades"))


# ── Teachers ───────────────────────────────────────────────────────────────────

@admin_bp.route("/teachers")
@login_required
@admin_required
def teachers():
    grade_filter = request.args.get("grade_id", type=int)
    query = User.query.filter_by(role="teacher")
    if grade_filter:
        query = query.join(TeacherProfile).join(TeacherSubjectGrade,
            TeacherSubjectGrade.teacher_id == User.id).filter(
            TeacherSubjectGrade.grade_group_id == grade_filter)
    teachers = query.order_by(User.last_name).all()
    grades = GradeGroup.query.order_by(GradeGroup.name).all()
    return render_template("admin/teachers.html", teachers=teachers, grades=grades, grade_filter=grade_filter)


@admin_bp.route("/teachers/new", methods=["GET", "POST"])
@login_required
@admin_required
def new_teacher():
    form = TeacherForm()
    grade_subjects = _get_grade_subjects_map()
    if form.validate_on_submit():
        email = form.email.data.lower().strip()
        if User.query.filter_by(email=email).first():
            flash(_("Já existe um usuário com este e-mail."), "danger")
        else:
            user = User(
                email=email,
                role="teacher",
                first_name=form.first_name.data,
                last_name=form.last_name.data,
                preferred_language="en",
            )
            db.session.add(user)
            db.session.flush()
            profile = TeacherProfile(user_id=user.id, bio="")
            db.session.add(profile)
            _save_teacher_subject_grades(user.id, request.form)
            token = generate_token(user.email, salt="invite")
            user.invite_token = token
            user.invite_sent_at = datetime.utcnow()
            db.session.commit()
            try:
                send_invite_email(user, token)
                flash(_("Professor criado e convite enviado para %(email)s.", email=email), "success")
            except Exception as e:
                flash(_("Professor criado, mas falha no e-mail: %(err)s", err=str(e)), "warning")
            return redirect(url_for("admin.teachers"))
    return render_template("admin/teacher_form.html", form=form, grade_subjects=grade_subjects, teacher=None)


@admin_bp.route("/teachers/<int:id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_teacher(id):
    user = User.query.filter_by(id=id, role="teacher").first_or_404()
    form = TeacherForm(obj=user)
    grade_subjects = _get_grade_subjects_map()
    if form.validate_on_submit():
        user.first_name = form.first_name.data
        user.last_name = form.last_name.data
        user.email = form.email.data.lower().strip()
        TeacherSubjectGrade.query.filter_by(teacher_id=user.id).delete()
        _save_teacher_subject_grades(user.id, request.form)
        db.session.commit()
        flash(_("Professor atualizado."), "success")
        return redirect(url_for("admin.teachers"))
    existing_sgs = {(t.grade_group_id, t.subject_id)
                    for t in TeacherSubjectGrade.query.filter_by(teacher_id=user.id).all()}
    return render_template("admin/teacher_form.html", form=form, grade_subjects=grade_subjects,
                           teacher=user, existing_sgs=existing_sgs)


@admin_bp.route("/teachers/<int:id>/resend-invite", methods=["POST"])
@login_required
@admin_required
def resend_teacher_invite(id):
    user = User.query.filter_by(id=id, role="teacher").first_or_404()
    if user.has_password():
        flash(_("Este professor já configurou sua senha."), "info")
    else:
        token = generate_token(user.email, salt="invite")
        user.invite_token = token
        user.invite_sent_at = datetime.utcnow()
        db.session.commit()
        try:
            send_invite_email(user, token)
            flash(_("Convite reenviado."), "success")
        except Exception as e:
            flash(_("Falha no e-mail: %(err)s", err=str(e)), "danger")
    return redirect(url_for("admin.teachers"))


@admin_bp.route("/teachers/<int:id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_teacher(id):
    user = User.query.filter_by(id=id, role="teacher").first_or_404()
    try:
        # 1. Delete bookings for this teacher's slots
        #    (bulk Slot.delete() bypasses ORM cascade → must do it manually)
        slot_ids = [row.id for row in Slot.query.filter_by(teacher_id=user.id).with_entities(Slot.id).all()]
        if slot_ids:
            Booking.query.filter(Booking.slot_id.in_(slot_ids)).delete(synchronize_session=False)
        # 2. Delete slots
        Slot.query.filter_by(teacher_id=user.id).delete(synchronize_session=False)
        # 3. Delete subject-grade assignments (FK → user.id, outside ORM cascade chain)
        TeacherSubjectGrade.query.filter_by(teacher_id=user.id).delete(synchronize_session=False)
        # 4. Delete the user (TeacherProfile cascades automatically)
        db.session.delete(user)
        db.session.commit()
        flash(_("Professor excluído."), "success")
    except Exception as e:
        db.session.rollback()
        flash(_("Erro ao excluir professor: %(err)s", err=str(e)), "danger")
    return redirect(url_for("admin.teachers"))


@admin_bp.route("/students/<int:id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_student(id):
    user = User.query.filter_by(id=id, role="student").first_or_404()
    try:
        # Delete bookings where this student is the student or the booker
        Booking.query.filter(
            (Booking.student_id == user.id) | (Booking.booked_by_id == user.id)
        ).delete(synchronize_session=False)
        # Free up any slots that were booked for this student
        Slot.query.filter_by(teacher_id=user.id).delete(synchronize_session=False)
        db.session.delete(user)
        db.session.commit()
        flash(_("Aluno excluído."), "success")
    except Exception as e:
        db.session.rollback()
        flash(_("Erro ao excluir aluno: %(err)s", err=str(e)), "danger")
    return redirect(url_for("admin.students"))


@admin_bp.route("/users/<int:user_id>/send-reset", methods=["POST"])
@login_required
@admin_required
def send_user_reset(user_id):
    """Send a password-set (first access) or reset email to any user."""
    user = User.query.get_or_404(user_id)
    redirect_target = request.form.get("redirect_to", "admin.teachers")
    try:
        if not user.has_password():
            token = generate_token(user.email, salt="invite")
            user.invite_token = token
            user.invite_sent_at = datetime.utcnow()
            db.session.commit()
            send_invite_email(user, token)
        else:
            token = generate_token(user.email, salt="reset")
            send_reset_email(user, token)
        flash(_("E-mail enviado para %(name)s.", name=user.first_name), "success")
    except Exception as e:
        flash(_("Falha ao enviar e-mail: %(err)s", err=str(e)), "danger")
    return redirect(url_for(redirect_target))


# ── Guardians ─────────────────────────────────────────────────────────────────

@admin_bp.route("/guardians")
@login_required
@admin_required
def guardians():
    guardian_list = (User.query.filter_by(role="guardian")
                     .order_by(User.last_name, User.first_name).all())
    return render_template("admin/guardians.html", guardians=guardian_list)


@admin_bp.route("/guardians/<int:id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_guardian(id):
    user = User.query.filter_by(id=id, role="guardian").first_or_404()
    form = GuardianForm(obj=user)
    if form.validate_on_submit():
        new_email = form.email.data.lower().strip()
        clash = User.query.filter(User.email == new_email, User.id != user.id).first()
        if clash:
            flash(_("Já existe um usuário com este e-mail."), "danger")
        else:
            user.first_name = form.first_name.data
            user.last_name  = form.last_name.data
            user.email      = new_email
            db.session.commit()
            flash(_("Responsável atualizado."), "success")
            return redirect(url_for("admin.guardians"))
    return render_template("admin/guardian_form.html", form=form, guardian=user)


@admin_bp.route("/guardians/<int:id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_guardian(id):
    user = User.query.filter_by(id=id, role="guardian").first_or_404()
    try:
        Booking.query.filter(Booking.booked_by_id == user.id).delete(synchronize_session=False)
        db.session.delete(user)
        db.session.commit()
        flash(_("Responsável excluído."), "success")
    except Exception as e:
        db.session.rollback()
        flash(_("Erro ao excluir responsável: %(err)s", err=str(e)), "danger")
    return redirect(url_for("admin.guardians"))


# ── Admin management ───────────────────────────────────────────────────────────

@admin_bp.route("/admins")
@login_required
@admin_required
def admins():
    admin_list = (User.query.filter_by(role="admin")
                  .order_by(User.last_name, User.first_name).all())
    return render_template("admin/admins.html", admins=admin_list)


@admin_bp.route("/admins/new", methods=["GET", "POST"])
@login_required
@admin_required
def new_admin():
    form = AdminForm()
    if form.validate_on_submit():
        email = form.email.data.lower().strip()
        if User.query.filter_by(email=email).first():
            flash(_("Já existe um usuário com este e-mail."), "danger")
        else:
            user = User(
                email=email,
                role="admin",
                first_name=form.first_name.data,
                last_name=form.last_name.data,
                preferred_language="pt",
            )
            db.session.add(user)
            db.session.flush()
            token = generate_token(user.email, salt="invite")
            user.invite_token = token
            user.invite_sent_at = datetime.utcnow()
            db.session.commit()
            try:
                send_invite_email(user, token)
                flash(_("Administrador criado e convite enviado para %(email)s.", email=email), "success")
            except Exception as e:
                flash(_("Administrador criado, mas falha no e-mail: %(err)s", err=str(e)), "warning")
            return redirect(url_for("admin.admins"))
    return render_template("admin/admin_form.html", form=form, admin_user=None)


@admin_bp.route("/admins/<int:id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_admin(id):
    user = User.query.filter_by(id=id, role="admin").first_or_404()
    form = AdminForm(obj=user)
    if form.validate_on_submit():
        new_email = form.email.data.lower().strip()
        clash = User.query.filter(User.email == new_email, User.id != user.id).first()
        if clash:
            flash(_("Este e-mail já está em uso."), "danger")
        else:
            user.first_name = form.first_name.data
            user.last_name = form.last_name.data
            user.email = new_email
            db.session.commit()
            flash(_("Administrador atualizado."), "success")
            return redirect(url_for("admin.admins"))
    return render_template("admin/admin_form.html", form=form, admin_user=user)


@admin_bp.route("/admins/<int:id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_admin(id):
    user = User.query.filter_by(id=id, role="admin").first_or_404()
    if user.id == current_user.id:
        flash(_("Você não pode excluir sua própria conta."), "danger")
        return redirect(url_for("admin.admins"))
    try:
        db.session.delete(user)
        db.session.commit()
        flash(_("Administrador excluído."), "success")
    except Exception as e:
        db.session.rollback()
        flash(_("Erro ao excluir: %(err)s", err=str(e)), "danger")
    return redirect(url_for("admin.admins"))


# ── Bulk actions ───────────────────────────────────────────────────────────────

@admin_bp.route("/users/bulk-delete", methods=["POST"])
@login_required
@admin_required
def bulk_delete():
    ids = [int(i) for i in request.form.get("ids", "").split(",") if i.strip().isdigit()]
    redirect_to = request.form.get("redirect_to", "admin.teachers")
    deleted = 0
    for uid in ids:
        user = User.query.get(uid)
        if not user or user.role == "admin":
            continue
        try:
            if user.role == "teacher":
                slot_ids = [r.id for r in
                            Slot.query.filter_by(teacher_id=user.id).with_entities(Slot.id).all()]
                if slot_ids:
                    Booking.query.filter(Booking.slot_id.in_(slot_ids)).delete(synchronize_session=False)
                Slot.query.filter_by(teacher_id=user.id).delete(synchronize_session=False)
                TeacherSubjectGrade.query.filter_by(teacher_id=user.id).delete(synchronize_session=False)
            else:
                Booking.query.filter(
                    (Booking.student_id == user.id) | (Booking.booked_by_id == user.id)
                ).delete(synchronize_session=False)
            db.session.delete(user)
            deleted += 1
        except Exception:
            db.session.rollback()
            flash(_("Erro ao excluir usuários."), "danger")
            return redirect(url_for(redirect_to))
    db.session.commit()
    flash(_("%(count)d usuário(s) excluído(s).", count=deleted), "success")
    return redirect(url_for(redirect_to))


@admin_bp.route("/users/bulk-email", methods=["POST"])
@login_required
@admin_required
def bulk_email():
    ids = [int(i) for i in request.form.get("ids", "").split(",") if i.strip().isdigit()]
    redirect_to = request.form.get("redirect_to", "admin.teachers")
    sent = errors = 0
    for uid in ids:
        user = User.query.get(uid)
        if not user:
            continue
        try:
            if not user.has_password():
                token = generate_token(user.email, salt="invite")
                user.invite_token = token
                user.invite_sent_at = datetime.utcnow()
                db.session.commit()
                send_invite_email(user, token)
            else:
                token = generate_token(user.email, salt="reset")
                send_reset_email(user, token)
            sent += 1
        except Exception:
            errors += 1
    if sent:
        flash(_("%(count)d e-mail(s) enviado(s).", count=sent), "success")
    if errors:
        flash(_("%(count)d e-mail(s) com falha.", count=errors), "warning")
    return redirect(url_for(redirect_to))


# ── CSV helpers ────────────────────────────────────────────────────────────────

# All available columns per entity (email always included automatically)
_TEACHER_COLS  = ["email", "first_name", "last_name", "subjects_grades", "status"]
_STUDENT_COLS  = ["email", "first_name", "last_name", "grade", "subjects", "guardian1", "guardian2", "status"]
_GUARDIAN_COLS = ["email", "first_name", "last_name", "student1", "student2", "status"]


def _csv_response(rows, headers, filename):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    w.writerows(rows)
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _parse_cols(param, allowed, always=("email",)):
    """Return ordered list of column names from comma-separated param, filtered to allowed set."""
    requested = [c.strip() for c in param.split(",") if c.strip() in allowed]
    # ensure always-required columns are present
    for c in always:
        if c not in requested:
            requested.insert(0, c)
    return requested


def _parse_csv_upload():
    f = request.files.get("csv_file")
    if not f or not f.filename:
        raise ValueError(_("Nenhum arquivo enviado."))
    stream = io.StringIO(f.stream.read().decode("utf-8-sig"))
    reader = csv.DictReader(stream)
    rows = list(reader)
    if not rows:
        raise ValueError(_("Arquivo vazio ou sem linhas de dados."))
    return rows


def _teacher_row(t, cols):
    row = []
    for c in cols:
        if c == "email":          row.append(t.email)
        elif c == "first_name":   row.append(t.first_name)
        elif c == "last_name":    row.append(t.last_name)
        elif c == "subjects_grades":
            sgs = t.teacher_profile.subject_grades if t.teacher_profile else []
            items = [f"{sg.subject.name}/{sg.grade_group.name}" for sg in sgs]
            # Always use JSON array so multiple entries are unambiguous
            row.append(json.dumps(items, ensure_ascii=False))
        elif c == "status":       row.append("Ativo" if t.has_password() else "Pendente")
    return row


def _guardian_obj(g):
    """Compact JSON object for a guardian embedded in a student row."""
    return json.dumps({"email": g.email, "first_name": g.first_name, "last_name": g.last_name},
                      ensure_ascii=False)


def _student_obj(s):
    """Compact JSON object for a student embedded in a guardian row."""
    grade = s.student_profile.grade_group.name if s.student_profile else ""
    return json.dumps({"email": s.email, "first_name": s.first_name,
                       "last_name": s.last_name, "grade": grade}, ensure_ascii=False)


def _student_active_subjects(s):
    """Return list of Subject names the student actually has (grade subjects minus exclusions)."""
    if not s.student_profile:
        return []
    grade_subject_ids = {gs.subject_id for gs in s.student_profile.grade_group.grade_subjects}
    excluded_ids = {e.subject_id for e in
                    StudentSubjectExclusion.query.filter_by(student_id=s.id).all()}
    active_ids = grade_subject_ids - excluded_ids
    subjects = Subject.query.filter(Subject.id.in_(active_ids)).order_by(Subject.name).all()
    return [sub.name for sub in subjects]


def _student_row(s, cols):
    guardians = [gs.guardian for gs in s.student_guardians]
    row = []
    for c in cols:
        if c == "email":        row.append(s.email)
        elif c == "first_name": row.append(s.first_name)
        elif c == "last_name":  row.append(s.last_name)
        elif c == "grade":      row.append(s.student_profile.grade_group.name if s.student_profile else "")
        elif c == "subjects":   row.append(json.dumps(_student_active_subjects(s), ensure_ascii=False))
        elif c == "status":     row.append("Ativo" if s.has_password() else "Pendente")
        elif c == "guardian1":  row.append(_guardian_obj(guardians[0]) if len(guardians) > 0 else "")
        elif c == "guardian2":  row.append(_guardian_obj(guardians[1]) if len(guardians) > 1 else "")
    return row


def _guardian_row(g, cols):
    """One row per guardian; students are embedded as JSON objects in student1/student2 cells."""
    students = [gs.student for gs in g.guardian_students]
    row = []
    for c in cols:
        if c == "email":        row.append(g.email)
        elif c == "first_name": row.append(g.first_name)
        elif c == "last_name":  row.append(g.last_name)
        elif c == "status":     row.append("Ativo" if g.has_password() else "Pendente")
        elif c == "student1":   row.append(_student_obj(students[0]) if len(students) > 0 else "")
        elif c == "student2":   row.append(_student_obj(students[1]) if len(students) > 1 else "")
    return row


# ── CSV export ─────────────────────────────────────────────────────────────────

@admin_bp.route("/teachers/export.csv")
@login_required
@admin_required
def export_teachers():
    cols = _parse_cols(request.args.get("cols", ",".join(_TEACHER_COLS)), _TEACHER_COLS)
    teachers = User.query.filter_by(role="teacher").order_by(User.last_name, User.first_name).all()
    return _csv_response([_teacher_row(t, cols) for t in teachers], cols, "professores.csv")


@admin_bp.route("/teachers/template.csv")
@login_required
@admin_required
def template_teachers():
    # Template never includes "status" (read-only) or "subjects_grades" by default
    all_import_cols = [c for c in _TEACHER_COLS if c != "status"]
    cols = _parse_cols(request.args.get("cols", "email,first_name,last_name"), all_import_cols)
    example = {"email": "joao.silva@escola.com", "first_name": "João",
                "last_name": "Silva",
                "subjects_grades": json.dumps(["Matemática/9º Ano A", "Português/9º Ano B"], ensure_ascii=False)}
    return _csv_response([[example.get(c, "") for c in cols]], cols, "modelo_professores.csv")


@admin_bp.route("/students/export.csv")
@login_required
@admin_required
def export_students():
    cols = _parse_cols(request.args.get("cols", ",".join(_STUDENT_COLS)), _STUDENT_COLS)
    students = User.query.filter_by(role="student").order_by(User.last_name, User.first_name).all()
    return _csv_response([_student_row(s, cols) for s in students], cols, "alunos.csv")


@admin_bp.route("/students/template.csv")
@login_required
@admin_required
def template_students():
    all_import_cols = [c for c in _STUDENT_COLS if c != "status"]
    cols = _parse_cols(request.args.get("cols", "email,first_name,last_name,grade"), all_import_cols)
    g_ex = json.dumps({"email": "carlos@email.com", "first_name": "Carlos", "last_name": "Oliveira"},
                      ensure_ascii=False)
    example = {"email": "maria.santos@escola.com", "first_name": "Maria",
               "last_name": "Santos", "grade": "9º Ano A",
               "subjects": json.dumps(["Matemática", "Português", "História"], ensure_ascii=False),
               "guardian1": g_ex, "guardian2": ""}
    return _csv_response([[example.get(c, "") for c in cols]], cols, "modelo_alunos.csv")


@admin_bp.route("/guardians/export.csv")
@login_required
@admin_required
def export_guardians():
    cols = _parse_cols(request.args.get("cols", ",".join(_GUARDIAN_COLS)), _GUARDIAN_COLS)
    guardians = User.query.filter_by(role="guardian").order_by(User.last_name, User.first_name).all()
    return _csv_response([_guardian_row(g, cols) for g in guardians], cols, "responsaveis.csv")


@admin_bp.route("/guardians/template.csv")
@login_required
@admin_required
def template_guardians():
    all_import_cols = [c for c in _GUARDIAN_COLS if c != "status"]
    cols = _parse_cols(request.args.get("cols", "email,first_name,last_name,student1"), all_import_cols)
    s_ex = json.dumps({"email": "maria.santos@escola.com", "first_name": "Maria",
                       "last_name": "Santos", "grade": "9º Ano A"}, ensure_ascii=False)
    example = {"email": "carlos@email.com", "first_name": "Carlos",
               "last_name": "Oliveira", "student1": s_ex, "student2": ""}
    return _csv_response([[example.get(c, "") for c in cols]], cols, "modelo_responsaveis.csv")


@admin_bp.route("/grades/matrix/export.csv")
@login_required
@admin_required
def export_grades_matrix():
    """Export grade × subject matrix: rows = grades, columns = subjects, cells = 1/0."""
    grades   = GradeGroup.query.order_by(GradeGroup.name).all()
    subjects = Subject.query.order_by(Subject.name).all()
    active   = {(gs.grade_group_id, gs.subject_id) for gs in GradeGroupSubject.query.all()}
    headers  = ["grade"] + [s.name for s in subjects]
    rows = [
        [g.name] + ["1" if (g.id, s.id) in active else "0" for s in subjects]
        for g in grades
    ]
    return _csv_response(rows, headers, "turmas_materias.csv")


@admin_bp.route("/grades/matrix/template.csv")
@login_required
@admin_required
def template_grades_matrix():
    """Return a minimal template with two example rows."""
    subjects = Subject.query.order_by(Subject.name).all()
    if subjects:
        headers = ["grade"] + [s.name for s in subjects]
        rows = [
            ["9º Ano A"] + ["1"] * len(subjects),
            ["9º Ano B"] + ["0"] * len(subjects),
        ]
    else:
        headers = ["grade", "Matemática", "Português"]
        rows = [["9º Ano A", "1", "1"], ["9º Ano B", "1", "0"]]
    return _csv_response(rows, headers, "modelo_turmas_materias.csv")


# ── CSV import ─────────────────────────────────────────────────────────────────

def _link_guardian_to_student(student_id, g_json_str):
    """Parse a guardian JSON object string and find-or-create the guardian, then link to student."""
    if not g_json_str:
        return
    try:
        data = json.loads(g_json_str)
    except (json.JSONDecodeError, ValueError):
        return
    em = data.get("email", "").strip().lower()
    fn = data.get("first_name", "").strip()
    ln = data.get("last_name", "").strip()
    if not em:
        return
    guardian = User.query.filter_by(email=em).first()
    if not guardian:
        if not fn or not ln:
            return
        guardian = User(email=em, role="guardian", first_name=fn, last_name=ln, preferred_language="en")
        db.session.add(guardian)
        db.session.flush()
    if not GuardianStudent.query.filter_by(guardian_id=guardian.id, student_id=student_id).first():
        db.session.add(GuardianStudent(guardian_id=guardian.id, student_id=student_id))


def _link_student_to_guardian(guardian_id, s_json_str):
    """Parse a student JSON object string and link the (existing) student to the guardian."""
    if not s_json_str:
        return
    try:
        data = json.loads(s_json_str)
    except (json.JSONDecodeError, ValueError):
        return
    em = data.get("email", "").strip().lower()
    if not em:
        return
    student = User.query.filter_by(email=em, role="student").first()
    if student and not GuardianStudent.query.filter_by(
            guardian_id=guardian_id, student_id=student.id).first():
        db.session.add(GuardianStudent(guardian_id=guardian_id, student_id=student.id))


def _import_teacher_subjects(teacher_id, subjects_grades_str):
    """Parse subjects_grades cell (JSON array or legacy semicolon string) and create records."""
    # Try JSON array first: ["Subject/Grade", ...]
    pairs = []
    stripped = subjects_grades_str.strip()
    if stripped.startswith("["):
        try:
            pairs = [p.strip() for p in json.loads(stripped) if isinstance(p, str) and p.strip()]
        except (json.JSONDecodeError, ValueError):
            pass
    if not pairs:
        # Fallback: legacy semicolon-separated "Subject/Grade; Subject2/Grade2"
        pairs = [p.strip() for p in stripped.split(";") if p.strip()]

    for pair in pairs:
        if "/" not in pair:
            continue
        subject_name, grade_name = [x.strip() for x in pair.split("/", 1)]
        subject = Subject.query.filter(db.func.lower(Subject.name) == subject_name.lower()).first()
        grade   = GradeGroup.query.filter(db.func.lower(GradeGroup.name) == grade_name.lower()).first()
        if subject and grade:
            if not TeacherSubjectGrade.query.filter_by(
                    teacher_id=teacher_id, subject_id=subject.id, grade_group_id=grade.id).first():
                db.session.add(TeacherSubjectGrade(
                    teacher_id=teacher_id, subject_id=subject.id, grade_group_id=grade.id))


@admin_bp.route("/teachers/import", methods=["POST"])
@login_required
@admin_required
def import_teachers():
    mode = request.form.get("mode", "add")
    cols = set(_parse_cols(request.form.get("cols", "email,first_name,last_name"), _TEACHER_COLS))
    has_names = "first_name" in cols and "last_name" in cols
    try:
        raw = _parse_csv_upload()
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for("admin.teachers"))

    emails_in_file, valid_rows = set(), []
    for row in raw:
        em = row.get("email", "").strip().lower()
        if not em:
            continue
        fn = row.get("first_name", "").strip() if "first_name" in cols else ""
        ln = row.get("last_name", "").strip()  if "last_name"  in cols else ""
        sg = row.get("subjects_grades", "").strip() if "subjects_grades" in cols else ""
        if has_names and mode != "delete" and (not fn or not ln):
            continue
        valid_rows.append((fn, ln, em, sg))
        emails_in_file.add(em)

    def _delete_teacher(user):
        slot_ids = [r.id for r in Slot.query.filter_by(teacher_id=user.id).with_entities(Slot.id).all()]
        if slot_ids:
            Booking.query.filter(Booking.slot_id.in_(slot_ids)).delete(synchronize_session=False)
        Slot.query.filter_by(teacher_id=user.id).delete(synchronize_session=False)
        TeacherSubjectGrade.query.filter_by(teacher_id=user.id).delete(synchronize_session=False)
        db.session.delete(user)

    if mode == "delete":
        deleted = 0
        for _, _, em, _ in valid_rows:
            user = User.query.filter_by(email=em, role="teacher").first()
            if user:
                _delete_teacher(user)
                deleted += 1
        db.session.commit()
        flash(_("%(deleted)d professor(es) apagado(s).", deleted=deleted), "success")
        return redirect(url_for("admin.teachers"))

    if mode == "replace":
        for user in User.query.filter_by(role="teacher").filter(~User.email.in_(emails_in_file)).all():
            _delete_teacher(user)
        db.session.flush()

    added = 0
    for fn, ln, em, sg in valid_rows:
        if User.query.filter_by(email=em).first():
            continue
        if not has_names:
            continue
        user = User(email=em, role="teacher", first_name=fn, last_name=ln, preferred_language="en")
        db.session.add(user)
        db.session.flush()
        db.session.add(TeacherProfile(user_id=user.id, bio=""))
        if sg:
            _import_teacher_subjects(user.id, sg)
        added += 1

    db.session.commit()
    flash(_("%(added)d professor(es) importado(s).", added=added), "success")
    return redirect(url_for("admin.teachers"))


@admin_bp.route("/students/import", methods=["POST"])
@login_required
@admin_required
def import_students():
    mode = request.form.get("mode", "add")
    cols = set(_parse_cols(request.form.get("cols", "email,first_name,last_name,grade"), _STUDENT_COLS))
    has_names = "first_name" in cols and "last_name" in cols
    try:
        raw = _parse_csv_upload()
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for("admin.students"))

    emails_in_file, valid_rows = set(), []
    for row in raw:
        em = row.get("email", "").strip().lower()
        if not em:
            continue
        fn         = row.get("first_name", "").strip() if "first_name" in cols else ""
        ln         = row.get("last_name", "").strip()  if "last_name"  in cols else ""
        grade_name = row.get("grade", "").strip()      if "grade"      in cols else ""
        subj_str   = row.get("subjects", "").strip()   if "subjects"   in cols else ""
        g1 = row.get("guardian1", "").strip() if "guardian1" in cols else ""
        g2 = row.get("guardian2", "").strip() if "guardian2" in cols else ""
        if has_names and mode != "delete" and (not fn or not ln):
            continue
        valid_rows.append((fn, ln, em, grade_name, subj_str, g1, g2))
        emails_in_file.add(em)

    def _delete_student(user):
        Booking.query.filter(
            (Booking.student_id == user.id) | (Booking.booked_by_id == user.id)
        ).delete(synchronize_session=False)
        db.session.delete(user)

    def _apply_subject_exclusions(user_id, grade_id, subj_str):
        """Set exclusions so the student only has the subjects listed in subj_str."""
        if not subj_str:
            return
        stripped = subj_str.strip()
        try:
            provided = json.loads(stripped) if stripped.startswith("[") else \
                       [p.strip() for p in stripped.split(";") if p.strip()]
        except (json.JSONDecodeError, ValueError):
            provided = [p.strip() for p in stripped.split(";") if p.strip()]
        provided_set = {n.strip() for n in provided if isinstance(n, str) and n.strip()}
        grade_subjects = GradeGroupSubject.query.filter_by(grade_group_id=grade_id).all()
        for gs in grade_subjects:
            subject = Subject.query.get(gs.subject_id)
            if subject and subject.name not in provided_set:
                if not StudentSubjectExclusion.query.filter_by(
                        student_id=user_id, subject_id=gs.subject_id).first():
                    db.session.add(StudentSubjectExclusion(
                        student_id=user_id, subject_id=gs.subject_id))

    if mode == "delete":
        deleted = 0
        for row_data in valid_rows:
            user = User.query.filter_by(email=row_data[2], role="student").first()
            if user:
                _delete_student(user)
                deleted += 1
        db.session.commit()
        flash(_("%(deleted)d aluno(s) apagado(s).", deleted=deleted), "success")
        return redirect(url_for("admin.students"))

    if mode == "replace":
        for user in User.query.filter_by(role="student").filter(~User.email.in_(emails_in_file)).all():
            _delete_student(user)
        db.session.flush()

    added = 0
    for fn, ln, em, grade_name, subj_str, g1, g2 in valid_rows:
        if User.query.filter_by(email=em).first():
            continue
        if not has_names:
            continue
        grade = GradeGroup.query.filter_by(name=grade_name).first() if grade_name else None
        if not grade and grade_name:
            grade = GradeGroup(name=grade_name)
            db.session.add(grade)
            db.session.flush()
        user = User(email=em, role="student", first_name=fn, last_name=ln, preferred_language="en")
        db.session.add(user)
        db.session.flush()
        if grade:
            db.session.add(StudentProfile(user_id=user.id, grade_group_id=grade.id))
            db.session.flush()
            _apply_subject_exclusions(user.id, grade.id, subj_str)
        if g1:
            _link_guardian_to_student(user.id, g1)
        if g2:
            _link_guardian_to_student(user.id, g2)
        added += 1

    db.session.commit()
    flash(_("%(added)d aluno(s) importado(s).", added=added), "success")
    return redirect(url_for("admin.students"))


@admin_bp.route("/guardians/import", methods=["POST"])
@login_required
@admin_required
def import_guardians():
    mode = request.form.get("mode", "add")
    cols = set(_parse_cols(request.form.get("cols", "email,first_name,last_name,student1"), _GUARDIAN_COLS))
    has_names = "first_name" in cols and "last_name" in cols
    try:
        raw = _parse_csv_upload()
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for("admin.guardians"))

    emails_in_file, valid_rows = set(), []
    for row in raw:
        em = row.get("email", "").strip().lower()
        if not em:
            continue
        fn = row.get("first_name", "").strip() if "first_name" in cols else ""
        ln = row.get("last_name", "").strip()  if "last_name"  in cols else ""
        s1 = row.get("student1", "").strip()   if "student1"   in cols else ""
        s2 = row.get("student2", "").strip()   if "student2"   in cols else ""
        if has_names and mode != "delete" and (not fn or not ln):
            continue
        valid_rows.append((fn, ln, em, s1, s2))
        emails_in_file.add(em)

    def _delete_guardian(user):
        Booking.query.filter(Booking.booked_by_id == user.id).delete(synchronize_session=False)
        db.session.delete(user)

    if mode == "delete":
        deleted = 0
        for row_data in valid_rows:
            user = User.query.filter_by(email=row_data[2], role="guardian").first()
            if user:
                _delete_guardian(user)
                deleted += 1
        db.session.commit()
        flash(_("%(deleted)d responsável(eis) apagado(s).", deleted=deleted), "success")
        return redirect(url_for("admin.guardians"))

    if mode == "replace":
        for user in User.query.filter_by(role="guardian").filter(~User.email.in_(emails_in_file)).all():
            _delete_guardian(user)
        db.session.flush()

    added = 0
    for fn, ln, em, s1, s2 in valid_rows:
        guardian = User.query.filter_by(email=em).first()
        if not guardian:
            if not has_names:
                continue
            guardian = User(email=em, role="guardian", first_name=fn, last_name=ln, preferred_language="en")
            db.session.add(guardian)
            db.session.flush()
            added += 1
        if s1:
            _link_student_to_guardian(guardian.id, s1)
        if s2:
            _link_student_to_guardian(guardian.id, s2)

    db.session.commit()
    flash(_("%(added)d responsável(eis) importado(s).", added=added), "success")
    return redirect(url_for("admin.guardians"))


@admin_bp.route("/grades/matrix/import", methods=["POST"])
@login_required
@admin_required
def import_grades_matrix():
    """Import the grade × subject matrix CSV.
    Header row: grade, Subject1, Subject2, ...
    Data rows:  GradeName, 1, 0, ...
    Modes: add (create missing), replace (rebuild entire matrix), delete (delete listed grades).
    """
    mode = request.form.get("mode", "add")
    f = request.files.get("csv_file")
    if not f or not f.filename:
        flash(_("Nenhum arquivo enviado."), "danger")
        return redirect(url_for("admin.grades"))
    try:
        reader = csv.reader(io.StringIO(f.stream.read().decode("utf-8-sig")))
        all_rows = [r for r in reader if any(c.strip() for c in r)]
    except Exception as e:
        flash(_("Erro ao ler arquivo: %(err)s", err=str(e)), "danger")
        return redirect(url_for("admin.grades"))

    if not all_rows:
        flash(_("Arquivo vazio."), "danger")
        return redirect(url_for("admin.grades"))

    header       = [c.strip() for c in all_rows[0]]   # ["grade", "Matemática", ...]
    subject_names = header[1:]                          # skip the "grade" column
    data_rows     = all_rows[1:]
    grade_names_in_file = {r[0].strip() for r in data_rows if r and r[0].strip()}

    if mode == "delete":
        deleted = 0
        for name in grade_names_in_file:
            grade = GradeGroup.query.filter_by(name=name).first()
            if grade:
                db.session.delete(grade)
                deleted += 1
        db.session.commit()
        flash(_("%(deleted)d turma(s) apagada(s).", deleted=deleted), "success")
        return redirect(url_for("admin.grades"))

    if mode == "replace":
        # Remove all grade-subject links and teacher assignments, then prune obsolete rows
        GradeGroupSubject.query.delete(synchronize_session=False)
        TeacherSubjectGrade.query.delete(synchronize_session=False)
        for g in GradeGroup.query.filter(~GradeGroup.name.in_(grade_names_in_file)).all():
            db.session.delete(g)
        for s in Subject.query.filter(~Subject.name.in_(subject_names)).all():
            db.session.delete(s)
        db.session.flush()

    # Ensure subjects exist
    subject_objs = {}
    for name in subject_names:
        if not name:
            continue
        s = Subject.query.filter_by(name=name).first()
        if not s:
            s = Subject(name=name)
            db.session.add(s)
            db.session.flush()
        subject_objs[name] = s

    added_grades = added_links = 0
    for row in data_rows:
        grade_name = row[0].strip() if row else ""
        if not grade_name:
            continue
        grade = GradeGroup.query.filter_by(name=grade_name).first()
        if not grade:
            grade = GradeGroup(name=grade_name)
            db.session.add(grade)
            db.session.flush()
            added_grades += 1

        for i, subject_name in enumerate(subject_names):
            if not subject_name or subject_name not in subject_objs:
                continue
            cell = row[i + 1].strip() if i + 1 < len(row) else "0"
            is_active = cell in ("1", "true", "True", "TRUE", "yes", "Yes", "YES")
            subject = subject_objs[subject_name]
            existing = GradeGroupSubject.query.filter_by(
                grade_group_id=grade.id, subject_id=subject.id).first()
            if is_active and not existing:
                db.session.add(GradeGroupSubject(grade_group_id=grade.id, subject_id=subject.id))
                added_links += 1
            elif not is_active and existing and mode == "replace":
                db.session.delete(existing)

    db.session.commit()
    flash(_("%(g)d turma(s) e %(l)d vínculo(s) importado(s).", g=added_grades, l=added_links), "success")
    return redirect(url_for("admin.grades"))


# ── Teacher absence per event day ──────────────────────────────────────────────

@admin_bp.route("/events/<int:event_id>/days/<int:day_id>/absence/<int:teacher_id>/toggle", methods=["POST"])
@login_required
@admin_required
def toggle_teacher_absence(event_id, day_id, teacher_id):
    ConferenceDay.query.filter_by(id=day_id, event_id=event_id).first_or_404()
    existing = TeacherDayAbsence.query.filter_by(day_id=day_id, teacher_id=teacher_id).first()
    if existing:
        db.session.delete(existing)
    else:
        db.session.add(TeacherDayAbsence(day_id=day_id, teacher_id=teacher_id))
    db.session.commit()
    return jsonify({"absent": existing is not None})  # True = was absent, now present; False = was present, now absent


# ── Toggle day active/inactive ─────────────────────────────────────────────────

@admin_bp.route("/events/<int:event_id>/days/<int:day_id>/toggle-active", methods=["POST"])
@login_required
@admin_required
def toggle_day_active(event_id, day_id):
    day = ConferenceDay.query.filter_by(id=day_id, event_id=event_id).first_or_404()
    day.is_active = not day.is_active
    db.session.commit()
    return jsonify({"is_active": day.is_active})


def _get_grade_subjects_map():
    """Returns list of (GradeGroup, Subject) pairs defined via GradeGroupSubject."""
    rows = (GradeGroupSubject.query
            .join(GradeGroup, GradeGroupSubject.grade_group_id == GradeGroup.id)
            .join(Subject, GradeGroupSubject.subject_id == Subject.id)
            .order_by(GradeGroup.name, Subject.name)
            .all())
    # Group by grade for easy template iteration: {grade: [subject, ...]}
    from collections import defaultdict
    grouped = defaultdict(list)
    grade_objs = {}
    for gs in rows:
        grouped[gs.grade_group_id].append(gs.subject)
        grade_objs[gs.grade_group_id] = gs.grade_group
    return [(grade_objs[gid], subjects) for gid, subjects in grouped.items()]


def _save_teacher_subject_grades(teacher_id, form_data):
    for key in form_data:
        if key.startswith("sg_"):
            parts = key.split("_")
            if len(parts) == 3:
                try:
                    subject_id = int(parts[1])
                    grade_id = int(parts[2])
                    existing = TeacherSubjectGrade.query.filter_by(
                        teacher_id=teacher_id, subject_id=subject_id, grade_group_id=grade_id).first()
                    if not existing:
                        db.session.add(TeacherSubjectGrade(
                            teacher_id=teacher_id, subject_id=subject_id, grade_group_id=grade_id))
                except (ValueError, Exception):
                    pass


# ── Students ───────────────────────────────────────────────────────────────────

@admin_bp.route("/students")
@login_required
@admin_required
def students():
    grade_filter = request.args.get("grade_id", type=int)
    query = User.query.filter_by(role="student")
    if grade_filter:
        query = query.join(StudentProfile).filter(StudentProfile.grade_group_id == grade_filter)
    students = query.order_by(User.last_name).all()
    grades = GradeGroup.query.order_by(GradeGroup.name).all()
    return render_template("admin/students.html", students=students, grades=grades, grade_filter=grade_filter)


def _link_or_create_guardian_by_fields(student_id, email, first_name, last_name):
    """Link an existing guardian by email, or create a new one if name is provided."""
    email = email.strip().lower()
    if not email:
        return
    guardian = User.query.filter_by(email=email, role="guardian").first()
    if not guardian:
        first_name = first_name.strip()
        last_name  = last_name.strip()
        if not first_name or not last_name:
            return  # can't create without a name
        guardian = User(email=email, role="guardian", first_name=first_name,
                        last_name=last_name, preferred_language="en")
        db.session.add(guardian)
        db.session.flush()
    if not GuardianStudent.query.filter_by(guardian_id=guardian.id, student_id=student_id).first():
        db.session.add(GuardianStudent(guardian_id=guardian.id, student_id=student_id))


@admin_bp.route("/students/new")
@login_required
@admin_required
def new_student():
    """Create a blank draft student and go straight to the edit interface."""
    import uuid
    placeholder_email = f"__draft_{uuid.uuid4().hex}@draft.local"
    user = User(email=placeholder_email, role="student",
                first_name="", last_name="", preferred_language="en")
    db.session.add(user)
    db.session.commit()
    return redirect(url_for("admin.edit_student", id=user.id, is_new=1))


@admin_bp.route("/students/<int:id>/discard", methods=["POST"])
@login_required
@admin_required
def discard_student(id):
    """Delete a draft student that was never properly filled in."""
    user = User.query.filter_by(id=id, role="student").first_or_404()
    Booking.query.filter(
        (Booking.student_id == user.id) | (Booking.booked_by_id == user.id)
    ).delete(synchronize_session=False)
    db.session.delete(user)
    db.session.commit()
    return redirect(url_for("admin.students"))


@admin_bp.route("/students/<int:id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_student(id):
    user = User.query.filter_by(id=id, role="student").first_or_404()
    is_new = bool(request.args.get("is_new"))
    form = StudentForm(obj=user)
    form.grade_group_id.choices = [(g.id, g.name) for g in GradeGroup.query.order_by(GradeGroup.name).all()]

    if request.method == "GET":
        # For draft students, show blank fields instead of the placeholder email/name
        if is_new or user.email.startswith("__draft_"):
            form.email.data = ""
            form.first_name.data = ""
            form.last_name.data = ""
        if user.student_profile:
            form.grade_group_id.data = user.student_profile.grade_group_id

    if form.validate_on_submit():
        new_email = form.email.data.lower().strip()
        clash = User.query.filter(User.email == new_email, User.id != user.id).first()
        if clash:
            flash(_("Já existe um usuário com este e-mail."), "danger")
        else:
            user.first_name = form.first_name.data
            user.last_name  = form.last_name.data
            user.email      = new_email
            if user.student_profile:
                user.student_profile.grade_group_id = form.grade_group_id.data
            elif form.grade_group_id.data:
                sp = StudentProfile(user_id=user.id, grade_group_id=form.grade_group_id.data)
                db.session.add(sp)
            db.session.commit()
            flash(_("Aluno salvo."), "success")
            # Stay on the edit page (without is_new) so the user can continue editing
            return redirect(url_for("admin.edit_student", id=user.id))

    guardians = [gs.guardian for gs in user.student_guardians]
    already_linked_ids = {g.id for g in guardians}
    available_guardians = [g for g in
                           User.query.filter_by(role="guardian")
                               .order_by(User.last_name, User.first_name).all()
                           if g.id not in already_linked_ids]
    grade_subjects = []
    excluded_ids = set()
    if user.student_profile:
        grade_subjects = (GradeGroupSubject.query
                          .filter_by(grade_group_id=user.student_profile.grade_group_id)
                          .join(Subject).order_by(Subject.name).all())
        excluded_ids = {e.subject_id for e in
                        StudentSubjectExclusion.query.filter_by(student_id=user.id).all()}
    return render_template("admin/student_form.html", form=form, student=user,
                           is_new=is_new,
                           guardians=guardians, available_guardians=available_guardians,
                           grade_subjects=grade_subjects, excluded_ids=excluded_ids)


@admin_bp.route("/students/<int:student_id>/subjects/<int:subject_id>/toggle", methods=["POST"])
@login_required
@admin_required
def toggle_student_subject(student_id, subject_id):
    existing = StudentSubjectExclusion.query.filter_by(
        student_id=student_id, subject_id=subject_id).first()
    if existing:
        db.session.delete(existing)
        excluded = False
    else:
        db.session.add(StudentSubjectExclusion(student_id=student_id, subject_id=subject_id))
        excluded = True
    db.session.commit()
    return jsonify({"excluded": excluded})


@admin_bp.route("/students/<int:student_id>/add-guardian", methods=["POST"])
@login_required
@admin_required
def add_guardian_to_student(student_id):
    student = User.query.filter_by(id=student_id, role="student").first_or_404()
    existing_count = GuardianStudent.query.filter_by(student_id=student_id).count()
    if existing_count >= 2:
        flash(_("Este aluno já possui 2 responsáveis vinculados."), "warning")
        return redirect(url_for("admin.edit_student", id=student_id))

    email = request.form.get("guardian_email", "").lower().strip()
    guardian = User.query.filter_by(email=email, role="guardian").first()

    if guardian:
        if GuardianStudent.query.filter_by(guardian_id=guardian.id, student_id=student_id).first():
            flash(_("Responsável já vinculado."), "info")
        else:
            db.session.add(GuardianStudent(guardian_id=guardian.id, student_id=student_id))
            db.session.commit()
            flash(_("Responsável vinculado."), "success")
    else:
        first = request.form.get("guardian_first_name", "").strip()
        last = request.form.get("guardian_last_name", "").strip()
        if not first or not last:
            flash(_("Informe nome e sobrenome para criar um novo responsável."), "danger")
            return redirect(url_for("admin.edit_student", id=student_id))
        if User.query.filter_by(email=email).first():
            flash(_("E-mail já está em uso."), "danger")
            return redirect(url_for("admin.edit_student", id=student_id))
        guardian = User(email=email, role="guardian", first_name=first, last_name=last, preferred_language="en")
        db.session.add(guardian)
        db.session.flush()
        db.session.add(GuardianStudent(guardian_id=guardian.id, student_id=student_id))
        token = generate_token(guardian.email, salt="invite")
        guardian.invite_token = token
        guardian.invite_sent_at = datetime.utcnow()
        db.session.commit()
        try:
            send_invite_email(guardian, token)
            flash(_("Responsável criado e convite enviado para %(email)s.", email=email), "success")
        except Exception as e:
            flash(_("Responsável criado, mas falha no e-mail: %(err)s", err=str(e)), "warning")

    return redirect(url_for("admin.edit_student", id=student_id))


@admin_bp.route("/students/<int:student_id>/remove-guardian/<int:guardian_id>", methods=["POST"])
@login_required
@admin_required
def remove_guardian_from_student(student_id, guardian_id):
    link = GuardianStudent.query.filter_by(guardian_id=guardian_id, student_id=student_id).first_or_404()
    db.session.delete(link)
    db.session.commit()
    flash(_("Responsável removido."), "success")
    return redirect(url_for("admin.edit_student", id=student_id))


@admin_bp.route("/students/<int:student_id>/guardians/<int:guardian_id>/update", methods=["POST"])
@login_required
@admin_required
def update_guardian_from_student(student_id, guardian_id):
    """Edit a guardian's profile and return to the student edit page."""
    guardian = User.query.filter_by(id=guardian_id, role="guardian").first_or_404()
    first_name = request.form.get("first_name", "").strip()
    last_name  = request.form.get("last_name", "").strip()
    email      = request.form.get("email", "").lower().strip()
    if not first_name or not last_name or not email:
        flash(_("Nome, sobrenome e e-mail são obrigatórios."), "danger")
        return redirect(url_for("admin.edit_student", id=student_id))
    clash = User.query.filter(User.email == email, User.id != guardian_id).first()
    if clash:
        flash(_("Já existe um usuário com este e-mail."), "danger")
        return redirect(url_for("admin.edit_student", id=student_id))
    guardian.first_name = first_name
    guardian.last_name  = last_name
    guardian.email      = email
    db.session.commit()
    flash(_("Responsável atualizado."), "success")
    return redirect(url_for("admin.edit_student", id=student_id))


# ── Events ─────────────────────────────────────────────────────────────────────

@admin_bp.route("/events")
@login_required
@admin_required
def events():
    all_events = ConferenceEvent.query.order_by(ConferenceEvent.created_at.desc()).all()
    return render_template("admin/events.html", events=all_events)


@admin_bp.route("/events/new", methods=["GET", "POST"])
@login_required
@admin_required
def new_event():
    form = ConferenceEventForm()
    if form.validate_on_submit():
        event = ConferenceEvent(
            name=form.name.data,
            student_booking_allowed=form.student_booking_allowed.data,
            cancel_deadline_hours=form.cancel_deadline_hours.data,
        )
        db.session.add(event)
        db.session.flush()
        _save_event_days_and_slots(event, form)
        db.session.commit()
        flash(_("Evento criado e horários gerados."), "success")
        return redirect(url_for("admin.events"))
    return render_template("admin/event_form.html", form=form, event=None)


@admin_bp.route("/events/<int:id>/check-conflicts")
@login_required
@admin_required
def event_check_conflicts(id):
    """Return days that have bookings and are about to be removed from the event."""
    from datetime import date as date_type
    event = ConferenceEvent.query.get_or_404(id)
    form_dates = set()
    for d in request.args.getlist('dates[]'):
        try:
            from datetime import datetime as dt
            form_dates.add(dt.strptime(d, '%Y-%m-%d').date())
        except (ValueError, TypeError):
            pass

    conflicts = []
    for day in event.days:
        if day.date in form_dates:
            continue  # day is staying — no conflict
        has_bookings = db.session.query(Booking).join(Slot).filter(
            Slot.day_id == day.id,
            Booking.cancelled_at == None
        ).first() is not None
        if has_bookings:
            count = db.session.query(Booking).join(Slot).filter(
                Slot.day_id == day.id,
                Booking.cancelled_at == None
            ).count()
            conflicts.append({
                'date': day.date.strftime('%d/%m/%Y'),
                'bookings': count,
            })
    return jsonify({'conflicts': conflicts})


@admin_bp.route("/events/<int:id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_event(id):
    event = ConferenceEvent.query.get_or_404(id)
    form = ConferenceEventForm(obj=event)
    if form.validate_on_submit():
        event.name = form.name.data
        event.student_booking_allowed = form.student_booking_allowed.data
        event.cancel_deadline_hours = form.cancel_deadline_hours.data

        # Map existing days by date
        existing_by_date = {day.date: day for day in event.days}
        form_dates = {fd.date.data for fd in form.days if fd.date.data}
        teachers = User.query.filter_by(role="teacher", is_active=True).all()
        protected = []  # days with bookings that cannot be removed

        # conflict_action: 'keep' = preserve bookings, 'remove_all' = force delete
        conflict_action = request.form.get('conflict_action', 'keep')

        # ── Remove days that disappeared from the form ──────────────────
        for date, day in list(existing_by_date.items()):
            if date not in form_dates:
                has_bookings = db.session.query(Booking).join(Slot).filter(
                    Slot.day_id == day.id,
                    Booking.cancelled_at == None
                ).first() is not None

                if has_bookings and conflict_action == 'keep':
                    protected.append(day.date.strftime('%d/%m/%Y'))
                else:
                    # 'remove_all': manually delete bookings first to bypass cascade check
                    if has_bookings:
                        for slot in day.slots:
                            if slot.booking:
                                db.session.delete(slot.booking)
                    db.session.delete(day)

        db.session.flush()

        # ── Update existing days / add new ones ─────────────────────────
        for fd in form.days:
            if not fd.date.data:
                continue
            date = fd.date.data

            if date in existing_by_date:
                # Update metadata
                day = existing_by_date[date]
                day.start_time            = fd.start_time.data
                day.end_time              = fd.end_time.data
                day.slot_duration_minutes = fd.slot_duration_minutes.data
                day.break_minutes         = fd.break_minutes.data or 0

                # Regenerate slots only when no bookings exist for this day
                has_bookings = db.session.query(Booking).join(Slot).filter(
                    Slot.day_id == day.id,
                    Booking.cancelled_at == None
                ).first() is not None
                if not has_bookings:
                    for s in list(day.slots):
                        db.session.delete(s)
                    db.session.flush()
                    db.session.add_all(generate_slots_for_day(day, teachers))
            else:
                # Brand-new day
                day = ConferenceDay(
                    event_id=event.id,
                    date=date,
                    start_time=fd.start_time.data,
                    end_time=fd.end_time.data,
                    slot_duration_minutes=fd.slot_duration_minutes.data,
                    break_minutes=fd.break_minutes.data or 0,
                )
                db.session.add(day)
                db.session.flush()
                db.session.add_all(generate_slots_for_day(day, teachers))

        db.session.commit()

        if protected:
            flash(
                _("Evento atualizado. O(s) dia(s) %(dates)s não foram removidos pois têm agendamentos confirmados.",
                  dates=', '.join(protected)),
                "warning"
            )
        else:
            flash(_("Evento atualizado."), "success")
        return redirect(url_for("admin.events"))
    all_teachers = (User.query.filter_by(role="teacher", is_active=True)
                    .order_by(User.last_name, User.first_name).all())
    absent_set = {(a.day_id, a.teacher_id)
                  for a in TeacherDayAbsence.query
                  .join(ConferenceDay, TeacherDayAbsence.day_id == ConferenceDay.id)
                  .filter(ConferenceDay.event_id == id).all()}
    return render_template("admin/event_form.html", form=form, event=event,
                           all_teachers=all_teachers, absent_set=absent_set)


@admin_bp.route("/events/<int:id>/publish", methods=["POST"])
@login_required
@admin_required
def publish_event(id):
    event = ConferenceEvent.query.get_or_404(id)
    event.status = "published"
    db.session.commit()
    flash(_("Evento publicado."), "success")
    return redirect(url_for("admin.events"))


@admin_bp.route("/events/<int:id>/close", methods=["POST"])
@login_required
@admin_required
def close_event(id):
    event = ConferenceEvent.query.get_or_404(id)
    event.status = "closed"
    db.session.commit()
    flash(_("Evento encerrado."), "success")
    return redirect(url_for("admin.events"))


@admin_bp.route("/events/<int:id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_event(id):
    event = ConferenceEvent.query.get_or_404(id)
    db.session.delete(event)
    db.session.commit()
    flash(_("Evento excluído."), "success")
    return redirect(url_for("admin.events"))


@admin_bp.route("/events/<int:id>/bookings")
@login_required
@admin_required
def event_bookings(id):
    event = ConferenceEvent.query.get_or_404(id)
    bookings = (Booking.query
                .join(Slot).join(ConferenceDay)
                .filter(ConferenceDay.event_id == id, Booking.cancelled_at == None)
                .order_by(Slot.start_datetime)
                .all())
    return render_template("admin/event_bookings.html", event=event, bookings=bookings)


def _save_event_days_and_slots(event, form):
    teachers = User.query.filter_by(role="teacher", is_active=True).all()
    for day_data in form.days:
        if not day_data.date.data:
            continue
        day = ConferenceDay(
            event_id=event.id,
            date=day_data.date.data,
            start_time=day_data.start_time.data,
            end_time=day_data.end_time.data,
            slot_duration_minutes=day_data.slot_duration_minutes.data,
            break_minutes=day_data.break_minutes.data or 0,
        )
        db.session.add(day)
        db.session.flush()
        slots = generate_slots_for_day(day, teachers)
        db.session.add_all(slots)


# ── Notifications ──────────────────────────────────────────────────────────────

@admin_bp.route("/events/<int:event_id>/notify", methods=["GET", "POST"])
@login_required
@admin_required
def notify(event_id):
    event = ConferenceEvent.query.get_or_404(event_id)
    form = NotifyForm()
    grade_choices = [(0, _("Todas as turmas"))] + [(g.id, g.name) for g in GradeGroup.query.order_by(GradeGroup.name).all()]
    form.grade_group_id.choices = grade_choices

    if form.validate_on_submit():
        guardians = _get_notify_recipients(form, event_id)
        sent = 0
        for guardian in guardians:
            token = None
            if not guardian.has_password():
                token = generate_token(guardian.email, salt="invite")
                guardian.invite_token = token
                guardian.invite_sent_at = datetime.utcnow()
            try:
                send_conference_info_email(guardian, event, token)
                db.session.add(EmailNotification(
                    event_id=event_id,
                    recipient_id=guardian.id,
                    type="conference_info",
                ))
                sent += 1
            except Exception:
                pass
        db.session.commit()
        flash(_("%(count)s e-mails enviados.", count=sent), "success")
        return redirect(url_for("admin.events"))

    preview_count = 0
    if request.method == "POST":
        preview_count = len(_get_notify_recipients(form, event_id))

    return render_template("admin/notify.html", form=form, event=event, preview_count=preview_count)


def _get_notify_recipients(form, event_id):
    query = User.query.filter_by(role="guardian", is_active=True)
    guardians = query.all()
    result = []
    for g in guardians:
        if form.all_guardians.data:
            result.append(g)
            continue
        if form.not_yet_notified.data:
            already = EmailNotification.query.filter_by(recipient_id=g.id, event_id=event_id).first()
            if not already:
                result.append(g)
                continue
        if form.multiple_children.data:
            count = GuardianStudent.query.filter_by(guardian_id=g.id).count()
            if count >= 2:
                result.append(g)
                continue
        if form.grade_group_id.data:
            for gs in g.guardian_students:
                sp = StudentProfile.query.filter_by(user_id=gs.student_id).first()
                if sp and sp.grade_group_id == form.grade_group_id.data:
                    result.append(g)
                    break
    seen = set()
    return [g for g in result if not (g.id in seen or seen.add(g.id))]
