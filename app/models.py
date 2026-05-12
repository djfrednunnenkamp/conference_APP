from datetime import datetime
from flask_login import UserMixin
from app.extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255))
    role = db.Column(db.Enum("admin", "teacher", "student", "guardian", "secretary"), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    invite_token = db.Column(db.String(255))
    invite_sent_at = db.Column(db.DateTime)
    preferred_language = db.Column(db.Enum("pt", "en"), default="pt", nullable=False)

    teacher_profile = db.relationship("TeacherProfile", uselist=False, back_populates="user", cascade="all, delete-orphan")
    student_profile = db.relationship("StudentProfile", uselist=False, back_populates="user", cascade="all, delete-orphan")
    guardian_students = db.relationship("GuardianStudent", foreign_keys="GuardianStudent.guardian_id", back_populates="guardian", cascade="all, delete-orphan")
    student_guardians = db.relationship("GuardianStudent", foreign_keys="GuardianStudent.student_id", back_populates="student", cascade="all, delete-orphan")
    email_notifications = db.relationship("EmailNotification", back_populates="recipient", cascade="all, delete-orphan")

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def has_password(self):
        return self.password_hash is not None


class TeacherProfile(db.Model):
    __tablename__ = "teacher_profile"

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), primary_key=True)
    bio = db.Column(db.Text)

    user = db.relationship("User", back_populates="teacher_profile")
    subject_grades = db.relationship(
        "TeacherSubjectGrade",
        primaryjoin="TeacherProfile.user_id == foreign(TeacherSubjectGrade.teacher_id)",
        cascade="all, delete-orphan",
        viewonly=False,
    )


class Subject(db.Model):
    __tablename__ = "subject"

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(100), nullable=False)
    division_id = db.Column(db.Integer, db.ForeignKey("division.id", ondelete="SET NULL"), nullable=True)

    division               = db.relationship("Division", back_populates="subjects")
    teacher_subject_grades = db.relationship("TeacherSubjectGrade", back_populates="subject")
    grade_subjects         = db.relationship("GradeGroupSubject", back_populates="subject", cascade="all, delete-orphan")

    __table_args__ = (db.UniqueConstraint("name", "division_id", name="uq_subject_name_division"),)


class Division(db.Model):
    """School division / sector (e.g. High School, Middle School, Fundamental, Pre-School)."""
    __tablename__ = "division"

    id    = db.Column(db.Integer, primary_key=True)
    name  = db.Column(db.String(100), nullable=False, unique=True)
    order = db.Column(db.Integer, default=0, nullable=False)

    grade_groups    = db.relationship("GradeGroup",   back_populates="division")
    subjects        = db.relationship("Subject",      back_populates="division")
    conference_days = db.relationship("ConferenceDay", back_populates="division")


class GradeGroup(db.Model):
    __tablename__ = "grade_group"

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(100), nullable=False, unique=True)
    division_id = db.Column(db.Integer, db.ForeignKey("division.id", ondelete="SET NULL"), nullable=True)
    order       = db.Column(db.Integer, default=0, nullable=False)

    division             = db.relationship("Division", back_populates="grade_groups")
    student_profiles     = db.relationship("StudentProfile",      back_populates="grade_group")
    teacher_subject_grades = db.relationship("TeacherSubjectGrade", back_populates="grade_group")
    grade_subjects       = db.relationship("GradeGroupSubject",   back_populates="grade_group", cascade="all, delete-orphan")


class GradeGroupSubject(db.Model):
    """Which subjects are offered in each grade group."""
    __tablename__ = "grade_group_subject"

    id = db.Column(db.Integer, primary_key=True)
    grade_group_id = db.Column(db.Integer, db.ForeignKey("grade_group.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False)

    grade_group = db.relationship("GradeGroup", back_populates="grade_subjects")
    subject = db.relationship("Subject", back_populates="grade_subjects")

    __table_args__ = (db.UniqueConstraint("grade_group_id", "subject_id"),)


class TeacherSubjectGrade(db.Model):
    __tablename__ = "teacher_subject_grade"

    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False)
    grade_group_id = db.Column(db.Integer, db.ForeignKey("grade_group.id"), nullable=False)

    teacher = db.relationship("User", foreign_keys=[teacher_id], overlaps="subject_grades")
    subject = db.relationship("Subject", back_populates="teacher_subject_grades")
    grade_group = db.relationship("GradeGroup", back_populates="teacher_subject_grades")

    __table_args__ = (
        db.UniqueConstraint("teacher_id", "subject_id", "grade_group_id"),
    )


class StudentProfile(db.Model):
    __tablename__ = "student_profile"

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), primary_key=True)
    grade_group_id = db.Column(db.Integer, db.ForeignKey("grade_group.id"), nullable=False)

    user = db.relationship("User", back_populates="student_profile")
    grade_group = db.relationship("GradeGroup", back_populates="student_profiles")


