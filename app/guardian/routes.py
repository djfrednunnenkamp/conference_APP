from functools import wraps
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, abort, request, jsonify
from flask_login import login_required, current_user
from flask_babel import _
from app.models import GuardianStudent, User, StudentProfile, Booking, Slot, ConferenceDay, ConferenceEvent
from app.utils import get_active_events, send_conference_info_email, send_guardian_bookings_email

guardian_bp = Blueprint("guardian", __name__, url_prefix="/guardian")


def guardian_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "guardian":
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _assert_guardian_owns_student(student_id):
    link = GuardianStudent.query.filter_by(
        guardian_id=current_user.id, student_id=student_id).first()
    if not link:
        abort(403)
    return link


@guardian_bp.route("/")
@login_required
@guardian_required
def dashboard():
    events = get_active_events()
    links = (GuardianStudent.query.filter_by(guardian_id=current_user.id)
             .join(User, GuardianStudent.student_id == User.id)
             .order_by(User.last_name, User.first_name).all())
    children = []
    for link in links:
        student = User.query.get(link.student_id)
        event_counts = []
        for event in events:
            booked = (Booking.query.join(Slot).join(ConferenceDay)
                      .filter(ConferenceDay.event_id == event.id,
                              Booking.student_id == student.id,
                              Booking.cancelled_at == None).count())
            event_counts.append({"event": event, "booked": booked})
        children.append({"student": student, "event_counts": event_counts})
    return render_template("guardian/dashboard.html", events=events, children=children)


@guardian_bp.route("/schedule/<int:student_id>/<int:event_id>")
@login_required
@guardian_required
def schedule(student_id, event_id):
    _assert_guardian_owns_student(student_id)
    student = User.query.get_or_404(student_id)
    event = ConferenceEvent.query.get_or_404(event_id)
    if event.status != "published":
        flash(_("Nenhum evento de conferência ativo."), "info")
        return redirect(url_for("guardian.dashboard"))
    return render_template("guardian/schedule.html", event=event, student=student)


@guardian_bp.route("/print")
@login_required
@guardian_required
def print_schedule():
    student_id = request.args.get("student_id", type=int)
    if not student_id:
        abort(400)
    _assert_guardian_owns_student(student_id)
    student = User.query.get_or_404(student_id)
    events = get_active_events()
    events_data = []
    for event in events:
        bkgs = (Booking.query.join(Slot).join(ConferenceDay)
                .filter(ConferenceDay.event_id == event.id,
                        Booking.student_id == student.id,
                        Booking.cancelled_at == None)
                .order_by(Slot.start_datetime).all())
        if bkgs:
            events_data.append({"event": event, "bookings": bkgs})
    return render_template("print_my_schedule.html",
                           student=student, events_data=events_data,
                           now=datetime.utcnow())


@guardian_bp.route("/send-schedule-email/<int:student_id>/<int:event_id>", methods=["POST"])
@login_required
@guardian_required
def send_schedule_email(student_id, event_id):
    _assert_guardian_owns_student(student_id)
    event = ConferenceEvent.query.get_or_404(event_id)
    send_conference_info_email(current_user, event)
    return jsonify({"ok": True}), 200


@guardian_bp.route("/send-bookings-email", methods=["POST"])
@login_required
@guardian_required
def send_bookings_email():
    events = get_active_events()
    links = (GuardianStudent.query.filter_by(guardian_id=current_user.id)
             .join(User, GuardianStudent.student_id == User.id)
             .order_by(User.last_name, User.first_name).all())
    children_data = []
    for link in links:
        student = User.query.get(link.student_id)
        events_bookings = []
        for event in events:
            bkgs = (Booking.query.join(Slot).join(ConferenceDay)
                    .filter(ConferenceDay.event_id == event.id,
                            Booking.student_id == student.id,
                            Booking.cancelled_at == None)
                    .order_by(Slot.start_datetime).all())
            if bkgs:
                events_bookings.append({"event": event, "bookings": bkgs})
        if events_bookings:
            children_data.append({"student": student, "events_bookings": events_bookings})
    if not children_data:
        return jsonify({"error": "Nenhuma reunião agendada para enviar."}), 400
    send_guardian_bookings_email(current_user, children_data)
    return jsonify({"ok": True}), 200


@guardian_bp.route("/bookings")
@login_required
@guardian_required
def bookings():
    events = get_active_events()
    past_events = ConferenceEvent.query.filter_by(status="closed").order_by(ConferenceEvent.name).all()
    links = (GuardianStudent.query.filter_by(guardian_id=current_user.id)
             .join(User, GuardianStudent.student_id == User.id)
             .order_by(User.last_name, User.first_name).all())
    children_data = []
    for link in links:
        student = User.query.get(link.student_id)
        events_bookings = []
        for event in events:
            bkgs = (Booking.query.join(Slot).join(ConferenceDay)
                    .filter(ConferenceDay.event_id == event.id,
                            Booking.student_id == student.id,
                            Booking.cancelled_at == None)
                    .order_by(Slot.start_datetime).all())
            events_bookings.append({"event": event, "bookings": bkgs})
        past_events_bookings = []
        for event in past_events:
            bkgs = (Booking.query.join(Slot).join(ConferenceDay)
                    .filter(ConferenceDay.event_id == event.id,
                            Booking.student_id == student.id,
                            Booking.cancelled_at == None)
                    .order_by(Slot.start_datetime).all())
            if bkgs:
                past_events_bookings.append({"event": event, "bookings": bkgs})
        children_data.append({
            "student": student,
            "events_bookings": events_bookings,
            "past_events_bookings": past_events_bookings,
        })
    return render_template("guardian/bookings.html", children_data=children_data)
