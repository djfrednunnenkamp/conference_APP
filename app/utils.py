from datetime import datetime, timedelta
from itsdangerous import URLSafeTimedSerializer
from flask import current_app, render_template, url_for
from flask_mail import Message
from app.extensions import mail, db


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


def get_active_event():
    from app.models import ConferenceEvent
    return ConferenceEvent.query.filter_by(status="published").order_by(ConferenceEvent.created_at.desc()).first()


def get_active_events():
    from app.models import ConferenceEvent
    return ConferenceEvent.query.filter_by(status="published").order_by(ConferenceEvent.created_at.desc()).all()
