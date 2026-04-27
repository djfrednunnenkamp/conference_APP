from functools import wraps
from datetime import date
from flask import Blueprint, render_template, redirect, url_for, flash, abort, request
from flask_login import login_required, current_user
from flask_babel import _
from app.extensions import db
from app.models import Slot, ConferenceDay, ConferenceEvent, Booking
from app.teacher.forms import TeacherProfileForm
from app.utils import get_active_event

teacher_bp = Blueprint("teacher", __name__, url_prefix="/teacher")


def teacher_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "teacher":
            abort(403)
        return f(*args, **kwargs)
    return decorated


@teacher_bp.route("/")
@login_required
@teacher_required
def dashboard():
    event = get_active_event()
    today = date.today()
    today_slots = []
    upcoming = []
    if event:
        today_slots = (Slot.query
                       .join(ConferenceDay)
                       .filter(ConferenceDay.event_id == event.id,
                               ConferenceDay.date == today,
                               Slot.teacher_id == current_user.id,
                               Slot.is_booked == True)
                       .order_by(Slot.start_datetime)
                       .all())
        upcoming = (Slot.query
                    .join(ConferenceDay)
                    .filter(ConferenceDay.event_id == event.id,
                            ConferenceDay.date > today,
                            Slot.teacher_id == current_user.id,
                            Slot.is_booked == True)
                    .order_by(Slot.start_datetime)
                    .all())
    return render_template("teacher/dashboard.html", event=event, today_slots=today_slots, upcoming=upcoming)


@teacher_bp.route("/schedule")
@login_required
@teacher_required
def schedule():
    event = get_active_event()
    date_filter = None
    slots = []
    if event:
        date_str = request.args.get("date")
        query = (Slot.query
                 .join(ConferenceDay)
                 .filter(ConferenceDay.event_id == event.id, Slot.teacher_id == current_user.id)
                 .order_by(Slot.start_datetime))
        if date_str:
            try:
                from datetime import date as date_type
                date_filter = date_type.fromisoformat(date_str)
                query = query.filter(ConferenceDay.date == date_filter)
            except ValueError:
                pass
        slots = query.all()
    return render_template("teacher/schedule.html", event=event, slots=slots, date_filter=date_filter)


@teacher_bp.route("/profile")
@login_required
@teacher_required
def profile():
    return redirect(url_for("teacher.dashboard"))
