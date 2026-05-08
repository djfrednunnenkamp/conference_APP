from functools import wraps
from datetime import datetime, date as date_type
import csv
import io
import json
import re
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, jsonify, Response
from flask_login import login_required, current_user
from flask_babel import _
from app.extensions import db, bcrypt
from app.models import (User, TeacherProfile, Subject, GradeGroup, GradeGroupSubject,
                        TeacherSubjectGrade, StudentProfile, GuardianStudent,
                        ConferenceEvent, ConferenceDay, Slot, Booking, EmailNotification,
                        TeacherDayAbsence, StudentSubjectExclusion, EventReminder,
                        Division, TeacherDayOverride, EventSector, EventSectorTeacher,
                        TeacherBreak, SecretaryDivision)
from app.admin.forms import (GradeGroupForm, SubjectForm, TeacherForm, StudentForm,
                              GuardianForm, AdminForm, ConferenceEventForm,
                              ConferenceEventSimpleForm, NotifyForm)
from app.utils import (generate_token, send_invite_email, send_conference_info_email,
                       send_reset_email, generate_slots_for_day,
                       generate_slots_for_sector_day,
                       send_teacher_absent_email, send_booking_reminder_email)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            abort(403)
        return f(*args, **kwargs)
    return decorated


def secretary_or_admin_required(f):
    """Allow access to both admins and secretaries."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ('admin', 'secretary'):
            abort(403)
        return f(*args, **kwargs)
    return decorated


def get_secretary_division_ids():
    """Return set of division_ids the current secretary manages. Empty set for admins (= all)."""
    if current_user.role == 'secretary':
        return {sd.division_id for sd in SecretaryDivision.query.filter_by(secretary_id=current_user.id).all()}
    return set()  # empty = no restriction = admin


# ── Dashboard ─────────────────────────────────────────────────────────────────

@admin_bp.route("/")
@login_required
@secretary_or_admin_required
def dashboard():
    total_students = User.query.filter_by(role="student").count()
    total_teachers = User.query.filter_by(role="teacher").count()
    total_guardians = User.query.filter_by(role="guardian").count()
    active_events = ConferenceEvent.query.filter_by(status="published").order_by(ConferenceEvent.name).all()
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


# ── Divisions ──────────────────────────────────────────────────────────────────

@admin_bp.route("/divisions")
@login_required
@secretary_or_admin_required
def divisions():
    from app import _natsort_key
    all_divisions = Division.query.order_by(Division.order, Division.name).all()
    if current_user.role == 'secretary':
        sec_div_ids = get_secretary_division_ids()
        all_divisions = [d for d in all_divisions if d.id in sec_div_ids]
    active_pairs  = {(gs.grade_group_id, gs.subject_id)
                     for gs in GradeGroupSubject.query.all()}

    # Build JS-serialisable data for the subject panel modal
    sectors_js = []
    for div in all_divisions:
        subjects_sorted = sorted(div.subjects, key=lambda s: _natsort_key(s.name))
        # Grades sorted by explicit order field, then name as tiebreaker
        grades_ordered = sorted(div.grade_groups, key=lambda g: (g.order, g.name))
        grades_js = {}
        for g in grades_ordered:
            grades_js[str(g.id)] = {
                "name": g.name,
                "active": [s.id for s in div.subjects if (g.id, s.id) in active_pairs],
            }
        sectors_js.append({
            "id": div.id,
            "name": div.name,
            "subjects": [{"id": s.id, "name": s.name} for s in subjects_sorted],
            "grades": grades_js,
        })

    return render_template("admin/divisions.html",
                           divisions=all_divisions,
                           active_pairs=active_pairs,
                           sectors_js=sectors_js)


@admin_bp.route("/divisions/new", methods=["POST"])
@login_required
@admin_required
def new_division():
    name = request.form.get("name", "").strip()
    if not name:
        flash(_("Nome obrigatório."), "warning")
    elif Division.query.filter_by(name=name).first():
        flash(_("Setor já existe."), "warning")
    else:
        max_order = db.session.query(db.func.max(Division.order)).scalar() or 0
        db.session.add(Division(name=name, order=max_order + 1))
        db.session.commit()
        flash(_("Setor criado."), "success")
    return redirect(url_for("admin.divisions"))


@admin_bp.route("/divisions/<int:id>/edit", methods=["POST"])
@login_required
@admin_required
def edit_division(id):
    division = Division.query.get_or_404(id)
    name = request.form.get("name", "").strip()
    if not name:
        flash(_("Nome obrigatório."), "warning")
    elif Division.query.filter(Division.name == name, Division.id != id).first():
        flash(_("Já existe um setor com esse nome."), "warning")
    else:
        division.name = name
        db.session.commit()
        flash(_("Setor atualizado."), "success")
    return redirect(url_for("admin.divisions"))


@admin_bp.route("/divisions/<int:id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_division(id):
    division = Division.query.get_or_404(id)
    # Unassign grade groups before deleting
    GradeGroup.query.filter_by(division_id=id).update({"division_id": None})
    db.session.delete(division)
    db.session.commit()
    flash(_("Setor excluído."), "success")
    return redirect(url_for("admin.divisions"))


@admin_bp.route("/divisions/reorder", methods=["POST"])
@login_required
@admin_required
def reorder_divisions():
    """Accepts JSON list of {id, order} and updates order values."""
    data = request.get_json(silent=True) or []
    for item in data:
        Division.query.filter_by(id=item["id"]).update({"order": item["order"]})
    db.session.commit()
    return jsonify({"ok": True})


@admin_bp.route("/divisions/<int:id>/move/<direction>", methods=["POST"])
@login_required
@admin_required
def move_division(id, direction):
    """Swap order values with the adjacent division (up or down)."""
    all_divs = Division.query.order_by(Division.order, Division.id).all()
    idx = next((i for i, d in enumerate(all_divs) if d.id == id), None)
    if idx is None:
        return redirect(url_for("admin.divisions"))
    swap_idx = idx - 1 if direction == "up" else idx + 1
    if 0 <= swap_idx < len(all_divs):
        a, b = all_divs[idx], all_divs[swap_idx]
        a.order, b.order = b.order, a.order
        db.session.commit()
    return redirect(url_for("admin.divisions"))


@admin_bp.route("/grades/<int:grade_id>/move/<direction>", methods=["POST"])
@login_required
@admin_required
def move_grade(grade_id, direction):
    """Swap order values with the adjacent grade within the same division."""
    grade = GradeGroup.query.get_or_404(grade_id)
    if grade.division_id is None:
        return redirect(url_for("admin.divisions"))
    siblings = (GradeGroup.query
                .filter_by(division_id=grade.division_id)
                .order_by(GradeGroup.order, GradeGroup.id)
                .all())
    idx = next((i for i, g in enumerate(siblings) if g.id == grade_id), None)
    if idx is None:
        return redirect(url_for("admin.divisions"))
    swap_idx = idx - 1 if direction == "up" else idx + 1
    swapped_id = None
    if 0 <= swap_idx < len(siblings):
        a, b = siblings[idx], siblings[swap_idx]
        a.order, b.order = b.order, a.order
        db.session.commit()
        swapped_id = b.id
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({"ok": True, "swapped_id": swapped_id})
    return redirect(url_for("admin.divisions"))


@admin_bp.route("/grades/<int:grade_id>/set-division", methods=["POST"])
@login_required
@admin_required
def set_grade_division(grade_id):
    """AJAX: assign or unassign a grade group to a division."""
    grade = GradeGroup.query.get_or_404(grade_id)
    division_id = request.get_json(silent=True, force=True).get("division_id")
    grade.division_id = int(division_id) if division_id else None
    db.session.commit()
    return jsonify({"ok": True, "division_id": grade.division_id})


@admin_bp.route("/grades/<int:id>/rename", methods=["POST"])
@login_required
@admin_required
def rename_grade(id):
    grade = GradeGroup.query.get_or_404(id)
    data  = request.get_json(silent=True) or {}
    name  = data.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Nome obrigatório"}), 400
    if GradeGroup.query.filter(GradeGroup.name == name, GradeGroup.id != id).first():
        return jsonify({"ok": False, "error": "Já existe uma turma com esse nome"}), 409
    grade.name = name
    db.session.commit()
    return jsonify({"ok": True, "name": grade.name})


@admin_bp.route("/subjects/<int:id>/rename", methods=["POST"])
@login_required
@secretary_or_admin_required
def rename_subject(id):
    subject     = Subject.query.get_or_404(id)
    data        = request.get_json(silent=True) or {}
    name        = data.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Nome obrigatório"}), 400
    if Subject.query.filter(Subject.name == name,
                            Subject.division_id == subject.division_id,
                            Subject.id != id).first():
        return jsonify({"ok": False, "error": "Já existe uma matéria com esse nome neste setor"}), 409
    subject.name = name
    db.session.commit()
    return jsonify({"ok": True, "name": subject.name})


@admin_bp.route("/divisions/<int:division_id>/grades/new", methods=["POST"])
@login_required
@admin_required
def new_division_grade(division_id):
    """Create a new grade group and assign it directly to this division."""
    Division.query.get_or_404(division_id)
    name = request.form.get("name", "").strip()
    if not name:
        flash(_("Nome obrigatório."), "warning")
    elif GradeGroup.query.filter_by(name=name).first():
        flash(_("Turma já existe."), "warning")
    else:
        max_order = (db.session.query(db.func.max(GradeGroup.order))
                     .filter_by(division_id=division_id).scalar() or 0)
        db.session.add(GradeGroup(name=name, division_id=division_id,
                                  order=max_order + 1))
        db.session.commit()
        flash(_("Turma adicionada."), "success")
    return redirect(url_for("admin.divisions"))


@admin_bp.route("/divisions/<int:division_id>/subjects/new", methods=["POST"])
@login_required
@secretary_or_admin_required
def new_division_subject(division_id):
    """Create a new subject inside a division."""
    Division.query.get_or_404(division_id)
    is_ajax = request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest"
    payload  = request.get_json(silent=True) or {}
    name     = (payload.get("name") or request.form.get("name", "")).strip()
    if not name:
        if is_ajax:
            return jsonify({"error": _("Nome obrigatório.")}), 400
        flash(_("Nome obrigatório."), "warning")
    elif Subject.query.filter_by(name=name, division_id=division_id).first():
        if is_ajax:
            return jsonify({"error": _("Matéria já existe neste setor.")}), 409
        flash(_("Matéria já existe neste setor."), "warning")
    else:
        subject = Subject(name=name, division_id=division_id)
        db.session.add(subject)
        db.session.commit()
        if is_ajax:
            return jsonify({"id": subject.id, "name": subject.name})
        flash(_("Matéria adicionada."), "success")
    return redirect(url_for("admin.divisions"))


@admin_bp.route("/subjects/<int:id>/delete", methods=["POST"])
@login_required
@secretary_or_admin_required
def delete_subject_by_id(id):
    """Delete a subject (called from divisions page)."""
    is_ajax = request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest"
    subject = Subject.query.get_or_404(id)
    GradeGroupSubject.query.filter_by(subject_id=id).delete()
    db.session.delete(subject)
    db.session.commit()
    if is_ajax:
        return jsonify({"ok": True})
    flash(_("Matéria excluída."), "success")
    return redirect(url_for("admin.divisions"))


# ── Grade Groups ───────────────────────────────────────────────────────────────

@admin_bp.route("/grades", methods=["GET", "POST"])
@login_required
@admin_required
def grades():
    # Unified page is now at /divisions
    return redirect(url_for("admin.divisions"))
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

    all_divisions = Division.query.order_by(Division.order, Division.name).all()

    # Division filter from query param
    # "0" = items with no division; None = show all
    raw_div = request.args.get("division_id")
    if raw_div == "0":
        selected_division_id = 0
        grades_q   = GradeGroup.query.filter_by(division_id=None)
        subjects_q = Subject.query.filter_by(division_id=None)
    elif raw_div and raw_div.isdigit():
        selected_division_id = int(raw_div)
        grades_q   = GradeGroup.query.filter_by(division_id=selected_division_id)
        subjects_q = Subject.query.filter_by(division_id=selected_division_id)
    else:
        selected_division_id = None
        grades_q   = GradeGroup.query
        subjects_q = Subject.query

    from app import _natsort_key
    all_grades   = sorted(grades_q.all(),   key=lambda g: _natsort_key(g.name), reverse=True)
    all_subjects = sorted(subjects_q.all(), key=lambda s: _natsort_key(s.name))

    # Only load active pairs for the visible grades & subjects
    visible_grade_ids   = {g.id for g in all_grades}
    visible_subject_ids = {s.id for s in all_subjects}
    active = {
        (gs.grade_group_id, gs.subject_id)
        for gs in GradeGroupSubject.query.all()
        if gs.grade_group_id in visible_grade_ids
        and gs.subject_id in visible_subject_ids
    }

    total_grade_count = GradeGroup.query.count()
    unassigned_count  = GradeGroup.query.filter_by(division_id=None).count()

    return render_template("admin/grades.html",
                           grade_form=grade_form, subject_form=subject_form,
                           grades=all_grades, all_subjects=all_subjects,
                           active=active, divisions=all_divisions,
                           selected_division_id=selected_division_id,
                           total_grade_count=total_grade_count,
                           unassigned_count=unassigned_count)


@admin_bp.route("/grades/<int:grade_id>/subjects/<int:subject_id>/toggle", methods=["POST"])
@login_required
@secretary_or_admin_required
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
        active = False
    else:
        db.session.add(GradeGroupSubject(grade_group_id=grade_id, subject_id=subject_id))
        active = True
    db.session.commit()
    # JSON for the new AJAX-based unified page
    if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"active": active})
    # Legacy form-POST redirect (grades matrix page still works if accessed directly)
    division_id = request.form.get("division_id")
    if division_id:
        return redirect(url_for("admin.divisions"))
    return redirect(url_for("admin.divisions"))


@admin_bp.route("/grades/<int:id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_grade(id):
    grade = GradeGroup.query.get_or_404(id)

    # Block if students are assigned — grade_group_id is NOT NULL on student_profile
    student_count = len(grade.student_profiles)
    if student_count:
        flash(
            _('Não é possível excluir a turma "%(name)s" pois há %(n)s aluno(s) vinculado(s).'
              ' Reatribua os alunos antes de excluir.',
              name=grade.name, n=student_count),
            "warning",
        )
        return redirect(url_for("admin.divisions"))

    # Remove teacher–subject–grade assignments first (NOT NULL FK, no cascade)
    TeacherSubjectGrade.query.filter_by(grade_group_id=id).delete(synchronize_session=False)

    # GradeGroupSubject has cascade="all, delete-orphan" on the relationship,
    # so those are handled automatically when we delete the grade.
    db.session.delete(grade)
    db.session.commit()
    flash(_("Turma excluída."), "success")
    return redirect(url_for("admin.divisions"))


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
@secretary_or_admin_required
def teachers():
    grade_filter = request.args.get("grade_id", type=int)
    query = User.query.filter_by(role="teacher")
    if grade_filter:
        query = query.join(TeacherProfile).join(TeacherSubjectGrade,
            TeacherSubjectGrade.teacher_id == User.id).filter(
            TeacherSubjectGrade.grade_group_id == grade_filter)
    teachers_list = query.order_by(User.last_name, User.first_name).all()
    from app import _natsort_key
    grades = sorted(GradeGroup.query.all(), key=lambda g: _natsort_key(g.name), reverse=True)
    grade_subjects_by_sector = _get_grade_subjects_by_sector()
    # Per-teacher current assignments as [[grade_id, subject_id], ...] for JS
    teacher_sgs = {
        t.id: [[sg.grade_group_id, sg.subject_id] for sg in t.teacher_profile.subject_grades]
        if t.teacher_profile else []
        for t in teachers_list
    }
    return render_template("admin/teachers.html",
                           teachers=teachers_list,
                           grades=grades,
                           grade_filter=grade_filter,
                           grade_subjects_by_sector=grade_subjects_by_sector,
                           sg_data_js=_sg_data_js(grade_subjects_by_sector),
                           teacher_sgs=teacher_sgs)


@admin_bp.route("/teachers/new", methods=["GET", "POST"])
@login_required
@admin_required
def new_teacher():
    form = TeacherForm()
    grade_subjects_by_sector = _get_grade_subjects_by_sector()
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
            db.session.commit()
            flash(_("Professor criado com sucesso."), "success")
            return redirect(url_for("admin.teachers"))
    return render_template("admin/teacher_form.html",
                           form=form,
                           grade_subjects_by_sector=grade_subjects_by_sector,
                           sg_data_js=_sg_data_js(grade_subjects_by_sector),
                           existing_sgs=set(),
                           teacher=None)


@admin_bp.route("/teachers/<int:id>/edit", methods=["GET", "POST"])
@login_required
@secretary_or_admin_required
def edit_teacher(id):
    user = User.query.filter_by(id=id, role="teacher").first_or_404()
    form = TeacherForm(obj=user)
    grade_subjects_by_sector = _get_grade_subjects_by_sector()
    existing_sgs = {(t.grade_group_id, t.subject_id)
                    for t in TeacherSubjectGrade.query.filter_by(teacher_id=user.id).all()}
    if form.validate_on_submit():
        user.first_name = form.first_name.data
        user.last_name = form.last_name.data
        user.email = form.email.data.lower().strip()
        TeacherSubjectGrade.query.filter_by(teacher_id=user.id).delete()
        _save_teacher_subject_grades(user.id, request.form)
        db.session.commit()
        flash(_("Professor atualizado."), "success")
        return redirect(url_for("admin.teachers"))
    past_conferences = _past_conferences_for_teacher(user.id)
    return render_template("admin/teacher_form.html",
                           form=form,
                           grade_subjects_by_sector=grade_subjects_by_sector,
                           sg_data_js=_sg_data_js(grade_subjects_by_sector),
                           existing_sgs=existing_sgs,
                           teacher=user,
                           past_conferences=past_conferences)


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
        # 1. Collect slot IDs booked by/for this student so we can free them
        booked_slot_ids = [b.slot_id for b in Booking.query.filter(
            (Booking.student_id == user.id) | (Booking.booked_by_id == user.id)
        ).all()]
        # 2. Delete the bookings
        Booking.query.filter(
            (Booking.student_id == user.id) | (Booking.booked_by_id == user.id)
        ).delete(synchronize_session=False)
        # 3. Mark those slots as available again
        if booked_slot_ids:
            Slot.query.filter(Slot.id.in_(booked_slot_ids)).update(
                {"is_booked": False}, synchronize_session=False)
        db.session.delete(user)
        db.session.commit()
        flash(_("Aluno excluído."), "success")
    except Exception as e:
        db.session.rollback()
        flash(_("Erro ao excluir aluno: %(err)s", err=str(e)), "danger")
    return redirect(url_for("admin.students"))


@admin_bp.route("/users/<int:user_id>/send-reset", methods=["POST"])
@login_required
@secretary_or_admin_required
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
@secretary_or_admin_required
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
    past_conferences = _past_conferences_for_guardian(user.id)
    return render_template("admin/guardian_form.html", form=form, guardian=user,
                           past_conferences=past_conferences)


@admin_bp.route("/guardians/new", methods=["POST"])
@login_required
@admin_required
def new_guardian():
    first_name = request.form.get("first_name", "").strip()
    last_name  = request.form.get("last_name",  "").strip()
    email      = request.form.get("email",       "").strip().lower()
    if not first_name or not last_name or not email:
        flash(_("Preencha todos os campos."), "danger")
        return redirect(url_for("admin.guardians"))
    if User.query.filter_by(email=email).first():
        flash(_("Já existe um usuário com este e-mail."), "danger")
        return redirect(url_for("admin.guardians"))
    user = User(email=email, role="guardian", first_name=first_name,
                last_name=last_name, preferred_language="en")
    db.session.add(user)
    db.session.commit()
    flash(_("Responsável criado com sucesso."), "success")
    return redirect(url_for("admin.guardians"))


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
    sec_list   = (User.query.filter_by(role="secretary")
                  .order_by(User.last_name, User.first_name).all())
    divisions  = Division.query.order_by(Division.order, Division.name).all()
    div_ids_by_sec = {s.id: {sd.division_id for sd in SecretaryDivision.query.filter_by(secretary_id=s.id).all()}
                      for s in sec_list}
    return render_template("admin/admins.html", admins=admin_list,
                           secretaries=sec_list, divisions=divisions,
                           div_ids_by_sec=div_ids_by_sec)


@admin_bp.route("/admins/inline-add", methods=["POST"])
@login_required
@admin_required
def admins_inline_add():
    email = request.form.get("email", "").strip().lower()
    first = request.form.get("first_name", "").strip()
    last  = request.form.get("last_name", "").strip()
    if not email or not first or not last:
        flash(_("Preencha todos os campos."), "danger")
    elif User.query.filter_by(email=email).first():
        flash(_("E-mail já está em uso."), "danger")
    else:
        user = User(email=email, role="admin", first_name=first, last_name=last, preferred_language="pt")
        db.session.add(user)
        db.session.commit()
        flash(_("Administrador criado com sucesso."), "success")
    return redirect(url_for("admin.admins"))


@admin_bp.route("/secretaries/inline-add", methods=["POST"])
@login_required
@admin_required
def secretaries_inline_add():
    email   = request.form.get("email", "").strip().lower()
    first   = request.form.get("first_name", "").strip()
    last    = request.form.get("last_name", "").strip()
    div_ids = [int(x) for x in request.form.getlist("division_ids") if x.isdigit()]
    if not email or not first or not last:
        flash(_("Preencha todos os campos."), "danger")
    elif User.query.filter_by(email=email).first():
        flash(_("E-mail já está em uso."), "danger")
    else:
        user = User(email=email, role="secretary", first_name=first, last_name=last, preferred_language="pt")
        db.session.add(user)
        db.session.flush()
        for did in div_ids:
            db.session.add(SecretaryDivision(secretary_id=user.id, division_id=did))
        db.session.commit()
        flash(_("Secretária criada com sucesso."), "success")
    return redirect(url_for("admin.admins"))


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


@admin_bp.route("/admins/<int:id>/edit-inline", methods=["POST"])
@login_required
@admin_required
def edit_admin_inline(id):
    user = User.query.filter_by(id=id, role="admin").first_or_404()
    email = request.form.get("email", "").strip().lower()
    first = request.form.get("first_name", "").strip()
    last  = request.form.get("last_name", "").strip()
    if not email or not first or not last:
        flash(_("Preencha todos os campos."), "danger")
    else:
        clash = User.query.filter(User.email == email, User.id != user.id).first()
        if clash:
            flash(_("E-mail já está em uso."), "danger")
        else:
            user.first_name = first
            user.last_name  = last
            user.email      = email
            db.session.commit()
            flash(_("Administrador atualizado."), "success")
    return redirect(url_for("admin.admins"))


@admin_bp.route("/secretaries/<int:id>/edit-inline", methods=["POST"])
@login_required
@admin_required
def edit_secretary_inline(id):
    user = User.query.filter_by(id=id, role='secretary').first_or_404()
    email = request.form.get("email", "").strip().lower()
    first = request.form.get("first_name", "").strip()
    last  = request.form.get("last_name", "").strip()
    div_ids = {int(x) for x in request.form.getlist("division_ids") if x.isdigit()}
    if not email or not first or not last:
        flash(_("Preencha todos os campos."), "danger")
    else:
        clash = User.query.filter(User.email == email, User.id != user.id).first()
        if clash:
            flash(_("E-mail já está em uso."), "danger")
        else:
            user.first_name = first
            user.last_name  = last
            user.email      = email
            existing = {sd.division_id: sd for sd in SecretaryDivision.query.filter_by(secretary_id=user.id).all()}
            for did, sd in existing.items():
                if did not in div_ids:
                    db.session.delete(sd)
            for did in div_ids:
                if did not in existing:
                    db.session.add(SecretaryDivision(secretary_id=user.id, division_id=did))
            db.session.commit()
            flash(_("Secretária atualizada."), "success")
    return redirect(url_for("admin.admins"))


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

# ── Secretary management ───────────────────────────────────────────────────────

@admin_bp.route("/secretaries")
@login_required
@admin_required
def secretaries():
    secs = User.query.filter_by(role='secretary').order_by(User.last_name, User.first_name).all()
    divisions = Division.query.order_by(Division.order, Division.name).all()
    div_ids_by_sec = {}
    for s in secs:
        div_ids_by_sec[s.id] = {sd.division_id for sd in SecretaryDivision.query.filter_by(secretary_id=s.id).all()}
    return render_template('admin/secretaries.html', secretaries=secs, divisions=divisions, div_ids_by_sec=div_ids_by_sec)


@admin_bp.route("/secretaries/new", methods=["GET", "POST"])
@login_required
@admin_required
def new_secretary():
    divisions = Division.query.order_by(Division.order, Division.name).all()
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        first = request.form.get("first_name", "").strip()
        last  = request.form.get("last_name", "").strip()
        div_ids = [int(x) for x in request.form.getlist("division_ids") if x.isdigit()]
        if not email or not first or not last:
            flash(_("Preencha todos os campos."), "danger")
        elif User.query.filter_by(email=email).first():
            flash(_("E-mail já está em uso."), "danger")
        else:
            user = User(email=email, role="secretary", first_name=first, last_name=last, preferred_language="pt")
            db.session.add(user)
            db.session.flush()
            for did in div_ids:
                db.session.add(SecretaryDivision(secretary_id=user.id, division_id=did))
            db.session.commit()
            flash(_("Secretária criada com sucesso."), "success")
            return redirect(url_for("admin.admins"))
    return render_template("admin/secretary_form.html", secretary=None, divisions=divisions, selected_div_ids=set())


@admin_bp.route("/secretaries/<int:id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_secretary(id):
    user = User.query.filter_by(id=id, role='secretary').first_or_404()
    divisions = Division.query.order_by(Division.order, Division.name).all()
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        first = request.form.get("first_name", "").strip()
        last  = request.form.get("last_name", "").strip()
        div_ids = {int(x) for x in request.form.getlist("division_ids") if x.isdigit()}
        clash = User.query.filter(User.email == email, User.id != user.id).first()
        if not email or not first or not last:
            flash(_("Preencha todos os campos."), "danger")
        elif clash:
            flash(_("E-mail já está em uso."), "danger")
        else:
            user.first_name = first
            user.last_name  = last
            user.email      = email
            # Sync divisions
            existing = {sd.division_id: sd for sd in SecretaryDivision.query.filter_by(secretary_id=user.id).all()}
            for did, sd in existing.items():
                if did not in div_ids:
                    db.session.delete(sd)
            for did in div_ids:
                if did not in existing:
                    db.session.add(SecretaryDivision(secretary_id=user.id, division_id=did))
            db.session.commit()
            flash(_("Secretária atualizada."), "success")
            return redirect(url_for("admin.admins"))
    selected_div_ids = {sd.division_id for sd in SecretaryDivision.query.filter_by(secretary_id=user.id).all()}
    return render_template("admin/secretary_form.html", secretary=user, divisions=divisions, selected_div_ids=selected_div_ids)


@admin_bp.route("/secretaries/<int:id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_secretary(id):
    user = User.query.filter_by(id=id, role='secretary').first_or_404()
    db.session.delete(user)
    db.session.commit()
    flash(_("Secretária removida."), "success")
    return redirect(url_for("admin.admins"))


@admin_bp.route("/secretaries/<int:id>/resend-invite", methods=["POST"])
@login_required
@admin_required
def resend_secretary_invite(id):
    user = User.query.filter_by(id=id, role='secretary').first_or_404()
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
_STUDENT_COLS  = ["email", "first_name", "last_name", "grade", "subjects",
                  "guardian1_email", "guardian1_first_name", "guardian1_last_name",
                  "guardian2_email", "guardian2_first_name", "guardian2_last_name",
                  "status"]
_GUARDIAN_COLS = ["email", "first_name", "last_name", "student1", "student2", "status"]


def _csv_response(rows, headers, filename):
    """Build a CSV HTTP response.

    Format: UTF-8 with BOM (Excel-compatible), comma delimiter, RFC 4180 quoting.
    The BOM (﻿) tells Excel to open as UTF-8 so accented characters (ã, ç, é…)
    display correctly without any manual import wizard.
    """
    buf = io.StringIO()
    buf.write('﻿')                          # UTF-8 BOM – Excel compatibility
    w = csv.writer(buf, quoting=csv.QUOTE_ALL)   # always quote → safe for commas/newlines in values
    w.writerow(headers)
    w.writerows(rows)
    return Response(
        buf.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _parse_cols(param, allowed, always=("email",)):
    """Return ordered list of column names from comma-separated param, filtered to allowed set."""
    requested = [c.strip() for c in param.split(",") if c.strip() in allowed]
    # ensure always-required columns are present
    for c in always:
        if c not in requested:
            requested.insert(0, c)
    return requested


_CSV_MAX_BYTES = 5 * 1024 * 1024   # 5 MB – protects against DoS via huge upload
_CSV_MIME_OK   = {"text/csv", "application/csv", "application/vnd.ms-excel",
                  "text/plain", "application/octet-stream"}


def _validate_csv_file(f):
    """Raise ValueError if file is missing, wrong type or too large."""
    if not f or not f.filename:
        raise ValueError(_("Nenhum arquivo enviado."))
    if not f.filename.lower().endswith(".csv"):
        raise ValueError(_("O arquivo deve ter extensão .csv."))
    # Read into memory with size guard
    data = f.stream.read(_CSV_MAX_BYTES + 1)
    if len(data) > _CSV_MAX_BYTES:
        raise ValueError(_("Arquivo muito grande (máximo 5 MB)."))
    return data


def _parse_csv_upload():
    f = request.files.get("csv_file")
    data = _validate_csv_file(f)
    text = data.decode("utf-8-sig")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=',\t;')
    except csv.Error:
        dialect = csv.excel
    stream = io.StringIO(text)
    reader = csv.DictReader(stream, dialect=dialect)
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
            # Standard: pipe-separated list of "Subject/Grade" pairs
            row.append("|".join(f"{sg.subject.name}/{sg.grade_group.name}" for sg in sgs))
        elif c == "status":       row.append("Ativo" if t.has_password() else "Pendente")
    return row


def _guardian_obj(g):
    """Serialize a guardian as semicolon-separated fields: email;first_name;last_name"""
    return f"{g.email};{g.first_name};{g.last_name}"


def _student_obj(s):
    """Serialize a student as semicolon-separated fields: email;first_name;last_name;grade"""
    grade = s.student_profile.grade_group.name if s.student_profile else ""
    return f"{s.email};{s.first_name};{s.last_name};{grade}"


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
        # Standard: pipe-separated list of subject names
        elif c == "subjects":   row.append("|".join(_student_active_subjects(s)))
        elif c == "status":     row.append("Ativo" if s.has_password() else "Pendente")
        elif c == "guardian1_email":      row.append(guardians[0].email      if len(guardians) > 0 else "")
        elif c == "guardian1_first_name": row.append(guardians[0].first_name if len(guardians) > 0 else "")
        elif c == "guardian1_last_name":  row.append(guardians[0].last_name  if len(guardians) > 0 else "")
        elif c == "guardian2_email":      row.append(guardians[1].email      if len(guardians) > 1 else "")
        elif c == "guardian2_first_name": row.append(guardians[1].first_name if len(guardians) > 1 else "")
        elif c == "guardian2_last_name":  row.append(guardians[1].last_name  if len(guardians) > 1 else "")
    return row


def _guardian_row(g, cols):
    """One row per guardian; linked students serialized as email;first_name;last_name;grade"""
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
                "subjects_grades": "Matemática/G9|Português/G10"}
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
    example = {"email": "maria.santos@escola.com", "first_name": "Maria",
               "last_name": "Santos", "grade": "G9",
               "subjects": "Matemática|Português|História",
               "guardian1_email": "carlos@email.com",
               "guardian1_first_name": "Carlos", "guardian1_last_name": "Oliveira",
               "guardian2_email": "", "guardian2_first_name": "", "guardian2_last_name": ""}
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
    example = {"email": "carlos@email.com", "first_name": "Carlos",
               "last_name": "Oliveira",
               "student1": "maria.santos@escola.com;Maria;Santos;G9",
               "student2": ""}
    return _csv_response([[example.get(c, "") for c in cols]], cols, "modelo_responsaveis.csv")


@admin_bp.route("/divisions/export.csv")
@login_required
@admin_required
def export_divisions():
    """Export sectors/grades/subject-assignments.
    Format: one row per grade.
      setor   – sector name
      turma   – grade name
      materias – pipe-separated subjects ASSIGNED to that grade (GradeGroupSubject)
    A sector with no grades gets a single row with an empty 'turma' column so
    it still appears in the file. Round-trip safe with import_divisions.
    """
    from app import _natsort_key
    divisions = Division.query.order_by(Division.order, Division.name).all()
    headers = ["setor", "turma", "materias"]
    rows = []
    for div in divisions:
        grades = sorted(div.grade_groups,
                        key=lambda g: (g.order, _natsort_key(g.name)))
        if not grades:
            # Sector exists but has no grades – export its subject pool anyway
            subjects_str = "|".join(
                sorted((s.name for s in div.subjects), key=_natsort_key))
            rows.append([div.name, "", subjects_str])
        else:
            for g in grades:
                assigned = sorted(
                    (gs.subject.name for gs in g.grade_subjects),
                    key=_natsort_key)
                rows.append([div.name, g.name, "|".join(assigned)])
    return _csv_response(rows, headers, "setores.csv")


@admin_bp.route("/divisions/template.csv")
@login_required
@admin_required
def template_divisions():
    """Return a minimal CSV template for divisions (one row per grade)."""
    headers = ["setor", "turma", "materias"]
    rows = [
        ["High School",   "G9",  "Mathematics|Science|English"],
        ["High School",   "G10", "Mathematics|Science|English"],
        ["High School",   "G11", "Mathematics|Science"],
        ["Middle School", "G6",  "Mathematics|Science|Portuguese"],
        ["Middle School", "G7",  "Mathematics|Science|Portuguese"],
    ]
    return _csv_response(rows, headers, "setores_modelo.csv")


@admin_bp.route("/divisions/import", methods=["POST"])
@login_required
@admin_required
def import_divisions():
    """Import sectors, grades and per-grade subject assignments from CSV.

    CSV format (one row per grade):
        setor    – sector name (created if missing)
        turma    – grade name (created if missing, assigned to sector)
        materias – pipe-separated subject names assigned to this grade

    A row with an empty 'turma' column is used to seed a sector's subject pool
    without creating a grade (e.g. from a sector-only export).

    Modes:
        add     – create/assign missing items, never delete anything
        replace – rebuild: remove grades/subjects NOT in the file (skips grades
                  that still have students)
        delete  – remove the sectors listed in the file
    """
    import csv, io

    file = request.files.get("csv_file")
    mode = request.form.get("mode", "add")

    try:
        raw = _validate_csv_file(file)
        stream = io.StringIO(raw.decode("utf-8-sig"))
        reader = csv.DictReader(stream)
        rows = list(reader)
    except Exception:
        flash(_("Erro ao ler o arquivo CSV."), "danger")
        return redirect(url_for("admin.divisions"))

    if not rows or "setor" not in (rows[0].keys() if rows else []):
        flash(_("Formato inválido. O arquivo deve ter a coluna 'setor'."), "danger")
        return redirect(url_for("admin.divisions"))

    created = updated = deleted = 0

    # ── Delete mode ───────────────────────────────────────────────────────────
    if mode == "delete":
        seen = set()
        for row in rows:
            div_name = row.get("setor", "").strip()
            if not div_name or div_name in seen:
                continue
            seen.add(div_name)
            div = Division.query.filter_by(name=div_name).first()
            if div:
                db.session.delete(div)
                deleted += 1
        db.session.commit()
        flash(_("%(n)s setor(es) removido(s).", n=deleted), "success")
        return redirect(url_for("admin.divisions"))

    # ── Build in-memory structure from CSV ────────────────────────────────────
    # csv_map[div_name] = {
    #   "grades": { grade_name: set(subject_names) },   ← per-grade subjects
    #   "pool":   set(subject_names),                   ← all subjects seen
    # }
    csv_map = {}
    for row in rows:
        div_name     = row.get("setor",    "").strip()
        grade_name   = row.get("turma",    "").strip()
        subjects_raw = row.get("materias", "").strip()
        if not div_name:
            continue
        subject_names = {s.strip() for s in subjects_raw.split("|")
                         if s.strip()} if subjects_raw else set()
        if div_name not in csv_map:
            csv_map[div_name] = {"grades": {}, "pool": set()}
        csv_map[div_name]["pool"].update(subject_names)
        if grade_name:
            if grade_name not in csv_map[div_name]["grades"]:
                csv_map[div_name]["grades"][grade_name] = set()
            csv_map[div_name]["grades"][grade_name].update(subject_names)

    # ── Process each sector ───────────────────────────────────────────────────
    for div_name, csv_data in csv_map.items():
        div = Division.query.filter_by(name=div_name).first()
        if not div:
            div = Division(name=div_name, order=0)
            db.session.add(div)
            db.session.flush()
            created += 1

        # ── Ensure all subjects in pool exist at sector level ──────────────
        existing_subject_names = {s.name for s in div.subjects}
        for sname in csv_data["pool"]:
            if sname not in existing_subject_names:
                db.session.add(Subject(name=sname, division_id=div.id))

        # ── Ensure all grades exist and belong to this sector ──────────────
        existing_grade_names = {g.name for g in div.grade_groups}
        for gname in csv_data["grades"]:
            if gname not in existing_grade_names:
                g = GradeGroup.query.filter_by(name=gname).first()
                if g:
                    g.division_id = div.id
                else:
                    db.session.add(GradeGroup(name=gname, division_id=div.id))

        # ── Replace mode: remove items absent from CSV ─────────────────────
        if mode == "replace":
            for g in list(div.grade_groups):
                if g.name not in csv_data["grades"]:
                    if g.student_profiles:
                        pass  # skip – students still assigned
                    else:
                        TeacherSubjectGrade.query.filter_by(
                            grade_group_id=g.id).delete(synchronize_session=False)
                        db.session.delete(g)
                        deleted += 1
            for s in list(div.subjects):
                if s.name not in csv_data["pool"]:
                    db.session.delete(s)
                    deleted += 1

        # ── Flush so all IDs are resolved ──────────────────────────────────
        db.session.flush()

        # ── Create per-grade subject assignments ───────────────────────────
        # Build lookup maps (name → object) after flush
        grade_map   = {g.name: g for g in div.grade_groups}
        subject_map = {s.name: s for s in div.subjects}

        for gname, snames in csv_data["grades"].items():
            g = grade_map.get(gname)
            if not g:
                continue
            for sname in snames:
                s = subject_map.get(sname)
                if not s:
                    continue
                already = GradeGroupSubject.query.filter_by(
                    grade_group_id=g.id, subject_id=s.id).first()
                if not already:
                    db.session.add(GradeGroupSubject(
                        grade_group_id=g.id, subject_id=s.id))

            # Replace mode: remove subject assignments absent from this grade's list
            if mode == "replace":
                for gs in list(g.grade_subjects):
                    if gs.subject.name not in snames:
                        db.session.delete(gs)

        updated += 1

    db.session.commit()

    if mode == "replace":
        flash(_("Importação concluída: %(c)s setor(es) processado(s), %(d)s item(ns) removido(s).",
                c=updated, d=deleted), "success")
    else:
        flash(_("Importação concluída: %(c)s setor(es) criado(s), %(u)s atualizado(s).",
                c=created, u=updated - created), "success")

    return redirect(url_for("admin.divisions"))


@admin_bp.route("/grades/matrix/export.csv")
@login_required
@admin_required
def export_grades_matrix():
    """Export grade × subject matrix with setor column."""
    from app import _natsort_key
    raw_div = request.args.get("division_id")

    if raw_div == "0":
        grades_q   = GradeGroup.query.filter_by(division_id=None)
        subjects_q = Subject.query.filter_by(division_id=None)
    elif raw_div and raw_div.isdigit():
        did = int(raw_div)
        grades_q   = GradeGroup.query.filter_by(division_id=did)
        subjects_q = Subject.query.filter_by(division_id=did)
    else:
        grades_q   = GradeGroup.query
        subjects_q = Subject.query

    grades   = sorted(grades_q.all(),   key=lambda g: _natsort_key(g.name), reverse=True)
    subjects = sorted(subjects_q.all(), key=lambda s: _natsort_key(s.name))
    active   = {(gs.grade_group_id, gs.subject_id) for gs in GradeGroupSubject.query.all()}
    headers  = ["setor", "turma"] + [s.name for s in subjects]
    rows = [
        [(g.division.name if g.division else ""), g.name]
        + ["1" if (g.id, s.id) in active else "0" for s in subjects]
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
        headers = ["setor", "turma"] + [s.name for s in subjects]
        rows = [
            ["High School", "G9"]  + ["1"] * len(subjects),
            ["High School", "G10"] + ["0"] * len(subjects),
        ]
    else:
        headers = ["setor", "turma", "Matemática", "Português"]
        rows = [["High School", "G9", "1", "1"], ["High School", "G10", "1", "0"]]
    return _csv_response(rows, headers, "modelo_turmas_materias.csv")


# ── CSV import ─────────────────────────────────────────────────────────────────

def _parse_person_cell(cell):
    """Parse a person cell into a dict with keys: email, first_name, last_name[, grade].

    Accepted formats:
      semicolon-sep  →  email;first_name;last_name[;grade]   (current standard)
      JSON object    →  {"email":...,"first_name":...,...}    (legacy)
    Returns dict or None if cell is empty/unparseable.
    """
    cell = cell.strip()
    if not cell:
        return None
    if cell.startswith("{"):
        # Legacy JSON object
        try:
            return json.loads(cell)
        except (json.JSONDecodeError, ValueError):
            return None
    # Standard semicolon-separated: email;first_name;last_name[;grade]
    parts = [p.strip() for p in cell.split(";")]
    if len(parts) < 1 or not parts[0]:
        return None
    data = {"email": parts[0].lower()}
    if len(parts) > 1: data["first_name"] = parts[1]
    if len(parts) > 2: data["last_name"]  = parts[2]
    if len(parts) > 3: data["grade"]      = parts[3]
    return data


def _link_guardian_to_student(student_id, g_str):
    """Parse a guardian cell and find-or-create the guardian, then link to student."""
    data = _parse_person_cell(g_str)
    if not data:
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


def _link_student_to_guardian(guardian_id, s_str):
    """Parse a student cell and link the (existing) student to the guardian."""
    data = _parse_person_cell(s_str)
    if not data:
        return
    em = data.get("email", "").strip().lower()
    if not em:
        return
    student = User.query.filter_by(email=em, role="student").first()
    if student and not GuardianStudent.query.filter_by(
            guardian_id=guardian_id, student_id=student.id).first():
        db.session.add(GuardianStudent(guardian_id=guardian_id, student_id=student.id))


def _import_teacher_subjects(teacher_id, subjects_grades_str):
    """Parse subjects_grades cell and create TeacherSubjectGrade records.

    Accepted formats (in order of preference):
      pipe-separated  →  Matemática/G9|Português/G10        (current standard)
      JSON array      →  ["Matemática/G9", "Português/G10"] (legacy, kept for backward compat)
      semicolon-sep   →  Matemática/G9; Português/G10       (old legacy)
    Each item must be "SubjectName/GradeName".
    """
    pairs = []
    stripped = subjects_grades_str.strip()
    if not stripped:
        return
    if stripped.startswith("["):
        # Legacy JSON array
        try:
            pairs = [p.strip() for p in json.loads(stripped) if isinstance(p, str) and p.strip()]
        except (json.JSONDecodeError, ValueError):
            pass
    if not pairs:
        # Standard pipe-separated (or legacy semicolon)
        sep = "|" if "|" in stripped else ";"
        pairs = [p.strip() for p in stripped.split(sep) if p.strip()]

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
        # New split-column format; fallback to old packed format
        g1_email = row.get("guardian1_email", "").strip()
        g1_fn    = row.get("guardian1_first_name", "").strip()
        g1_ln    = row.get("guardian1_last_name", "").strip()
        g1 = f"{g1_email};{g1_fn};{g1_ln}" if g1_email else row.get("guardian1", "").strip()

        g2_email = row.get("guardian2_email", "").strip()
        g2_fn    = row.get("guardian2_first_name", "").strip()
        g2_ln    = row.get("guardian2_last_name", "").strip()
        g2 = f"{g2_email};{g2_fn};{g2_ln}" if g2_email else row.get("guardian2", "").strip()

        if has_names and mode != "delete" and (not fn or not ln):
            continue
        valid_rows.append((fn, ln, em, grade_name, subj_str, g1, g2, len(valid_rows) + 2))
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

    added, skipped = 0, []
    for fn, ln, em, grade_name, subj_str, g1, g2, line_num in valid_rows:
        existing = User.query.filter_by(email=em).first()
        if existing:
            if existing.role == "student":
                skipped.append(f"Linha {line_num} ({em}): aluno já existe")
            else:
                skipped.append(f"Linha {line_num} ({em}): e-mail já usado por um {existing.role}")
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
    if added:
        flash(_("%(added)d aluno(s) importado(s).", added=added), "success")
    if skipped:
        details = " | ".join(skipped)
        flash(f"{len(skipped)} aluno(s) não importado(s): {details}", "warning")
    if not added and not skipped:
        flash(_("Nenhum aluno novo encontrado no arquivo."), "info")
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
    New format:  setor, turma, Subject1, Subject2, ...
    Legacy format: grade, Subject1, Subject2, ...  (no setor column)
    Modes: add (create missing), replace (rebuild), delete (delete listed grades).
    """
    mode = request.form.get("mode", "add")
    f = request.files.get("csv_file")
    try:
        raw = _validate_csv_file(f)
        stream = io.StringIO(raw.decode("utf-8-sig"))
        reader = csv.DictReader(stream)
        data_rows = [r for r in reader if any(v.strip() for v in r.values())]
        header = [c.strip() for c in (reader.fieldnames or [])]
    except Exception as e:
        flash(_("Erro ao ler arquivo: %(err)s", err=str(e)), "danger")
        return redirect(url_for("admin.grades"))

    if not header:
        flash(_("Arquivo vazio ou sem cabeçalho."), "danger")
        return redirect(url_for("admin.grades"))

    # Normalise header keys (strip whitespace from dict keys in each row)
    data_rows = [{k.strip(): v.strip() for k, v in row.items()} for row in data_rows]

    # Detect format: new → first cols are "setor" and "turma"; legacy → first col is "grade"
    has_setor = (len(header) >= 2
                 and header[0].lower() == "setor"
                 and header[1].lower() == "turma")
    if has_setor:
        grade_key    = "turma"
        setor_key    = "setor"
        subject_names = [h for h in header if h.lower() not in ("setor", "turma")]
    else:
        grade_key    = header[0]   # "grade" or first column
        setor_key    = None
        subject_names = header[1:]

    grade_names_in_file = {r[grade_key] for r in data_rows if r.get(grade_key)}

    if mode == "delete":
        deleted = 0
        for name in grade_names_in_file:
            grade = GradeGroup.query.filter_by(name=name).first()
            if grade:
                db.session.delete(grade)
                deleted += 1
        db.session.commit()
        flash(_("%(n)d turma(s) apagada(s).", n=deleted), "success")
        return redirect(url_for("admin.grades"))

    if mode == "replace":
        GradeGroupSubject.query.delete(synchronize_session=False)
        TeacherSubjectGrade.query.delete(synchronize_session=False)
        for g in GradeGroup.query.filter(~GradeGroup.name.in_(grade_names_in_file)).all():
            db.session.delete(g)
        for s in Subject.query.filter(~Subject.name.in_(subject_names)).all():
            db.session.delete(s)
        db.session.flush()

    # Division lookup/create cache
    div_cache = {}
    def get_or_create_division(name):
        name = name.strip()
        if not name:
            return None
        if name not in div_cache:
            d = Division.query.filter_by(name=name).first()
            if not d:
                max_o = db.session.query(db.func.max(Division.order)).scalar() or 0
                d = Division(name=name, order=max_o + 1)
                db.session.add(d)
                db.session.flush()
            div_cache[name] = d
        return div_cache[name]

    # Ensure all subjects exist (once per division)
    subject_objs = {}  # (name, div_id) → Subject
    for row in data_rows:
        div = get_or_create_division(row[setor_key]) if setor_key else None
        div_id = div.id if div else None
        for sname in subject_names:
            if not sname:
                continue
            key = (sname, div_id)
            if key not in subject_objs:
                s = Subject.query.filter_by(name=sname, division_id=div_id).first()
                if not s:
                    s = Subject(name=sname, division_id=div_id)
                    db.session.add(s)
                    db.session.flush()
                subject_objs[key] = s

    added_grades = added_links = 0
    for row in data_rows:
        grade_name = row.get(grade_key, "").strip()
        if not grade_name:
            continue

        div = get_or_create_division(row[setor_key]) if setor_key else None
        div_id = div.id if div else None

        grade = GradeGroup.query.filter_by(name=grade_name).first()
        if not grade:
            grade = GradeGroup(name=grade_name, division_id=div_id)
            db.session.add(grade)
            db.session.flush()
            added_grades += 1
        elif div_id and not grade.division_id:
            grade.division_id = div_id

        for sname in subject_names:
            if not sname:
                continue
            subject = subject_objs.get((sname, div_id))
            if not subject:
                continue
            cell = row.get(sname, "0").strip()
            is_active = cell in ("1", "true", "True", "TRUE", "yes", "YES")
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