class StudentSubjectExclusion(db.Model):
    """Records a subject that a student is excluded from (opt-out from their grade's default subjects)."""
    __tablename__ = "student_subject_exclusion"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False)

    __table_args__ = (db.UniqueConstraint("student_id", "subject_id"),)


class GuardianStudent(db.Model):
    __tablename__ = "guardian_student"

    id = db.Column(db.Integer, primary_key=True)
    guardian_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    guardian = db.relationship("User", foreign_keys=[guardian_id], back_populates="guardian_students")
    student = db.relationship("User", foreign_keys=[student_id], back_populates="student_guardians")

    __table_args__ = (
        db.UniqueConstraint("guardian_id", "student_id"),
    )


class ConferenceEvent(db.Model):
    __tablename__ = "conference_event"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    student_booking_allowed           = db.Column(db.Boolean, default=False, nullable=False)
    allow_duplicate_teacher_booking   = db.Column(db.Boolean, default=False, nullable=False)
    cancel_deadline_hours             = db.Column(db.Integer, default=24, nullable=False)
    deadline_email_enabled            = db.Column(db.Boolean, default=True,  nullable=False, server_default='1')
    deadline_email_sent               = db.Column(db.Boolean, default=False, nullable=False)
    status = db.Column(db.Enum("draft", "published", "closed"), default="draft", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    days = db.relationship("ConferenceDay", back_populates="event", cascade="all, delete-orphan", order_by="ConferenceDay.date")
    sectors = db.relationship("EventSector", back_populates="event", cascade="all, delete-orphan")
    email_notifications = db.relationship("EmailNotification", back_populates="event", cascade="all, delete-orphan")


class ConferenceDay(db.Model):
    __tablename__ = "conference_day"

    id                    = db.Column(db.Integer, primary_key=True)
    event_id              = db.Column(db.Integer, db.ForeignKey("conference_event.id"), nullable=False)
    division_id           = db.Column(db.Integer, db.ForeignKey("division.id", ondelete="SET NULL"), nullable=True)
    date                  = db.Column(db.Date, nullable=False)
    start_time            = db.Column(db.Time, nullable=False)
    end_time              = db.Column(db.Time, nullable=False)
    slot_duration_minutes = db.Column(db.Integer, nullable=False)
    break_minutes         = db.Column(db.Integer, default=0, nullable=False)
    is_active             = db.Column(db.Boolean, default=True, nullable=False, server_default='1')

    event    = db.relationship("ConferenceEvent", back_populates="days")
    division = db.relationship("Division", back_populates="conference_days")
    slots    = db.relationship("Slot",              back_populates="day", cascade="all, delete-orphan")
    absences = db.relationship("TeacherDayAbsence", back_populates="day", cascade="all, delete-orphan")
    teacher_overrides = db.relationship("TeacherDayOverride", back_populates="day", cascade="all, delete-orphan")
    breaks   = db.relationship("TeacherBreak", back_populates="day", cascade="all, delete-orphan")


class TeacherDayAbsence(db.Model):
    """Records a teacher as absent/excluded for a specific conference day."""
    __tablename__ = "teacher_day_absence"

    id = db.Column(db.Integer, primary_key=True)
    day_id = db.Column(db.Integer, db.ForeignKey("conference_day.id"), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    day = db.relationship("ConferenceDay", back_populates="absences")
    teacher = db.relationship("User")

    __table_args__ = (db.UniqueConstraint("day_id", "teacher_id"),)


class TeacherDayOverride(db.Model):
    """Per-teacher slot duration override for a specific conference day (e.g. advisors)."""
    __tablename__ = "teacher_day_override"

    id                    = db.Column(db.Integer, primary_key=True)
    day_id                = db.Column(db.Integer, db.ForeignKey("conference_day.id"), nullable=False)
    teacher_id            = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    slot_duration_minutes = db.Column(db.Integer, nullable=False)

    day     = db.relationship("ConferenceDay", back_populates="teacher_overrides")
    teacher = db.relationship("User")

    __table_args__ = (db.UniqueConstraint("day_id", "teacher_id"),)


class Slot(db.Model):
    __tablename__ = "slot"

    id = db.Column(db.Integer, primary_key=True)
    day_id = db.Column(db.Integer, db.ForeignKey("conference_day.id"), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    start_datetime = db.Column(db.DateTime, nullable=False)
    end_datetime = db.Column(db.DateTime, nullable=False)
    is_booked = db.Column(db.Boolean, default=False, nullable=False)
    is_break = db.Column(db.Boolean, default=False, nullable=False, server_default='0')

    day = db.relationship("ConferenceDay", back_populates="slots")
    teacher = db.relationship("User")
    booking = db.relationship("Booking", uselist=False, back_populates="slot", cascade="all, delete-orphan")


class Booking(db.Model):
    __tablename__ = "booking"

    id = db.Column(db.Integer, primary_key=True)
    slot_id = db.Column(db.Integer, db.ForeignKey("slot.id"), unique=True, nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    booked_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    booked_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    cancelled_at = db.Column(db.DateTime)

    slot = db.relationship("Slot", back_populates="booking")
    student = db.relationship("User", foreign_keys=[student_id])
    booked_by = db.relationship("User", foreign_keys=[booked_by_id])

    @property
    def is_cancelled(self):
        return self.cancelled_at is not None


class EventReminder(db.Model):
    """Configures a booking-summary email sent X hours before each conference day."""
    __tablename__ = "event_reminder"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("conference_event.id", ondelete="CASCADE"), nullable=False)
    hours_before = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    event = db.relationship("ConferenceEvent", backref=db.backref("reminders", cascade="all, delete-orphan", order_by="EventReminder.hours_before"))


class EmailNotification(db.Model):
    __tablename__ = "email_notification"

    id = db.Column(db.Integer, primary_key=True)
    # event_id is optional — emails like invites and resets are not tied to an event
    event_id = db.Column(db.Integer, db.ForeignKey("conference_event.id", ondelete="SET NULL"), nullable=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    type = db.Column(db.String(32), nullable=False)   # invite | conference_info | reminder | reset_password | teacher_absent
    body_html = db.Column(db.Text, nullable=True)

    event = db.relationship("ConferenceEvent", back_populates="email_notifications")
    recipient = db.relationship("User", back_populates="email_notifications")


class EventSector(db.Model):
    """Per-sector schedule configuration (timing defaults + teacher list) for a conference event."""
    __tablename__ = "event_sector"

    id                    = db.Column(db.Integer, primary_key=True)
    event_id              = db.Column(db.Integer, db.ForeignKey("conference_event.id", ondelete="CASCADE"), nullable=False)
    division_id           = db.Column(db.Integer, db.ForeignKey("division.id", ondelete="SET NULL"), nullable=True)
    start_time            = db.Column(db.Time, nullable=True)
    end_time              = db.Column(db.Time, nullable=True)
    slot_duration_minutes = db.Column(db.Integer, nullable=True)
    break_minutes         = db.Column(db.Integer, default=0, nullable=True)

    event           = db.relationship("ConferenceEvent", back_populates="sectors")
    division        = db.relationship("Division")
    teacher_configs = db.relationship("EventSectorTeacher", back_populates="sector",
                                      cascade="all, delete-orphan")

    __table_args__ = (db.UniqueConstraint("event_id", "division_id", name="uq_event_sector"),)


class EventSectorTeacher(db.Model):
    """Teacher assignment + optional slot-duration override within a sector for a conference event."""
    __tablename__ = "event_sector_teacher"

    id                    = db.Column(db.Integer, primary_key=True)
    sector_id             = db.Column(db.Integer, db.ForeignKey("event_sector.id", ondelete="CASCADE"), nullable=False)
    teacher_id            = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    slot_duration_minutes = db.Column(db.Integer, nullable=True)   # NULL = inherit from sector

    sector  = db.relationship("EventSector", back_populates="teacher_configs")
    teacher = db.relationship("User")

    __table_args__ = (db.UniqueConstraint("sector_id", "teacher_id", name="uq_sector_teacher"),)


class TeacherBreak(db.Model):
    """A blocked time slot (break) for a teacher on a specific conference day."""
    __tablename__ = 'teacher_break'

    id         = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    day_id     = db.Column(db.Integer, db.ForeignKey('conference_day.id', ondelete='CASCADE'), nullable=False)
    start_time = db.Column(db.Time, nullable=False)

    teacher = db.relationship('User', foreign_keys=[teacher_id])
    day     = db.relationship('ConferenceDay', back_populates='breaks', foreign_keys=[day_id])

    __table_args__ = (db.UniqueConstraint('teacher_id', 'day_id', 'start_time', name='uq_teacher_break'),)


class SecretaryDivision(db.Model):
    """Maps a secretary user to the divisions they manage."""
    __tablename__ = 'secretary_division'

    id           = db.Column(db.Integer, primary_key=True)
    secretary_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    division_id  = db.Column(db.Integer, db.ForeignKey('division.id', ondelete='CASCADE'), nullable=False)

    secretary = db.relationship('User',     foreign_keys=[secretary_id])
    division  = db.relationship('Division', foreign_keys=[division_id])

    __table_args__ = (db.UniqueConstraint('secretary_id', 'division_id', name='uq_secretary_division'),)
