from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, abort
from flask_login import login_required, current_user
from app.models import Booking, Slot, ConferenceDay, ConferenceEvent
from app.utils import get_active_events

student_bp = Blueprint("student", __name__, url_prefix="/student")


def student_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "student":
            abort(403)
        return f(*args, **kwargs)
    return decorated


@student_bp.route("/")
@login_required
@student_required
def dashboard():
    events = get_active_events()
    return render_template("student/dashboard.html", events=events)


@student_bp.route("/schedule/<int:event_id>")
@login_required
@student_required
def schedule(event_id):
    event = ConferenceEvent.query.get_or_404(event_id)
    if event.status != "published" or not event.student_booking_allowed:
        return redirect(url_for("student.dashboard"))
    return render_template("student/schedule.html", event=event, student=current_user)


@student_bp.route("/bookings")
@login_required
@student_required
def bookings():
    events = get_active_events()
    events_bookings = []
    for event in events:
        bkgs = (Booking.query
                .join(Slot).join(ConferenceDay)
                .filter(ConferenceDay.event_id == event.id,
                        Booking.student_id == current_user.id,
                        Booking.cancelled_at == None)
                .order_by(Slot.start_datetime)
                .all())
        events_bookings.append({"event": event, "bookings": bkgs})
    return render_template("student/bookings.html", events_bookings=events_bookings)