@admin_bp.route("/events/<int:event_id>/attendance_data")
@login_required
@secretary_or_admin_required
def event_attendance_data(event_id):
    event = ConferenceEvent.query.get_or_404(event_id)
    days  = sorted(event.days, key=lambda d: d.date)

    absence_records = (TeacherDayAbsence.query
                       .join(ConferenceDay, TeacherDayAbsence.day_id == ConferenceDay.id)
                       .filter(ConferenceDay.event_id == event_id).all())
    absent_set = {(a.day_id, a.teacher_id) for a in absence_records}

    from sqlalchemy import func
    day_ids = [d.id for d in days]
    counts = (db.session.query(Slot.day_id, Slot.teacher_id, func.count(Booking.id))
              .join(Booking, (Booking.slot_id == Slot.id) & (Booking.cancelled_at == None))
              .filter(Slot.day_id.in_(day_ids))
              .group_by(Slot.day_id, Slot.teacher_id)
              .all()) if day_ids else []
    booking_counts = {f"{d}_{t}": c for d, t, c in counts}

    all_teachers = (User.query.filter_by(role="teacher", is_active=True)
                    .order_by(User.last_name, User.first_name).all())

    return jsonify({
        "days": [{"id": d.id,
                  "date": d.date.strftime('%d/%m/%Y'),
                  "division": d.division.name if d.division else None} for d in days],
        "teachers": [{"id": t.id, "name": t.full_name,
                      "initials": (t.first_name[0] + t.last_name[0]).upper()}
                     for t in all_teachers],
        "absent": [[a.day_id, a.teacher_id] for a in absence_records],
        "bookings": booking_counts,
    })


