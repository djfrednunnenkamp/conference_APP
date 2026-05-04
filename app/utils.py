from datetime import datetime, timedelta
from itsdangerous import URLSafeTimedSerializer
from flask import current_app, render_template, url_for
from flask_mail import Message
from app.extensions import mail, db


def _log_email(recipient_id, email_type, event_id=None):
    """Record a sent email in EmailNotification. Never raises — logging must not break mail flow."""
    try:
        from app.models import EmailNotification
        db.session.add(EmailNotification(
            recipient_id=recipient_id,
            type=email_type,
            event_id=event_id,
        ))
        db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass


def generate_token(email, salt="invite"):
    s = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    return s.dumps(email, salt=salt)


def verify_token(token, salt="invite", max_age=72 * 3600):
    s = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    try:
        email = s.loads(token, salt=salt, max_age=max_age)
        return email
    except Exception:
        return None


def send_invite_email(user, token):
    # First-access email is always in English so the user can understand it
    # regardless of their (not yet chosen) language preference.
    link = url_for("auth.set_password", token=token, _external=True)
    subject = "Welcome to Conferensia – Set your password"
    template = "emails/invite_en.html"
    body = render_template(template, user=user, link=link)
    msg = Message(subject=subject, recipients=[user.email], html=body)
    mail.send(msg)
    _log_email(user.id, "invite")


def send_conference_info_email(user, event, token=None):
    if token:
        link = url_for("auth.set_password", token=token, _external=True)
    else:
        link = url_for("auth.login", _external=True)

    lang = user.preferred_language
    if lang == "en":
        subject = f"Conference information: {event.name}"
        template = "emails/conference_info_en.html"
    else:
        subject = f"Informações sobre as conferências: {event.name}"
        template = "emails/conference_info_pt.html"

    body = render_template(template, user=user, event=event, link=link)
    msg = Message(subject=subject, recipients=[user.email], html=body)
    mail.send(msg)
    _log_email(user.id, "conference_info", event_id=event.id)


def send_reset_email(user, token):
    link = url_for("auth.reset_password", token=token, _external=True)
    lang = user.preferred_language
    if lang == "en":
        subject = "Reset your password"
        template = "emails/reset_en.html"
    else:
        subject = "Redefinir sua senha"
        template = "emails/reset_pt.html"

    body = render_template(template, user=user, link=link)
    msg = Message(subject=subject, recipients=[user.email], html=body)
    mail.send(msg)
    _log_email(user.id, "reset_password")


def generate_slots_for_day(day, teachers):
    """Generate Slot objects for a ConferenceDay and a list of teacher User objects."""
    from app.models import Slot
    slots = []
    start_dt = datetime.combine(day.date, day.start_time)
    end_dt = datetime.combine(day.date, day.end_time)
    step = timedelta(minutes=day.slot_duration_minutes + day.break_minutes)
    slot_duration = timedelta(minutes=day.slot_duration_minutes)

    current = start_dt
    while current + slot_duration <= end_dt:
        for teacher in teachers:
            slot = Slot(
                day_id=day.id,
                teacher_id=teacher.id,
                start_datetime=current,
                end_datetime=current + slot_duration,
                is_booked=False,
            )
            slots.append(slot)
        current += step

    return slots


def generate_slots_for_sector_day(day, teacher_configs, break_minutes):
    """
    Generate Slot objects for a ConferenceDay with per-teacher duration support.

    day             : ConferenceDay instance (already flushed, has .id and .date/.start_time/.end_time)
    teacher_configs : list of (User, slot_duration_minutes) tuples
    break_minutes   : break between slots in minutes (same for all teachers in the sector)
    """
    from app.models import Slot
    slots = []
    for teacher, duration_min in teacher_configs:
        if not duration_min or duration_min <= 0:
            continue
        start_dt = datetime.combine(day.date, day.start_time)
        end_dt   = datetime.combine(day.date, day.end_time)
        step     = timedelta(minutes=duration_min + (break_minutes or 0))
        slot_dur = timedelta(minutes=duration_min)
        if step.total_seconds() <= 0:
            continue
        current = start_dt
        guard   = 500   # safety cap
        while current + slot_dur <= end_dt and guard > 0:
            slots.append(Slot(
                day_id=day.id,
                teacher_id=teacher.id,
                start_datetime=current,
                end_datetime=current + slot_dur,
                is_booked=False,
            ))
            current += step
            guard  -= 1
    return slots


def send_teacher_absent_email(guardian, teacher, day, bookings, event):
    """Email to a guardian when a teacher they have meetings with is marked absent."""
    link = url_for("auth.login", _external=True)
    lang = guardian.preferred_language
    if lang == "en":
        subject = f"Teacher absence notice: {teacher.full_name} — {event.name}"
        template = "emails/teacher_absent_en.html"
    else:
        subject = f"Aviso de ausência: Prof. {teacher.full_name} — {event.name}"
        template = "emails/teacher_absent_pt.html"
    body = render_template(template, guardian=guardian, teacher=teacher,
                           day=day, bookings=bookings, event=event, link=link)
    msg = Message(subject=subject, recipients=[guardian.email], html=body)
    mail.send(msg)
    _log_email(guardian.id, "teacher_absent", event_id=event.id)


def send_booking_reminder_email(guardian, event, day, bookings):
    """Reminder email with a summary of confirmed meetings for a given conference day."""
    link = url_for("auth.login", _external=True)
    lang = guardian.preferred_language
    if lang == "en":
        subject = f"Meeting reminder — {event.name} · {day.date.strftime('%d/%m/%Y')}"
        template = "emails/reminder_en.html"
    else:
        subject = f"Lembrete de reuniões — {event.name} · {day.date.strftime('%d/%m/%Y')}"
        template = "emails/reminder_pt.html"
    body = render_template(template, guardian=guardian, event=event,
                           day=day, bookings=bookings, link=link)
    msg = Message(subject=subject, recipients=[guardian.email], html=body)
    mail.send(msg)
    _log_email(guardian.id, "reminder", event_id=event.id)


def get_active_event():
    from app.models import ConferenceEvent
    return ConferenceEvent.query.filter_by(status="published").order_by(ConferenceEvent.name).first()


def get_active_events():
    from app.models import ConferenceEvent
    return ConferenceEvent.query.filter_by(status="published").order_by(ConferenceEvent.name).all()
