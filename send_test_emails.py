"""
Send one test email for every template in the system.
Run from the project root:  python3 send_test_emails.py
"""
import os, sys
from datetime import date, time, datetime
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from app.extensions import mail
from flask_mail import Message
from flask import render_template

app = create_app()

TO = "test.frednunnenkamp@gmail.com"

# ── Fake objects ──────────────────────────────────────────────────────────────

class FakeUser:
    first_name = "Fred"
    last_name  = "Nunnenkamp"
    full_name  = "Fred Nunnenkamp"
    email      = TO
    preferred_language = "pt"

class FakeTeacher:
    full_name = "Prof. Ana Souza"

class FakeEvent:
    name = "Conferências de Pais e Mestres – 2025"

class FakeDay:
    date       = date(2025, 9, 15)
    start_time = time(8, 0)
    end_time   = time(17, 0)

class FakeSlot:
    start_datetime = datetime(2025, 9, 15, 9, 0)
    end_datetime   = datetime(2025, 9, 15, 9, 20)
    teacher        = FakeTeacher()

class FakeStudent:
    full_name = "Lucas Nunnenkamp"

class FakeBooking:
    slot    = FakeSlot()
    student = FakeStudent()

LINK       = "https://conferensia.example.com/auth/login"
TOKEN_LINK = "https://conferensia.example.com/auth/set-password/FAKE_TOKEN"

guardian  = FakeUser()
user      = FakeUser()
teacher   = FakeTeacher()
event     = FakeEvent()
day       = FakeDay()
bookings  = [FakeBooking(), FakeBooking()]

# ── Email definitions ─────────────────────────────────────────────────────────

emails = [
    {
        "label": "1/9 · Convite (invite) — EN",
        "subject": "[TEST] Welcome to Conferensia – Set your password",
        "template": "emails/invite_en.html",
        "ctx": {"user": user, "link": TOKEN_LINK},
    },
    {
        "label": "2/9 · Info da conferência — PT",
        "subject": "[TEST] Informações sobre as conferências: Conferências de Pais e Mestres – 2025",
        "template": "emails/conference_info_pt.html",
        "ctx": {"user": user, "event": event, "link": LINK},
    },
    {
        "label": "3/9 · Info da conferência — EN",
        "subject": "[TEST] Conference information: Parents & Teachers 2025",
        "template": "emails/conference_info_en.html",
        "ctx": {"user": user, "event": event, "link": LINK},
    },
    {
        "label": "4/9 · Lembrete de reuniões — PT",
        "subject": "[TEST] Lembrete de reuniões — Conferências · 15/09/2025",
        "template": "emails/reminder_pt.html",
        "ctx": {"guardian": guardian, "event": event, "day": day, "bookings": bookings, "link": LINK},
    },
    {
        "label": "5/9 · Lembrete de reuniões — EN",
        "subject": "[TEST] Meeting reminder — Conferências · 09/15/2025",
        "template": "emails/reminder_en.html",
        "ctx": {"guardian": guardian, "event": event, "day": day, "bookings": bookings, "link": LINK},
    },
    {
        "label": "6/9 · Redefinir senha — PT",
        "subject": "[TEST] Redefinir sua senha",
        "template": "emails/reset_pt.html",
        "ctx": {"user": user, "link": TOKEN_LINK},
    },
    {
        "label": "7/9 · Redefinir senha — EN",
        "subject": "[TEST] Reset your password",
        "template": "emails/reset_en.html",
        "ctx": {"user": user, "link": TOKEN_LINK},
    },
    {
        "label": "8/9 · Ausência de professor — PT",
        "subject": "[TEST] Aviso de ausência: Prof. Ana Souza — Conferências 2025",
        "template": "emails/teacher_absent_pt.html",
        "ctx": {"guardian": guardian, "teacher": teacher, "day": day, "bookings": bookings, "event": event, "link": LINK},
    },
    {
        "label": "9/9 · Ausência de professor — EN",
        "subject": "[TEST] Teacher absence notice: Prof. Ana Souza — Conferências 2025",
        "template": "emails/teacher_absent_en.html",
        "ctx": {"guardian": guardian, "teacher": teacher, "day": day, "bookings": bookings, "event": event, "link": LINK},
    },
]

# ── Send ──────────────────────────────────────────────────────────────────────

with app.app_context():
    for e in emails:
        try:
            body = render_template(e["template"], **e["ctx"])
            msg  = Message(subject=e["subject"], recipients=[TO], html=body)
            mail.send(msg)
            print(f"  ✅  {e['label']}")
        except Exception as ex:
            print(f"  ❌  {e['label']}  →  {ex}")

print(f"\nPronto! Verifique {TO}")