@admin_bp.route("/events/<int:event_id>/days/<int:day_id>/absence/<int:teacher_id>/set_absent",
                methods=["POST"])
@login_required
@secretary_or_admin_required
def set_teacher_absent(event_id, day_id, teacher_id):
    data           = request.get_json() or {}
    cancel_bk      = data.get('cancel_bookings', False)
    send_notify    = data.get('notify', False)

    ConferenceDay.query.filter_by(id=day_id, event_id=event_id).first_or_404()
    if not TeacherDayAbsence.query.filter_by(day_id=day_id, teacher_id=teacher_id).first():
        db.session.add(TeacherDayAbsence(day_id=day_id, teacher_id=teacher_id))

    cancelled_bookings = []
    if cancel_bk:
        cancelled_bookings = (Booking.query.join(Slot)
                              .filter(Slot.teacher_id == teacher_id,
                                      Slot.day_id == day_id,
                                      Booking.cancelled_at == None).all())
        for b in cancelled_bookings:
            b.cancelled_at = datetime.utcnow()

    db.session.commit()

    sent = 0
    if send_notify and cancelled_bookings:
        day     = ConferenceDay.query.get(day_id)
        event   = ConferenceEvent.query.get(event_id)
        teacher = User.query.get(teacher_id)
        notified = set()
        for booking in cancelled_bookings:
            student = User.query.get(booking.student_id)
            if not student:
                continue
            for gs in student.student_guardians:
                guardian = gs.guardian
                if guardian.id in notified:
                    continue
                gids = {link.student_id for link in guardian.guardian_students}
                g_bookings = [b for b in cancelled_bookings if b.student_id in gids]
                try:
                    send_teacher_absent_email(guardian, teacher, day, g_bookings, event)
                    notified.add(guardian.id)
                    sent += 1
                except Exception:
                    pass

    return jsonify({"ok": True, "sent": sent})

