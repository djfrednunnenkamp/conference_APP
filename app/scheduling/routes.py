from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request, abort
from flask_login import login_required, current_user
from app.extensions import db
from app.models import (Slot, ConferenceDay, ConferenceEvent, Booking,
                        GuardianStudent, StudentProfile, TeacherSubjectGrade, User,
                        TeacherDayAbsence)

scheduling_bp = Blueprint("scheduling", __name__, url_prefix="/scheduling")


def _can_access_student(student_id):
    if current_user.role == "guardian":
        return GuardianStudent.query.filter_by(
            guardian_id=current_user.id, student_id=student_id).first() is not None
    if current_user.role == "student":
        return current_user.id == student_id
    if current_user.role == "admin":
        return True
    return False


@scheduling_bp.route("/slots/<int:event_id>/<int:student_id>")
@login_required
def get_slots(event_id, student_id):
    if not _can_access_student(student_id):
        abort(403)

    event = ConferenceEvent.query.get_or_404(event_id)
    student = User.query.get_or_404(student_id)
    sp = StudentProfile.query.filter_by(user_id=student_id).first()
    if not sp:
        return jsonify({"slots": []})

    teacher_ids = {tsg.teacher_id for tsg in
                   TeacherSubjectGrade.query.filter_by(grade_group_id=sp.grade_group_id).all()}

    # Collect absent teacher IDs per day for this event
    absent_pairs = (
        db.session.query(TeacherDayAbsence.day_id, TeacherDayAbsence.teacher_id)
        .join(ConferenceDay, TeacherDayAbsence.day_id == ConferenceDay.id)
        .filter(ConferenceDay.event_id == event_id)
        .all()
    )
    absent_set = {(d, t) for d, t in absent_pairs}

    slots = (Slot.query.join(ConferenceDay)
             .filter(ConferenceDay.event_id == event_id,
                     ConferenceDay.is_active == True,
                     Slot.teacher_id.in_(teacher_ids))
             .order_by(Slot.start_datetime)
             .all())

    # Filter out slots whose teacher is marked absent on that day (keep break slots)
    slots = [s for s in slots if s.is_break or (s.day_id, s.teacher_id) not in absent_set]

    my_bookings = {b.slot_id for b in
                   Booking.query.filter_by(student_id=student_id, cancelled_at=None).all()}

    # Build conflict ranges only from visible slots in THIS event (already filtered for
    # active days, non-absent teachers). Using my_bookings cross-event caused false
    # conflict stripes when another event or an absent teacher shared the same time.
    my_times = set()
    for s in slots:
        if not s.is_break and s.id in my_bookings:
            my_times.add((s.start_datetime, s.end_datetime))

    result = []
    for slot in slots:
        if slot.is_break:
            status = "break"
            booking_id = None
        elif slot.id in my_bookings:
            booking = Booking.query.filter_by(slot_id=slot.id, cancelled_at=None).first()
            status = "booked_by_me"
            booking_id = booking.id if booking else None
        elif slot.is_booked:
            status = "booked_by_others"
            booking_id = None
        else:
            conflict = any(
                s < slot.end_datetime and e > slot.start_datetime
                for s, e in my_times
            )
            status = "conflict" if conflict else "available"
            booking_id = None

        teacher = slot.teacher
        tsg = TeacherSubjectGrade.query.filter_by(
            teacher_id=slot.teacher_id, grade_group_id=sp.grade_group_id).first()
        subject_name = tsg.subject.name if tsg and tsg.subject else ""

        result.append({
            "slot_id": slot.id,
            "teacher_id": slot.teacher_id,
            "teacher_name": teacher.full_name if teacher else "",
            "subject": subject_name,
            "start": slot.start_datetime.isoformat(),
            "end": slot.end_datetime.isoformat(),
            "status": status,
            "booking_id": booking_id,
            "day_id": slot.day_id,
            "is_break": slot.is_break,
        })

    all_teachers = [
        {"id": t.id, "name": t.full_name}
        for t in User.query.filter_by(role="teacher", is_active=True)
                            .order_by(User.last_name, User.first_name).all()
    ]

    days_list = [
        {"id": d.id, "date": d.date.strftime('%Y-%m-%d'), "is_active": d.is_active}
        for d in sorted(event.days, key=lambda x: x.date)
    ]

    return jsonify({
        "slots": result,
        "days": days_list,
        "cancel_deadline_hours": event.cancel_deadline_hours,
        "allow_duplicate_teacher_booking": event.allow_duplicate_teacher_booking,
        "all_teachers": all_teachers,
    })


@scheduling_bp.route("/book", methods=["POST"])
@login_required
def book():
    data = request.get_json() or {}
    slot_id = data.get("slot_id")
    student_id = data.get("student_id")

    if not slot_id or not student_id:
        return jsonify({"error": "Missing slot_id or student_id"}), 400
    if not _can_access_student(student_id):
        return jsonify({"error": "Forbidden"}), 403

    slot = Slot.query.with_for_update().get(slot_id)
    if not slot:
        return jsonify({"error": "Slot not found"}), 404
    if slot.is_break:
        return jsonify({"error": "Slot is a break"}), 400
    if slot.is_booked:
        return jsonify({"error": "Slot already booked"}), 409

    day = ConferenceDay.query.get(slot.day_id)
    event = ConferenceEvent.query.get(day.event_id)
    if event.status != "published":
        return jsonify({"error": "Event not active"}), 409

    # Block booking when within the cancellation deadline window
    deadline = slot.start_datetime - timedelta(hours=event.cancel_deadline_hours)
    if datetime.utcnow() > deadline:
        return jsonify({"error": "Booking deadline passed"}), 409

    existing = (Booking.query.join(Slot)
                .filter(Booking.student_id == student_id,
                        Booking.cancelled_at == None,
                        Slot.start_datetime == slot.start_datetime)
                .first())
    if existing:
        return jsonify({"error": "Time conflict"}), 409

    # Reuse a previously cancelled booking for this slot if one exists.
    # Booking.slot_id has a unique constraint, so we cannot INSERT a second row.
    cancelled = Booking.query.filter(
        Booking.slot_id == slot_id,
        Booking.cancelled_at != None
    ).first()
    if cancelled:
        cancelled.cancelled_at = None
        cancelled.student_id = student_id
        cancelled.booked_by_id = current_user.id
        cancelled.booked_at = datetime.utcnow()
        slot.is_booked = True
        db.session.commit()
        return jsonify({"booking_id": cancelled.id}), 200

    booking = Booking(
        slot_id=slot_id,
        student_id=student_id,
        booked_by_id=current_user.id,
    )
    slot.is_booked = True
    db.session.add(booking)
    db.session.commit()
    return jsonify({"booking_id": booking.id}), 200


@scheduling_bp.route("/cancel/<int:booking_id>", methods=["POST"])
@login_required
def cancel(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if not _can_access_student(booking.student_id):
        return jsonify({"error": "Forbidden"}), 403
    if booking.cancelled_at:
        return jsonify({"error": "Already cancelled"}), 400

    slot = booking.slot
    day = ConferenceDay.query.get(slot.day_id)
    event = ConferenceEvent.query.get(day.event_id)
    deadline = slot.start_datetime - timedelta(hours=event.cancel_deadline_hours)
    if datetime.utcnow() > deadline:
        return jsonify({"error": "Cancellation deadline passed"}), 403

    booking.cancelled_at = datetime.utcnow()
    slot.is_booked = False
    db.session.commit()
    return jsonify({"ok": True}), 200
