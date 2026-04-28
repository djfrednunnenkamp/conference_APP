from functools import wraps
from datetime import date
from flask import Blueprint, render_template, redirect, url_for, flash, abort, request
from flask_login import login_required, current_user
from flask_babel import _
from app.extensions import db
from app.models import Slot, ConferenceDay, ConferenceEvent, Booking
from app.teacher.forms import TeacherProfileForm
from app.utils import get_active_event, get_active_events

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
    events = get_active_events()
    today = date.today()

    # Find the nearest day (today or future) that has booked slots for this teacher
    next_day = None
    next_day_event = None
    next_day_slots = []
    total_upcoming = 0

    # Collect all upcoming booked slots across all active events
    for event in events:
        upcoming_slots = (Slot.query
                          .join(ConferenceDay)
                          .filter(ConferenceDay.event_id == event.id,
                                  ConferenceDay.date >= today,
                                  Slot.teacher_id == current_user.id,
                                  Slot.is_booked == True)
                          .order_by(Slot.start_datetime)
                          .all())
        upcoming_slots = [s for s in upcoming_slots if s.booking and not s.booking.cancelled_at]
        total_upcoming += len(upcoming_slots)

        # Find the earliest day with bookings
        for slot in upcoming_slots:
            slot_date = slot.day.date
            if next_day is None or slot_date < next_day:
                next_day = slot_date
                next_day_event = event

    # Load all slots for that next day (booked and available) to show the full picture
    if next_day and next_day_event:
        next_day_slots = (Slot.query
                          .join(ConferenceDay)
                          .filter(ConferenceDay.event_id == next_day_event.id,
                                  ConferenceDay.date == next_day,
                                  Slot.teacher_id == current_user.id)
                          .order_by(Slot.start_datetime)
                          .all())

    is_today = next_day == today if next_day else False

    return render_template("teacher/dashboard.html",
                           next_day=next_day,
                           next_day_event=next_day_event,
                           next_day_slots=next_day_slots,
                           is_today=is_today,
                           total_upcoming=total_upcoming,
                           events=events)


@teacher_bp.route("/schedule")
@login_required
@teacher_required
def schedule():
    events = get_active_events()

    # If an event is selected, show its days/slots
    event_id = request.args.get("event_id", type=int)
    selected_event = None
    days_data = []

    if event_id:
        selected_event = next((e for e in events if e.id == event_id), None)
        if selected_event:
            for day in sorted(selected_event.days, key=lambda d: d.date):
                slots = (Slot.query
                         .filter_by(day_id=day.id, teacher_id=current_user.id)
                         .order_by(Slot.start_datetime)
                         .all())
                days_data.append({"day": day, "slots": slots})

    # Build summary counts for the event list, sorted by nearest upcoming day
    today_date = date.today()
    events_summary = []
    for event in events:
        booked = (Slot.query
                  .join(ConferenceDay)
                  .filter(ConferenceDay.event_id == event.id,
                          Slot.teacher_id == current_user.id,
                          Slot.is_booked == True)
                  .count())
        total = (Slot.query
                 .join(ConferenceDay)
                 .filter(ConferenceDay.event_id == event.id,
                         Slot.teacher_id == current_user.id)
                 .count())
        # Nearest day (today or future), fallback to earliest past day
        sorted_days = sorted(event.days, key=lambda d: d.date)
        upcoming = [d for d in sorted_days if d.date >= today_date]
        nearest_day = upcoming[0].date if upcoming else (sorted_days[0].date if sorted_days else date.max)
        events_summary.append({"event": event, "booked": booked, "total": total, "nearest_day": nearest_day})

    events_summary.sort(key=lambda x: x["nearest_day"])

    return render_template("teacher/schedule.html",
                           events_summary=events_summary,
                           selected_event=selected_event,
                           days_data=days_data)


@teacher_bp.route("/print")
@login_required
@teacher_required
def print_schedule():
    events = get_active_events()
    if not events:
        abort(404)

    day_ids_param = request.args.get("days", "")
    selected_ids  = {int(x) for x in day_ids_param.split(",") if x.strip().isdigit()} if day_ids_param else None

    # Collect all selected days across all events
    all_selected_days = []
    for event in events:
        for day in sorted(event.days, key=lambda d: d.date):
            if selected_ids is None or day.id in selected_ids:
                all_selected_days.append(day)

    day_id_set = {d.id for d in all_selected_days}

    raw_slots = (Slot.query
                 .filter(
                     Slot.day_id.in_(day_id_set),
                     Slot.teacher_id == current_user.id,
                     Slot.is_booked == True)
                 .order_by(Slot.start_datetime)
                 .all())
    booked_slots = [s for s in raw_slots if s.booking and not s.booking.cancelled_at]

    # Use the first event for the header (most common case); all days listed
    pages = [{"teacher": current_user, "slots": booked_slots}]
    return render_template("admin/print_schedule.html",
                           event=events[0], pages=pages, selected_days=all_selected_days)


@teacher_bp.route("/profile")
@login_required
@teacher_required
def profile():
    return redirect(url_for("teacher.dashboard"))