@admin_bp.route("/events/<int:event_id>/days/<int:day_id>/absence/<int:teacher_id>/toggle", methods=["POST"])
@login_required
@secretary_or_admin_required
def toggle_teacher_absence(event_id, day_id, teacher_id):
    ConferenceDay.query.filter_by(id=day_id, event_id=event_id).first_or_404()
    existing = TeacherDayAbsence.query.filter_by(day_id=day_id, teacher_id=teacher_id).first()
    if existing:
        db.session.delete(existing)
        is_absent = False
        affected = 0
    else:
        db.session.add(TeacherDayAbsence(day_id=day_id, teacher_id=teacher_id))
        is_absent = True
        affected = (Booking.query.join(Slot)
                    .filter(Slot.teacher_id == teacher_id,
                            Slot.day_id == day_id,
                            Booking.cancelled_at == None)
                    .count())
    db.session.commit()
    return jsonify({"is_absent": is_absent, "affected_bookings": affected})


@admin_bp.route("/events/<int:event_id>/days/<int:day_id>/absence/<int:teacher_id>/notify", methods=["POST"])
@login_required
@secretary_or_admin_required
def notify_teacher_absent(event_id, day_id, teacher_id):
    """Send absence notification emails to guardians/students with bookings for this teacher on this day."""
    day = ConferenceDay.query.filter_by(id=day_id, event_id=event_id).first_or_404()
    event = ConferenceEvent.query.get_or_404(event_id)
    teacher = User.query.get_or_404(teacher_id)
    bookings = (Booking.query.join(Slot)
                .filter(Slot.teacher_id == teacher_id,
                        Slot.day_id == day_id,
                        Booking.cancelled_at == None)
                .all())
    sent = 0
    notified = set()
    for booking in bookings:
        student = User.query.get(booking.student_id)
        if not student:
            continue
        for gs in student.student_guardians:
            guardian = gs.guardian
            if guardian.id in notified:
                continue
            # Collect all this guardian's affected bookings
            gids = {link.student_id for link in guardian.guardian_students}
            guardian_bookings = [b for b in bookings if b.student_id in gids]
            try:
                send_teacher_absent_email(guardian, teacher, day, guardian_bookings, event)
                notified.add(guardian.id)
                sent += 1
            except Exception:
                pass
    return jsonify({"sent": sent})


