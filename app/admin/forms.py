from flask_wtf import FlaskForm
from wtforms import (StringField, SelectField, BooleanField, IntegerField,
                     SubmitField, TextAreaField, DateField, TimeField, FieldList, FormField)
from wtforms.validators import DataRequired, Email, Optional, NumberRange


class GradeGroupForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired()])
    submit = SubmitField("Save")


class SubjectForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired()])
    submit = SubmitField("Save")


class TeacherForm(FlaskForm):
    first_name = StringField("First Name", validators=[DataRequired()])
    last_name = StringField("Last Name", validators=[DataRequired()])
    email = StringField("Email", validators=[DataRequired(), Email()])
    submit = SubmitField("Save")


class StudentForm(FlaskForm):
    first_name = StringField("First Name", validators=[DataRequired()])
    last_name = StringField("Last Name", validators=[DataRequired()])
    email = StringField("Email", validators=[DataRequired(), Email()])
    grade_group_id = SelectField("Grade Group", coerce=int, validators=[DataRequired()])
    submit = SubmitField("Save")


class GuardianForm(FlaskForm):
    first_name = StringField("First Name", validators=[DataRequired()])
    last_name = StringField("Last Name", validators=[DataRequired()])
    email = StringField("Email", validators=[DataRequired(), Email()])
    submit = SubmitField("Save")


class AdminForm(FlaskForm):
    first_name = StringField("First Name", validators=[DataRequired()])
    last_name = StringField("Last Name", validators=[DataRequired()])
    email = StringField("Email", validators=[DataRequired(), Email()])
    submit = SubmitField("Save")


class ConferenceDaySubForm(FlaskForm):
    class Meta:
        csrf = False

    date = DateField("Date", validators=[DataRequired()])
    start_time = TimeField("Start Time", validators=[DataRequired()])
    end_time = TimeField("End Time", validators=[DataRequired()])
    slot_duration_minutes = IntegerField("Slot Duration (min)", validators=[DataRequired(), NumberRange(min=1)], default=10)
    break_minutes = IntegerField("Break (min)", validators=[Optional(), NumberRange(min=0)], default=0)


class ConferenceEventForm(FlaskForm):
    name = StringField("Event Name", validators=[DataRequired()])
    student_booking_allowed = BooleanField("Allow student booking")
    cancel_deadline_hours = IntegerField("Cancellation deadline (hours)", validators=[DataRequired(), NumberRange(min=0)], default=24)
    days = FieldList(FormField(ConferenceDaySubForm), min_entries=1)
    submit = SubmitField("Save")


class NotifyForm(FlaskForm):
    all_guardians = BooleanField("All guardians")
    not_yet_notified = BooleanField("Guardians not yet notified for this event")
    multiple_children = BooleanField("Guardians with 2+ children")
    grade_group_id = SelectField("By grade group", coerce=int)
    submit = SubmitField("Send Emails")
