"""Background scheduler tasks."""
from datetime import datetime, timedelta
from flask import current_app, render_template, url_for
from flask_mail import Message
from app.extensions import db, mail


def _attach_logo(msg):
    import os
    logo_path = os.path.join(os.path.dirname(__file__), "static", "img", "logo_email.png")
    with open(logo_path, "rb") as f:
        data = f.read()
    msg.attach(filename="logo.png", content_type="image/png", data=data,
               disposition="inline",
               headers={"Content-ID": "<logo>", "X-Attachment-Id": "logo"})


def _logo_data_uri():
    import os, base64
    logo_path = os.path.join(os.path.dirname(__file__), "static", "img", "logo_email.png")
    with open(logo_path, "rb") as f:
        data = f.read()
    return "data:image/png;base64," + base64.b64encode(data).decode()


def _log(user_id, email_type, event_id=None, body_html=None):
    try:
        from app.models import EmailNotification
        db.session.add(EmailNotification(
            recipient_id=user_id, type=email_type, event_id=event_id,
            body_html=body_html))
        db.session.commit()
    except Exception:
        pass


def _send_student_deadline_email(student, event, bookings):
    link = url_for("auth.login", _external=True)
    lang = getattr(student, "preferred_language", "pt")
    if lang == "en":
        subject = f"Your conference schedule: {event.name}"
        tmpl = "emails/deadline_student_en.html"
    else:
        subject = f"Seu cronograma de reuniões: {event.name}"
        tmpl = "emails/deadline_student_pt.html"
    body = render_template(tmpl, user=student, event=event,
                           bookings=bookings, link=link, logo_url="cid:logo")
    preview = render_template(tmpl, user=student, event=event,
                              bookings=bookings, link=link, logo_url=_logo_data_uri())
    msg = Message(subject=subject, recipients=[student.email], html=body)
    _attach_logo(msg)
    mail.send(msg)
    _log(student.id, "deadline_summary", event_id=event.id, body_html=preview)


def _send_guardian_deadline_email(guardian, event, children):
    """children: list of {'student': User, 'bookings': [Booking]}"""
    link = url_for("auth.login", _external=True)
    lang = getattr(guardian, "preferred_language", "pt")
    if lang == "en":
        subject = f"Conference schedule for your children: {event.name}"
        tmpl = "emails/deadline_guardian_en.html"
    else:
        subject = f"Cronograma de reuniões dos seus filhos: {event.name}"
        tmpl = "emails/deadline_guardian_pt.html"
    body = render_template(tmpl, user=guardian, event=event,
                           children=children, link=link, logo_url="cid:logo")
    preview = render_template(tmpl, user=guardian, event=event,
                              children=children, link=link, logo_url=_logo_data_uri())
    msg = Message(subject=subject, recipients=[guardian.email], html=body)
    _attach_logo(msg)
    mail.send(msg)
    _log(guardian.id, "deadline_summary", event_id=event.id, body_html=preview)


def send_deadline_emails_for_event(event):
    """Send schedule-summary emails to every affected student and guardian."""
    from app.models import (ConferenceDay, Slot, Booking, EventSector,
                            GradeGroup, StudentProfile, GuardianStudent, User)

    # Collect grade group IDs covered by this event
    division_ids = [s.division_id for s in event.sectors if s.division_id]
    if not division_ids:
        return

    grade_group_ids = [
        g.id for g in GradeGroup.query.filter(
            GradeGroup.division_id.in_(division_ids)).all()
    ]
    profiles = StudentProfile.query.filter(
        StudentProfile.grade_group_id.in_(grade_group_ids)).all()
    student_ids = [p.user_id for p in profiles]

    # Pre-fetch bookings per student
    bookings_by_student = {}
    for sid in student_ids:
        bookings_by_student[sid] = (
            Booking.query.join(Slot).join(ConferenceDay)
            .filter(ConferenceDay.event_id == event.id,
                    Booking.student_id == sid,
                    Booking.cancelled_at == None)
            .order_by(Slot.start_datetime).all()
        )

    # Email each active student
    for sid in student_ids:
        student = User.query.get(sid)
        if student and student.email and student.is_active:
            try:
                _send_student_deadline_email(
                    student, event, bookings_by_student[sid])
            except Exception as e:
                current_app.logger.error(
                    f"deadline email failed for student {sid}: {e}")

    # Collect children per guardian
    guardian_map = {}  # guardian_id → {'guardian': User, 'children': [...]}
    for sid in student_ids:
        for link in GuardianStudent.query.filter_by(student_id=sid).all():
            guardian = User.query.get(link.guardian_id)
            if not guardian or not guardian.email or not guardian.is_active:
                continue
            if guardian.id not in guardian_map:
                guardian_map[guardian.id] = {"guardian": guardian, "children": []}
            student = User.query.get(sid)
            if student:
                guardian_map[guardian.id]["children"].append({
                    "student": student,
                    "bookings": bookings_by_student[sid],
                })

    # Email each guardian
    for gdata in guardian_map.values():
        try:
            _send_guardian_deadline_email(
                gdata["guardian"], event, gdata["children"])
        except Exception as e:
            current_app.logger.error(
                f"deadline email failed for guardian {gdata['guardian'].id}: {e}")


def check_and_send_deadline_emails():
    """Called by APScheduler every 5 minutes."""
    from app.models import ConferenceEvent, ConferenceDay, Slot

    now = datetime.utcnow()
    events = ConferenceEvent.query.filter_by(
        status="published", deadline_email_enabled=True, deadline_email_sent=False).all()

    for event in events:
        earliest = (
            Slot.query.join(ConferenceDay)
            .filter(ConferenceDay.event_id == event.id, Slot.is_break == False)
            .order_by(Slot.start_datetime).first()
        )
        if not earliest:
            continue
        deadline = earliest.start_datetime - timedelta(
            hours=event.cancel_deadline_hours)
        if now < deadline:
            continue

        current_app.logger.info(
            f"Sending deadline emails for event {event.id} ({event.name})")
        send_deadline_emails_for_event(event)
        event.deadline_email_sent = True
        db.session.commit()