# ── Teacher breaks ─────────────────────────────────────────────────────────────

@admin_bp.route("/events/<int:event_id>/teacher-breaks/<int:teacher_id>")
@login_required
@secretary_or_admin_required
def teacher_break_data(event_id, teacher_id):
    """Return all days + slot grid + current breaks for a teacher in this event."""
    from datetime import timedelta, time as dt_time
    event = ConferenceEvent.query.get_or_404(event_id)
    teacher = User.query.get_or_404(teacher_id)

    # Find the EventSectorTeacher record for this teacher in this event
    etc = (EventSectorTeacher.query
           .join(EventSector, EventSectorTeacher.sector_id == EventSector.id)
           .filter(EventSector.event_id == event_id,
                   EventSectorTeacher.teacher_id == teacher_id)
           .first())
    if not etc:
        return jsonify({"teacher_name": teacher.full_name, "days": []})

    sector = etc.sector
    slot_dur_min = etc.slot_duration_minutes or sector.slot_duration_minutes or 0
    break_min = sector.break_minutes or 0

    # Get all conference days for this sector's division
    days = (ConferenceDay.query
            .filter_by(event_id=event_id, division_id=sector.division_id)
            .order_by(ConferenceDay.date)
            .all())

    # Fetch existing breaks for these days for this teacher
    day_ids = [d.id for d in days]
    existing_breaks = TeacherBreak.query.filter(
        TeacherBreak.teacher_id == teacher_id,
        TeacherBreak.day_id.in_(day_ids)
    ).all()
    breaks_by_day = {}
    for tb in existing_breaks:
        breaks_by_day.setdefault(tb.day_id, set()).add(
            tb.start_time.strftime('%H:%M'))

    days_out = []
    for day in days:
        # Use sector start/end if available, else fall back to day
        s_time = sector.start_time or day.start_time
        e_time = sector.end_time or day.end_time
        if not slot_dur_min or slot_dur_min <= 0:
            days_out.append({
                "day_id": day.id,
                "date": day.date.strftime('%Y-%m-%d'),
                "slots": []
            })
            continue

        from datetime import datetime as _dt
        start_dt = _dt.combine(day.date, s_time)
        end_dt   = _dt.combine(day.date, e_time)
        step     = timedelta(minutes=slot_dur_min + break_min)
        slot_dur = timedelta(minutes=slot_dur_min)

        day_break_set = breaks_by_day.get(day.id, set())
        slots_out = []
        current = start_dt
        guard = 500
        while current + slot_dur <= end_dt and guard > 0:
            t_str = current.strftime('%H:%M')
            slots_out.append({
                "start_time": t_str,
                "is_break": t_str in day_break_set,
            })
            current += step
            guard -= 1

        days_out.append({
            "day_id": day.id,
            "date": day.date.strftime('%Y-%m-%d'),
            "slots": slots_out,
        })

    return jsonify({"teacher_name": teacher.full_name, "days": days_out})


@admin_bp.route("/events/<int:event_id>/teacher-breaks/toggle", methods=["POST"])
@login_required
@secretary_or_admin_required
def toggle_teacher_break(event_id):
    """Toggle a break for a teacher at a specific day+time."""
    from datetime import datetime as _dt, time as _time, timedelta
    event = ConferenceEvent.query.get_or_404(event_id)
    data = request.get_json(silent=True) or {}
    teacher_id = data.get('teacher_id')
    day_id = data.get('day_id')
    start_time_str = data.get('start_time')  # "HH:MM"

    if not teacher_id or not day_id or not start_time_str:
        return jsonify({"error": "Missing fields"}), 400

    day = ConferenceDay.query.filter_by(id=day_id, event_id=event_id).first_or_404()

    try:
        h, m = map(int, start_time_str.split(':'))
        from datetime import time as dt_time
        start_time = dt_time(h, m)
    except Exception:
        return jsonify({"error": "Invalid start_time"}), 400

    existing = TeacherBreak.query.filter_by(
        teacher_id=teacher_id, day_id=day_id, start_time=start_time).first()

    if existing:
        # Remove break
        db.session.delete(existing)
        is_break = False
        # If published: update corresponding slot
        if event.status == 'published':
            start_dt = _dt.combine(day.date, start_time)
            slot = Slot.query.filter_by(
                teacher_id=teacher_id, day_id=day_id,
                start_datetime=start_dt).first()
            if slot:
                slot.is_break = False
    else:
        # Add break
        db.session.add(TeacherBreak(
            teacher_id=teacher_id, day_id=day_id, start_time=start_time))
        is_break = True
        # If published: also sync the Slot
        if event.status == 'published':
            start_dt = _dt.combine(day.date, start_time)
            slot = Slot.query.filter_by(
                teacher_id=teacher_id, day_id=day_id,
                start_datetime=start_dt).first()
            if slot:
                slot.is_break = True
                # Cancel any active booking on this slot
                if slot.booking and not slot.booking.cancelled_at:
                    slot.booking.cancelled_at = _dt.utcnow()
                    slot.is_booked = False
            else:
                # No slot yet — find duration from sector config
                etc = (EventSectorTeacher.query
                       .join(EventSector, EventSectorTeacher.sector_id == EventSector.id)
                       .filter(EventSector.event_id == event_id,
                               EventSectorTeacher.teacher_id == teacher_id)
                       .first())
                dur_min = None
                if etc:
                    dur_min = etc.slot_duration_minutes or (etc.sector.slot_duration_minutes if etc.sector else None)
                if dur_min:
                    end_dt = start_dt + timedelta(minutes=dur_min)
                    db.session.add(Slot(
                        day_id=day_id,
                        teacher_id=teacher_id,
                        start_datetime=start_dt,
                        end_datetime=end_dt,
                        is_booked=False,
                        is_break=True,
                    ))

    db.session.commit()
    return jsonify({"is_break": is_break})


# ── Event reminders ────────────────────────────────────────────────────────────

@admin_bp.route("/events/<int:event_id>/reminders/add", methods=["POST"])
@login_required
@secretary_or_admin_required
def add_reminder(event_id):
    ConferenceEvent.query.get_or_404(event_id)
    hours = request.get_json(silent=True) or {}
    hours_before = hours.get("hours_before")
    if hours_before is None:
        hours_before = request.form.get("hours_before", type=int)
    if hours_before is None or int(hours_before) < 0:
        return jsonify({"error": "Invalid value"}), 400
    reminder = EventReminder(event_id=event_id, hours_before=int(hours_before))
    db.session.add(reminder)
    db.session.commit()
    return jsonify({"id": reminder.id, "hours_before": reminder.hours_before})


@admin_bp.route("/events/<int:event_id>/reminders/<int:reminder_id>/delete", methods=["POST"])
@login_required
@secretary_or_admin_required
def delete_reminder(event_id, reminder_id):
    reminder = EventReminder.query.filter_by(id=reminder_id, event_id=event_id).first_or_404()
    db.session.delete(reminder)
    db.session.commit()
    return jsonify({"ok": True})


@admin_bp.route("/events/<int:event_id>/reminders/<int:reminder_id>/send", methods=["POST"])
@login_required
@secretary_or_admin_required
def send_reminder_now(event_id, reminder_id):
    """Manually send a booking-summary reminder to all guardians with bookings in this event."""
    event = ConferenceEvent.query.get_or_404(event_id)
    EventReminder.query.filter_by(id=reminder_id, event_id=event_id).first_or_404()
    sent = errors = 0
    for day in event.days:
        # Build guardian → bookings map for this day
        guardian_map = {}
        day_bookings = (Booking.query.join(Slot).join(ConferenceDay)
                        .filter(ConferenceDay.id == day.id,
                                Booking.cancelled_at == None).all())
        for b in day_bookings:
            student = User.query.get(b.student_id)
            if not student:
                continue
            for gs in student.student_guardians:
                gid = gs.guardian_id
                if gid not in guardian_map:
                    guardian_map[gid] = []
                guardian_map[gid].append(b)
        for gid, bkgs in guardian_map.items():
            guardian = User.query.get(gid)
            if not guardian:
                continue
            try:
                send_booking_reminder_email(guardian, event, day, bkgs)
                sent += 1
            except Exception:
                errors += 1
    return jsonify({"sent": sent, "errors": errors})


# ── Toggle day active/inactive ─────────────────────────────────────────────────

@admin_bp.route("/events/<int:event_id>/days/<int:day_id>/toggle-active", methods=["POST"])
@login_required
@secretary_or_admin_required
def toggle_day_active(event_id, day_id):
    day = ConferenceDay.query.filter_by(id=day_id, event_id=event_id).first_or_404()
    day.is_active = not day.is_active
    db.session.commit()
    return jsonify({"is_active": day.is_active})


def _get_grade_subjects_map():
    """Returns list of (GradeGroup, Subject) pairs defined via GradeGroupSubject."""
    from app import _natsort_key
    rows = (GradeGroupSubject.query
            .join(GradeGroup, GradeGroupSubject.grade_group_id == GradeGroup.id)
            .join(Subject, GradeGroupSubject.subject_id == Subject.id)
            .order_by(Subject.name)
            .all())
    # Group by grade for easy template iteration: {grade: [subject, ...]}
    from collections import defaultdict
    grouped = defaultdict(list)
    grade_objs = {}
    for gs in rows:
        grouped[gs.grade_group_id].append(gs.subject)
        grade_objs[gs.grade_group_id] = gs.grade_group
    # Sort grades descending (G12 → G11 → G10 …)
    sorted_gids = sorted(grade_objs.keys(),
                         key=lambda gid: _natsort_key(grade_objs[gid].name),
                         reverse=True)
    return [(grade_objs[gid], grouped[gid]) for gid in sorted_gids]


def _sg_data_js(grade_subjects_by_sector):
    """Serialisable list for JS — mirrors grade_subjects_by_sector structure."""
    result = []
    for div, grade_list in grade_subjects_by_sector:
        result.append({
            "div_id":   div.id   if div else 0,
            "div_name": div.name if div else "Sem setor",
            "grades": [
                {"grade_id":   g.id,
                 "grade_name": g.name,
                 "subjects":   [{"id": s.id, "name": s.name} for s in subs]}
                for g, subs in grade_list
            ],
        })
    return result


def _get_grade_subjects_by_sector():
    """Returns sector-grouped structure for the teacher form.

    Returns:
        [(Division, [(GradeGroup, [Subject, ...])])]
    Includes ALL grades in ALL sectors, even those with no subject assignments.
    Ordered: sectors by (order, name); grades by (order, name); subjects by name.
    """
    from app import _natsort_key
    from collections import defaultdict

    # Pre-load every subject assignment once (grade_id → sorted subjects)
    grade_subjects: dict = defaultdict(list)
    for gs in (GradeGroupSubject.query
               .join(Subject, GradeGroupSubject.subject_id == Subject.id)
               .order_by(Subject.name)
               .all()):
        grade_subjects[gs.grade_group_id].append(gs.subject)

    # Walk every Division (in display order) and include all its grades
    result = []
    for div in Division.query.order_by(Division.order, Division.name).all():
        grades = sorted(div.grade_groups,
                        key=lambda g: (g.order, _natsort_key(g.name)))
        if grades:          # skip sectors that have no grades at all
            result.append((div, [(g, grade_subjects[g.id]) for g in grades]))
    return result


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
@secretary_or_admin_required
def students():
    # Purge abandoned draft records (created via new_student but never filled in)
    abandoned = User.query.filter(
        User.role == "student",
        User.email.like("__draft_%@draft.local")
    ).all()
    for u in abandoned:
        db.session.delete(u)
    if abandoned:
        db.session.commit()

    grade_filter = request.args.get("grade_id", type=int)
    query = User.query.filter_by(role="student").filter(
        ~User.email.like("__draft_%@draft.local")
    )
    if grade_filter:
        query = query.join(StudentProfile).filter(StudentProfile.grade_group_id == grade_filter)
    students = query.order_by(User.last_name).all()
    from app import _natsort_key
    grades = sorted(GradeGroup.query.all(), key=lambda g: _natsort_key(g.name), reverse=True)
    published_events = ConferenceEvent.query.filter_by(status='published').order_by(ConferenceEvent.name).all()
    return render_template("admin/students.html", students=students, grades=grades,
                           grade_filter=grade_filter, published_events=published_events)


@admin_bp.route("/students/<int:student_id>/schedule/<int:event_id>")
@login_required
@secretary_or_admin_required
def admin_student_schedule(student_id, event_id):
    student = User.query.get_or_404(student_id)
    event   = ConferenceEvent.query.get_or_404(event_id)
    if event.status != 'published':
        flash(_("Este evento não está publicado."), "warning")
        return redirect(url_for("admin.students"))
    return render_template("admin/student_schedule.html", event=event, student=student)


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
    past_conferences = _past_conferences_for_student(user.id)
    return render_template("admin/student_form.html", form=form, student=user,
                           is_new=is_new,
                           guardians=guardians, available_guardians=available_guardians,
                           grade_subjects=grade_subjects, excluded_ids=excluded_ids,
                           past_conferences=past_conferences)


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
        db.session.commit()
        flash(_("Responsável criado com sucesso."), "success")

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


# ── Past-conference helpers ──────────────────────────────────────────────────

def _past_event_filter():
    today = date_type.today()
    return db.or_(ConferenceEvent.status == "closed", ConferenceDay.date < today)


def _past_conferences_for_guardian(guardian_id):
    rows = (
        db.session.query(Booking, Slot, ConferenceDay, ConferenceEvent)
        .join(Slot, Slot.id == Booking.slot_id)
        .join(ConferenceDay, ConferenceDay.id == Slot.day_id)
        .join(ConferenceEvent, ConferenceEvent.id == ConferenceDay.event_id)
        .filter(Booking.booked_by_id == guardian_id, Booking.cancelled_at == None,
                _past_event_filter())
        .order_by(ConferenceEvent.id, ConferenceDay.date, Slot.start_datetime)
        .all()
    )
    events_map = {}
    for booking, slot, day, event in rows:
        if event.id not in events_map:
            events_map[event.id] = {"event": event, "meetings": []}
        events_map[event.id]["meetings"].append(
            {"student": booking.student, "teacher": slot.teacher, "day": day, "slot": slot}
        )
    return list(events_map.values())


def _past_conferences_for_student(student_id):
    rows = (
        db.session.query(Booking, Slot, ConferenceDay, ConferenceEvent)
        .join(Slot, Slot.id == Booking.slot_id)
        .join(ConferenceDay, ConferenceDay.id == Slot.day_id)
        .join(ConferenceEvent, ConferenceEvent.id == ConferenceDay.event_id)
        .filter(Booking.student_id == student_id, Booking.cancelled_at == None,
                _past_event_filter())
        .order_by(ConferenceEvent.id, ConferenceDay.date, Slot.start_datetime)
        .all()
    )
    events_map = {}
    for booking, slot, day, event in rows:
        if event.id not in events_map:
            events_map[event.id] = {"event": event, "meetings": []}
        events_map[event.id]["meetings"].append(
            {"teacher": slot.teacher, "day": day, "slot": slot}
        )
    return list(events_map.values())


def _past_conferences_for_teacher(teacher_id):
    rows = (
        db.session.query(Slot, ConferenceDay, ConferenceEvent, Booking)
        .join(ConferenceDay, ConferenceDay.id == Slot.day_id)
        .join(ConferenceEvent, ConferenceEvent.id == ConferenceDay.event_id)
        .outerjoin(Booking, Booking.slot_id == Slot.id)
        .filter(Slot.teacher_id == teacher_id, Slot.is_booked == True,
                Slot.is_break == False, _past_event_filter())
        .order_by(ConferenceEvent.id, ConferenceDay.date, Slot.start_datetime)
        .all()
    )
    events_map = {}
    for slot, day, event, booking in rows:
        if event.id not in events_map:
            events_map[event.id] = {"event": event, "meetings": []}
        events_map[event.id]["meetings"].append(
            {"student": booking.student if booking else None, "day": day, "slot": slot}
        )
    return list(events_map.values())


# ── Events ─────────────────────────────────────────────────────────────────────

@admin_bp.route("/events")
@login_required
@secretary_or_admin_required
def events():
    all_events = ConferenceEvent.query.order_by(ConferenceEvent.name).all()
    return render_template("admin/events.html", events=all_events, today=date_type.today())


@admin_bp.route("/events/<int:event_id>/copy", methods=["POST"])
@login_required
@admin_required
def copy_event(event_id):
    src = ConferenceEvent.query.get_or_404(event_id)
    new_event = ConferenceEvent(
        name=f"{src.name} cópia",
        student_booking_allowed=src.student_booking_allowed,
        allow_duplicate_teacher_booking=src.allow_duplicate_teacher_booking,
        cancel_deadline_hours=src.cancel_deadline_hours,
        status="draft",
    )
    db.session.add(new_event)
    db.session.flush()
    for sector in src.sectors:
        new_sector = EventSector(
            event_id=new_event.id,
            division_id=sector.division_id,
            start_time=sector.start_time,
            end_time=sector.end_time,
            slot_duration_minutes=sector.slot_duration_minutes,
            break_minutes=sector.break_minutes,
        )
        db.session.add(new_sector)
        db.session.flush()
        for tc in sector.teacher_configs:
            db.session.add(EventSectorTeacher(
                sector_id=new_sector.id,
                teacher_id=tc.teacher_id,
                slot_duration_minutes=tc.slot_duration_minutes,
            ))
    for day in src.days:
        db.session.add(ConferenceDay(
            event_id=new_event.id,
            division_id=day.division_id,
            date=day.date,
            start_time=day.start_time,
            end_time=day.end_time,
            slot_duration_minutes=day.slot_duration_minutes,
            break_minutes=day.break_minutes,
        ))
    db.session.commit()
    flash(_("Evento copiado como rascunho."), "success")
    return redirect(url_for("admin.edit_event", id=new_event.id, is_new=1))


def _has_at_least_one_day():
    """Return True if the submitted form contains at least one complete day row
    (date + start_time + end_time) in any sector."""
    for key in request.form:
        m = re.match(r'^sector_(\d+)_slot_duration$', key)
        if not m:
            continue
        dk = m.group(1)
        dates  = request.form.getlist(f"sector_{dk}_day_dates[]")
        starts = request.form.getlist(f"sector_{dk}_day_starts[]")
        ends   = request.form.getlist(f"sector_{dk}_day_ends[]")
        for d, s, e in zip(dates, starts, ends):
            if d.strip() and s.strip() and e.strip():
                return True
    return False


@admin_bp.route("/events/new", methods=["GET", "POST"])
@login_required
@admin_required
def new_event():
    form = ConferenceEventSimpleForm()
    divisions = Division.query.order_by(Division.order, Division.name).all()
    if form.validate_on_submit():
        if not _has_at_least_one_day():
            flash(_("Adicione pelo menos 1 dia de reunião (com data, início e fim) em qualquer setor."), "warning")
        else:
            event = ConferenceEvent(
                name=form.name.data,
                student_booking_allowed=form.student_booking_allowed.data,
                cancel_deadline_hours=form.cancel_deadline_hours.data,
            )
            db.session.add(event)
            db.session.flush()
            _save_event_sectors(event, conflict_action='keep')
            db.session.commit()
            flash(_("Evento criado e horários gerados."), "success")
            return redirect(url_for("admin.edit_event", id=event.id, is_new=1))
    sector_teachers_js = _build_sector_teachers_js(divisions)
    # Preserve submitted form data on validation error
    existing_sectors = {}
    if request.method == 'POST':
        existing_sectors = _build_existing_sectors_from_post()
    return render_template("admin/event_form.html",
                           form=form, event=None,
                           divisions=divisions,
                           sector_teachers_js=sector_teachers_js,
                           existing_sectors=existing_sectors,
                           all_teachers_data=[], absent_set_list=[], absent_set=set(),
                           secretary_division_ids=[])


@admin_bp.route("/events/<int:id>/check-conflicts")
@login_required
@secretary_or_admin_required
def event_check_conflicts(id):
    """Return days that have bookings and are about to be removed from the event (used by JS modal)."""
    event = ConferenceEvent.query.get_or_404(id)
    # Collect all dates still in the form (sent as sector_{divId}_day_dates[] query params)
    form_dates = set()
    for key, val in request.args.items(multi=True):
        if re.match(r'^sector_\d+_day_dates\[\]$', key) and val:
            try:
                form_dates.add(datetime.strptime(val, '%Y-%m-%d').date())
            except ValueError:
                pass
    conflicts = []
    for day in event.days:
        if day.date in form_dates:
            continue
        count = db.session.query(Booking).join(Slot).filter(
            Slot.day_id == day.id,
            Booking.cancelled_at == None
        ).count()
        if count:
            conflicts.append({'date': day.date.strftime('%d/%m/%Y'), 'bookings': count})
    return jsonify({'conflicts': conflicts})


@admin_bp.route("/events/<int:id>/edit", methods=["GET", "POST"])
@login_required
@secretary_or_admin_required
def edit_event(id):
    event = ConferenceEvent.query.get_or_404(id)
    form  = ConferenceEventSimpleForm(obj=event)
    divisions = Division.query.order_by(Division.order, Division.name).all()

    if form.validate_on_submit():
        if event.status != 'draft':
            flash(_("Evento publicado não pode ser editado. Despublique primeiro."), "warning")
            return redirect(url_for("admin.edit_event", id=id))

        # For secretaries: filter out sectors they don't manage from the form data
        if current_user.role == 'secretary':
            sec_div_ids = get_secretary_division_ids()
            from werkzeug.datastructures import ImmutableMultiDict
            allowed_items = []
            for key, value in request.form.items(multi=True):
                m = re.match(r'^sector_(\d+)_', key)
                if m:
                    if int(m.group(1)) in sec_div_ids:
                        allowed_items.append((key, value))
                else:
                    allowed_items.append((key, value))
            request.form = ImmutableMultiDict(allowed_items)

        if not _has_at_least_one_day():
            flash(_("Adicione pelo menos 1 dia de reunião (com data, início e fim) em qualquer setor."), "warning")
        else:
            event.name                            = form.name.data
            event.student_booking_allowed         = form.student_booking_allowed.data
            event.allow_duplicate_teacher_booking = request.form.get('allow_duplicate_teacher_booking') == 'on'
            event.cancel_deadline_hours           = form.cancel_deadline_hours.data
            conflict_action = request.form.get('conflict_action', 'keep')
            protected = _save_event_sectors(event, conflict_action=conflict_action)
            db.session.commit()
            if protected:
                flash(_("Evento atualizado. Dia(s) %(d)s não removido(s) por terem agendamentos.",
                        d=', '.join(protected)), "warning")
            else:
                flash(_("Evento atualizado."), "success")
            return redirect(url_for("admin.events"))

    # ── Build template context ────────────────────────────────────────────────
    sector_teachers_js = _build_sector_teachers_js(divisions)
    existing_sectors   = _build_existing_sectors(event)
    all_teachers = (User.query.filter_by(role="teacher", is_active=True)
                    .order_by(User.last_name, User.first_name).all())
    absent_set = {(a.day_id, a.teacher_id)
                  for a in TeacherDayAbsence.query
                  .join(ConferenceDay, TeacherDayAbsence.day_id == ConferenceDay.id)
                  .filter(ConferenceDay.event_id == id).all()}
    all_teachers_data = [
        {"id": t.id, "name": t.full_name,
         "initials": (t.first_name[0] + t.last_name[0]).upper()}
        for t in all_teachers
    ]
    absent_set_list = [[d, t] for d, t in absent_set]
    secretary_division_ids = list(get_secretary_division_ids()) if current_user.role == 'secretary' else []
    # Teacher IDs that have at least one break in this event
    teachers_with_breaks = list({
        tb.teacher_id for tb in
        TeacherBreak.query.join(ConferenceDay, TeacherBreak.day_id == ConferenceDay.id)
        .filter(ConferenceDay.event_id == id).all()
    })
    is_new = request.args.get('is_new') == '1'
    return render_template("admin/event_form.html",
                           form=form, event=event,
                           divisions=divisions,
                           sector_teachers_js=sector_teachers_js,
                           existing_sectors=existing_sectors,
                           all_teachers=all_teachers,
                           all_teachers_data=all_teachers_data,
                           absent_set_list=absent_set_list,
                           absent_set=absent_set,
                           secretary_division_ids=secretary_division_ids,
                           teachers_with_breaks=teachers_with_breaks,
                           is_new=is_new)


@admin_bp.route("/events/<int:id>/publish", methods=["POST"])
@login_required
@admin_required
def publish_event(id):
    event = ConferenceEvent.query.get_or_404(id)
    if event.status != 'draft':
        flash(_("Apenas eventos em rascunho podem ser publicados."), "warning")
        return redirect(url_for("admin.events"))
    _generate_all_slots_for_event(event)
    event.status = "published"
    db.session.commit()
    flash(_("Evento publicado e horários gerados."), "success")
    return redirect(url_for("admin.events"))


@admin_bp.route("/events/<int:id>/update_meta", methods=["POST"])
@login_required
@secretary_or_admin_required
def update_event_meta(id):
    event = ConferenceEvent.query.get_or_404(id)
    if request.is_json:
        data = request.get_json()
        event.student_booking_allowed         = bool(data.get('student_booking_allowed', False))
        event.allow_duplicate_teacher_booking = bool(data.get('allow_duplicate_teacher_booking', False))
        if 'cancel_deadline_hours' in data:
            try:
                event.cancel_deadline_hours = max(0, int(data['cancel_deadline_hours']))
            except (ValueError, TypeError):
                pass
        db.session.commit()
        return jsonify({"ok": True})
    event.student_booking_allowed = request.form.get('student_booking_allowed') == 'y'
    db.session.commit()
    flash(_("Configuração atualizada."), "success")
    return redirect(url_for("admin.edit_event", id=id))


@admin_bp.route("/events/<int:id>/unpublish", methods=["POST"])
@login_required
@admin_required
def unpublish_event(id):
    event = ConferenceEvent.query.get_or_404(id)
    if event.status != 'published':
        flash(_("Apenas eventos publicados podem ser despublicados."), "warning")
        return redirect(url_for("admin.events"))
    for day in event.days:
        for slot in list(day.slots):
            db.session.delete(slot)
    event.status = "draft"
    db.session.commit()
    flash(_("Evento despublicado. Todos os horários e agendamentos foram removidos."), "warning")
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
@secretary_or_admin_required
def event_bookings(id):
    event = ConferenceEvent.query.get_or_404(id)
    bookings = (Booking.query
                .join(Slot).join(ConferenceDay)
                .filter(ConferenceDay.event_id == id, Booking.cancelled_at == None)
                .order_by(Slot.start_datetime)
                .all())
    teacher_ids_with_bookings = list({b.slot.teacher_id for b in bookings})

    # Build guardian data for each booking (student → guardians)
    student_ids = {b.student_id for b in bookings}
    from app.models import GuardianStudent
    gs_rows = GuardianStudent.query.filter(GuardianStudent.student_id.in_(student_ids)).all()
    guardian_ids_by_student = {}
    for gs in gs_rows:
        guardian_ids_by_student.setdefault(gs.student_id, []).append(gs.guardian_id)
    guardian_ids = {gid for gids in guardian_ids_by_student.values() for gid in gids}
    guardians_map = {u.id: u for u in User.query.filter(User.id.in_(guardian_ids)).all()} if guardian_ids else {}

    # JSON-friendly data for client-side filtering
    bookings_json = []
    for b in bookings:
        g_ids = guardian_ids_by_student.get(b.student_id, [])
        bookings_json.append({
            "id":           b.id,
            "teacher_id":   b.slot.teacher_id,
            "teacher_name": b.slot.teacher.full_name if b.slot.teacher else "",
            "student_id":   b.student_id,
            "student_name": b.student.full_name if b.student else "",
            "guardian_ids": g_ids,
        })

    # Unique lists for filter dropdowns
    teachers_list  = sorted({(b.slot.teacher_id, b.slot.teacher.full_name) for b in bookings if b.slot.teacher},  key=lambda x: x[1])
    students_list  = sorted({(b.student_id, b.student.full_name) for b in bookings if b.student}, key=lambda x: x[1])
    guardians_list = sorted({(gid, guardians_map[gid].full_name) for gid in guardian_ids if gid in guardians_map}, key=lambda x: x[1])

    today = date_type.today()
    is_past = (event.status == 'closed') or (bool(event.days) and event.days[-1].date < today)
    return render_template("admin/event_bookings.html",
                           event=event, bookings=bookings,
                           teacher_ids_with_bookings=teacher_ids_with_bookings,
                           bookings_json=bookings_json,
                           teachers_list=teachers_list,
                           students_list=students_list,
                           guardians_list=guardians_list,
                           guardian_ids_by_student=guardian_ids_by_student,
                           is_past=is_past)


@admin_bp.route("/events/<int:id>/export-students.csv")
@login_required
@secretary_or_admin_required
def export_event_students(id):
    event = ConferenceEvent.query.get_or_404(id)
    bookings = (Booking.query
                .join(Slot).join(ConferenceDay)
                .filter(ConferenceDay.event_id == id, Booking.cancelled_at == None)
                .all())
    # Count meetings per student
    counts = {}
    students = {}
    for b in bookings:
        sid = b.student_id
        counts[sid] = counts.get(sid, 0) + 1
        if sid not in students:
            students[sid] = b.student

    threshold  = max(1, int(request.args.get('threshold', 1) or 1))
    mode       = request.args.get('mode', 'all')   # all | gte | lte
    inc_count  = request.args.get('inc_count',  '0') == '1'
    inc_status = request.args.get('inc_status', '1') == '1'

    rows = []
    for sid, student in students.items():
        n = counts[sid]
        if mode == 'gte' and n < threshold:
            continue
        if mode == 'lte' and n > threshold:
            continue
        row = {'Nome': student.first_name, 'Sobrenome': student.last_name,
               'E-mail': student.email}
        if inc_count:
            row['Reuniões'] = n
        if inc_status:
            row['Status'] = _('Fez') if n >= threshold else _('Não fez')
        rows.append(row)

    rows.sort(key=lambda r: (r['Sobrenome'], r['Nome']))
    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    safe_name = re.sub(r'[^\w\-]', '_', event.name)
    return Response(output.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition':
                             f'attachment; filename="alunos_{safe_name}.csv"'})


@admin_bp.route("/events/<int:id>/print")
@login_required
@secretary_or_admin_required
def print_schedule(id):
    from collections import defaultdict
    event = ConferenceEvent.query.get_or_404(id)

    day_ids_param   = request.args.get("days", "")
    teacher_id_param = request.args.get("teacher", "")

    all_days = sorted(event.days, key=lambda d: d.date)

    if day_ids_param:
        selected_ids  = {int(x) for x in day_ids_param.split(",") if x.strip().isdigit()}
        selected_days = [d for d in all_days if d.id in selected_ids]
    else:
        selected_days = all_days

    day_id_set = {d.id for d in selected_days}

    # Booked, non-cancelled slots for the selected days
    raw_slots = (Slot.query
                 .join(ConferenceDay)
                 .filter(
                     ConferenceDay.event_id == id,
                     Slot.day_id.in_(day_id_set),
                     Slot.is_booked == True)
                 .order_by(Slot.start_datetime)
                 .all())
    booked_slots = [s for s in raw_slots if s.booking and not s.booking.cancelled_at]

    # Optionally filter to a single teacher
    if teacher_id_param and teacher_id_param.isdigit():
        booked_slots = [s for s in booked_slots if s.teacher_id == int(teacher_id_param)]

    # Group by teacher_id
    teacher_slot_map = defaultdict(list)
    for slot in booked_slots:
        teacher_slot_map[slot.teacher_id].append(slot)

    teacher_ids = list(teacher_slot_map.keys())
    teachers = (User.query.filter(User.id.in_(teacher_ids))
                .order_by(User.last_name, User.first_name).all())

    pages = [{"teacher": t, "slots": teacher_slot_map[t.id]} for t in teachers]

    return render_template("admin/print_schedule.html",
                           event=event, pages=pages, selected_days=selected_days)


def _save_event_days_and_slots(event, form):
    """Legacy helper kept for compatibility — new code uses _save_event_sectors."""
    teachers = User.query.filter_by(role="teacher", is_active=True).order_by(User.last_name, User.first_name).all()
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


def _build_sector_teachers_js(divisions):
    """
    For each division return a list of all active teachers annotated with
    whether they naturally belong to that sector (via TeacherSubjectGrade).
    Returns {str(div_id): [{id, name, in_sector}, ...], ...}
    """
    from collections import defaultdict
    grade_to_div = {g.id: g.division_id for g in GradeGroup.query.all() if g.division_id}
    teacher_divs = defaultdict(set)
    for tsg in TeacherSubjectGrade.query.all():
        div_id = grade_to_div.get(tsg.grade_group_id)
        if div_id:
            teacher_divs[tsg.teacher_id].add(div_id)

    all_teachers = (User.query.filter_by(role="teacher", is_active=True)
                    .order_by(User.last_name, User.first_name).all())
    result = {}
    for div in divisions:
        result[str(div.id)] = [
            {"id": t.id, "name": t.full_name,
             "in_sector": div.id in teacher_divs[t.id]}
            for t in all_teachers
        ]
    return result


def _build_existing_sectors(event):
    """
    Return existing_sectors dict for the template:
    {str(div_id): {start_time, end_time, slot_duration, break, dates[], teachers[]}}

    Also handles legacy events that have ConferenceDay records but no EventSector records.
    """
    existing = {}

    def _day_entry(day):
        return {
            "date":  day.date.strftime('%Y-%m-%d'),
            "start": day.start_time.strftime('%H:%M'),
            "end":   day.end_time.strftime('%H:%M'),
        }

    # ── From EventSector records (new system) ─────────────────────────────────
    for sector in event.sectors:
        div_key = str(sector.division_id) if sector.division_id is not None else "0"
        days = (ConferenceDay.query
                .filter_by(event_id=event.id, division_id=sector.division_id)
                .order_by(ConferenceDay.date).all())
        existing[div_key] = {
            "slot_duration": sector.slot_duration_minutes or 10,
            "break":         sector.break_minutes or 0,
            "days":          [_day_entry(d) for d in days],
            "teachers": [
                {"id": etc.teacher_id, "duration": etc.slot_duration_minutes}
                for etc in sector.teacher_configs
            ],
        }

    # ── Legacy orphaned days (old system, no EventSector) ─────────────────────
    seen_dates = {k: {e["date"] for e in v["days"]} for k, v in existing.items()}
    for day in event.days:
        div_key  = str(day.division_id) if day.division_id is not None else "0"
        date_str = day.date.strftime('%Y-%m-%d')
        if div_key in existing:
            if date_str not in seen_dates.get(div_key, set()):
                existing[div_key]["days"].append(_day_entry(day))
                seen_dates.setdefault(div_key, set()).add(date_str)
        else:
            existing[div_key] = {
                "slot_duration": day.slot_duration_minutes,
                "break":         day.break_minutes,
                "days":          [_day_entry(day)],
                "teachers":      [],
            }
            seen_dates[div_key] = {date_str}

    # Sort days by date within each sector
    for key in existing:
        existing[key]["days"].sort(key=lambda d: d["date"])
    return existing


def _build_existing_sectors_from_post():
    """
    Reconstruct existing_sectors from POST data so the form keeps user input
    when the server rejects the submission (e.g. missing day validation).
    """
    result = {}
    for key in request.form:
        m = re.match(r'^sector_(\d+)_slot_duration$', key)
        if not m:
            continue
        dk = m.group(1)
        dates  = request.form.getlist(f"sector_{dk}_day_dates[]")
        starts = request.form.getlist(f"sector_{dk}_day_starts[]")
        ends   = request.form.getlist(f"sector_{dk}_day_ends[]")
        days = []
        for d, s, e in zip(dates, starts, ends):
            if d.strip():
                days.append({"date": d.strip(), "start": s.strip(), "end": e.strip()})
        # Parse teachers
        teachers = []
        for tid_str in request.form.getlist(f"sector_{dk}_teachers[]"):
            try:
                tid = int(tid_str)
                dur_raw = request.form.get(f"sector_{dk}_teacher_{tid}_duration", "").strip()
                teachers.append({"id": tid, "duration": int(dur_raw) if dur_raw else None})
            except ValueError:
                pass
        result[dk] = {
            "slot_duration": int(request.form.get(f"sector_{dk}_slot_duration", 10) or 10),
            "break":         int(request.form.get(f"sector_{dk}_break", 0) or 0),
            "days":          days,
            "teachers":      teachers,
        }
    return result


def _save_event_sectors(event, conflict_action='keep'):
    """
    Parse per-sector form data (sector_{divId}_*) and persist:
      EventSector, EventSectorTeacher, ConferenceDay, Slot

    Returns a list of protected day dates (string, had bookings → not removed).
    """
    from datetime import time as time_type

    # ── Discover which division IDs are in the form ───────────────────────────
    div_ids_in_form = set()
    for key in request.form:
        m = re.match(r'^sector_(\d+)_slot_duration$', key)
        if m:
            div_ids_in_form.add(int(m.group(1)))

    # ── Remove sectors no longer present ─────────────────────────────────────
    for sector in list(event.sectors):
        sid = sector.division_id if sector.division_id is not None else 0
        if sid not in div_ids_in_form:
            for day in list(ConferenceDay.query.filter_by(
                    event_id=event.id, division_id=sector.division_id).all()):
                db.session.delete(day)
            db.session.delete(sector)
    db.session.flush()

    protected = []

    for div_id_key in div_ids_in_form:
        div_id = div_id_key if div_id_key != 0 else None  # 0 → NULL in DB

        # ── Parse sector constants (duration + break) ────────────────────────
        dur_raw = request.form.get(f"sector_{div_id_key}_slot_duration", "").strip()
        brk_raw = request.form.get(f"sector_{div_id_key}_break", "0").strip()
        try:
            slot_dur  = max(1, int(dur_raw) if dur_raw else 10)
            break_min = max(0, int(brk_raw) if brk_raw else 0)
        except (ValueError, TypeError):
            continue

        # ── Parse per-day times (date + start + end) ─────────────────────────
        dates_raw  = request.form.getlist(f"sector_{div_id_key}_day_dates[]")
        starts_raw = request.form.getlist(f"sector_{div_id_key}_day_starts[]")
        ends_raw   = request.form.getlist(f"sector_{div_id_key}_day_ends[]")

        # form_days: {date → (start_time, end_time)}
        form_days = {}
        for d_str, s_str, e_str in zip(dates_raw, starts_raw, ends_raw):
            d_str = (d_str or "").strip()
            s_str = (s_str or "").strip()
            e_str = (e_str or "").strip()
            if not (d_str and s_str and e_str):
                continue
            try:
                date  = datetime.strptime(d_str, '%Y-%m-%d').date()
                sh, sm = map(int, s_str.split(':'))
                eh, em = map(int, e_str.split(':'))
                form_days[date] = (time_type(sh, sm), time_type(eh, em))
            except (ValueError, TypeError):
                pass

        # ── Parse teacher selection ───────────────────────────────────────────
        selected_tids = set()
        for tid_str in request.form.getlist(f"sector_{div_id_key}_teachers[]"):
            try:
                selected_tids.add(int(tid_str))
            except ValueError:
                pass

        teacher_dur_overrides = {}
        for tid in selected_tids:
            raw = request.form.get(f"sector_{div_id_key}_teacher_{tid}_duration", "").strip()
            try:
                teacher_dur_overrides[tid] = int(raw) if raw else None
            except ValueError:
                teacher_dur_overrides[tid] = None

        # ── Get or create EventSector ─────────────────────────────────────────
        sector = EventSector.query.filter_by(
            event_id=event.id, division_id=div_id).first()
        if not sector:
            sector = EventSector(event_id=event.id, division_id=div_id)
            db.session.add(sector)
        sector.slot_duration_minutes = slot_dur
        sector.break_minutes         = break_min
        db.session.flush()

        # ── Update EventSectorTeacher ─────────────────────────────────────────
        sector_day_ids = [d.id for d in ConferenceDay.query.filter_by(
            event_id=event.id, division_id=div_id).all()]
        for etc in list(sector.teacher_configs):
            if etc.teacher_id not in selected_tids:
                if sector_day_ids:
                    TeacherBreak.query.filter(
                        TeacherBreak.teacher_id == etc.teacher_id,
                        TeacherBreak.day_id.in_(sector_day_ids)
                    ).delete(synchronize_session=False)
                db.session.delete(etc)
        db.session.flush()

        for tid in selected_tids:
            etc = EventSectorTeacher.query.filter_by(
                sector_id=sector.id, teacher_id=tid).first()
            if not etc:
                etc = EventSectorTeacher(sector_id=sector.id, teacher_id=tid)
                db.session.add(etc)
            etc.slot_duration_minutes = teacher_dur_overrides.get(tid)
        db.session.flush()

        # Build (User, duration) list for slot generation
        teacher_gen = []
        teacher_map = {t.id: t for t in
                       User.query.filter(User.id.in_(selected_tids)).all()}
        for etc in sector.teacher_configs:
            teacher = teacher_map.get(etc.teacher_id)
            if teacher:
                teacher_gen.append((teacher, etc.slot_duration_minutes or slot_dur))

        # ── Handle ConferenceDay records ──────────────────────────────────────
        existing_days = {
            day.date: day for day in
            ConferenceDay.query.filter_by(
                event_id=event.id, division_id=div_id).all()
        }

        # Remove days no longer in form
        for date, day in list(existing_days.items()):
            if date not in form_days:
                bk_count = db.session.query(Booking).join(Slot).filter(
                    Slot.day_id == day.id, Booking.cancelled_at == None).count()
                if bk_count and conflict_action == 'keep':
                    protected.append(date.strftime('%d/%m/%Y'))
                else:
                    if bk_count:
                        for slot in day.slots:
                            if slot.booking:
                                db.session.delete(slot.booking)
                    db.session.delete(day)
        db.session.flush()

        # Refresh after deletes
        existing_days = {
            day.date: day for day in
            ConferenceDay.query.filter_by(
                event_id=event.id, division_id=div_id).all()
        }

        # ── Create / update days and generate slots ───────────────────────────
        for date, (start_t, end_t) in sorted(form_days.items()):
            if date in existing_days:
                day = existing_days[date]
                timing_changed = (
                    day.start_time != start_t or day.end_time != end_t or
                    day.slot_duration_minutes != slot_dur or
                    day.break_minutes != break_min
                )
                existing_t_ids = {s.teacher_id for s in day.slots}
                teachers_changed = existing_t_ids != {t.id for t, _ in teacher_gen}

                day.start_time            = start_t
                day.end_time              = end_t
                day.slot_duration_minutes = slot_dur
                day.break_minutes         = break_min

            else:
                day = ConferenceDay(
                    event_id=event.id,
                    division_id=div_id,
                    date=date,
                    start_time=start_t,
                    end_time=end_t,
                    slot_duration_minutes=slot_dur,
                    break_minutes=break_min,
                )
                db.session.add(day)
                db.session.flush()

    return protected


def _generate_all_slots_for_event(event):
    """Generate slots for all sectors/days of a draft event being published."""
    for sector in event.sectors:
        slot_dur = sector.slot_duration_minutes
        break_min = sector.break_minutes
        teacher_map = {t.id: t for t in
                       User.query.filter(User.id.in_(
                           [etc.teacher_id for etc in sector.teacher_configs])).all()}
        teacher_gen = []
        for etc in sector.teacher_configs:
            teacher = teacher_map.get(etc.teacher_id)
            if teacher:
                teacher_gen.append((teacher, etc.slot_duration_minutes or slot_dur))
        if not teacher_gen:
            continue
        days = ConferenceDay.query.filter_by(
            event_id=event.id, division_id=sector.division_id).all()
        for day in days:
            # Build breaks set for this day
            day_breaks = TeacherBreak.query.filter_by(day_id=day.id).all()
            breaks_set = {(tb.teacher_id, tb.start_time) for tb in day_breaks} if day_breaks else None
            for s in list(day.slots):
                db.session.delete(s)
            db.session.flush()
            db.session.add_all(
                generate_slots_for_sector_day(day, teacher_gen, break_min, breaks_set=breaks_set))


# ── Notifications ──────────────────────────────────────────────────────────────

@admin_bp.route("/events/<int:event_id>/notify", methods=["GET", "POST"])
@login_required
@secretary_or_admin_required
def notify(event_id):
    event = ConferenceEvent.query.get_or_404(event_id)
    if request.method == "POST":
        params = {k: request.form.get(k, '') for k in
                  ('include_guardians', 'include_students', 'division_ids', 'grade_ids',
                   'min_children', 'not_notified')}
        recipients = _get_notify_recipients_v2(params, event_id)
        sent = 0
        for user in recipients:
            token = None
            if not user.has_password():
                token = generate_token(user.email, salt="invite")
                user.invite_token = token
                user.invite_sent_at = datetime.utcnow()
            try:
                send_conference_info_email(user, event, token)
                sent += 1
            except Exception:
                pass
        db.session.commit()
        flash(_("%(count)s e-mails enviados.", count=sent), "success")
        return redirect(url_for("admin.events"))

    divisions = Division.query.order_by(Division.order, Division.name).all()
    divisions_js = [
        {"id": d.id, "name": d.name,
         "grades": [{"id": g.id, "name": g.name}
                    for g in sorted(d.grade_groups, key=lambda g: g.name)]}
        for d in divisions
    ]
    return render_template("admin/notify.html", event=event, divisions_js=divisions_js)


@admin_bp.route("/events/<int:event_id>/notify/preview")
@login_required
@secretary_or_admin_required
def notify_preview(event_id):
    ConferenceEvent.query.get_or_404(event_id)
    params = {k: request.args.get(k, '') for k in
              ('include_guardians', 'include_students', 'division_ids', 'grade_ids',
               'min_children', 'not_notified')}
    recipients = _get_notify_recipients_v2(params, event_id)
    return jsonify({"count": len(recipients)})


def _parse_id_list(s):
    """Parse comma-separated integer string; return set or None (=all)."""
    if not s or s.strip() == '':
        return None
    try:
        ids = {int(x) for x in s.split(',') if x.strip()}
        return ids if ids else None
    except ValueError:
        return None


def _get_notify_recipients_v2(params, event_id):
    include_guardians = params.get('include_guardians', '1') == '1'
    include_students  = params.get('include_students',  '0') == '1'
    division_ids      = _parse_id_list(params.get('division_ids', ''))
    grade_ids_param   = _parse_id_list(params.get('grade_ids', ''))
    min_children      = int(params.get('min_children') or 1)
    not_notified      = params.get('not_notified') == '1'

    # Resolve grade_group_ids to filter by
    if grade_ids_param is not None:
        grade_ids = grade_ids_param
    elif division_ids is not None:
        grade_ids = {g.id for g in GradeGroup.query.filter(
            GradeGroup.division_id.in_(division_ids)).all()}
    else:
        grade_ids = None  # no grade filter

    # Students in scope
    sq = User.query.filter_by(role='student', is_active=True)
    if grade_ids is not None:
        sq = sq.join(StudentProfile, StudentProfile.user_id == User.id)\
               .filter(StudentProfile.grade_group_id.in_(grade_ids))
    students = sq.order_by(User.last_name, User.first_name).all()
    student_ids = {s.id for s in students}

    result = []

    if include_students:
        for s in students:
            if not_notified and EmailNotification.query.filter_by(
                    recipient_id=s.id, event_id=event_id).first():
                continue
            result.append(s)

    if include_guardians:
        if grade_ids is not None:
            gids = {gs.guardian_id for gs in
                    GuardianStudent.query.filter(
                        GuardianStudent.student_id.in_(student_ids)).all()}
            gq = User.query.filter(User.id.in_(gids),
                                   User.role == 'guardian', User.is_active == True)
        else:
            gq = User.query.filter_by(role='guardian', is_active=True)
        for g in gq.order_by(User.last_name, User.first_name).all():
            if GuardianStudent.query.filter_by(guardian_id=g.id).count() < min_children:
                continue
            if not_notified and EmailNotification.query.filter_by(
                    recipient_id=g.id, event_id=event_id).first():
                continue
            result.append(g)

    seen = set()
    return [r for r in result if not (r.id in seen or seen.add(r.id))]
