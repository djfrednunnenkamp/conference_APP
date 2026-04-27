"""Run once to create the first admin user: python seed_admin.py"""
from app import create_app
from app.extensions import db, bcrypt
from app.models import User

app = create_app()

with app.app_context():
    if User.query.filter_by(role="admin").first():
        print("Admin already exists.")
    else:
        admin = User(
            email="admin@school.com",
            password_hash=bcrypt.generate_password_hash("admin123").decode("utf-8"),
            role="admin",
            first_name="Admin",
            last_name="User",
            preferred_language="pt",
        )
        db.session.add(admin)
        db.session.commit()
        print("Admin created: admin@school.com / admin123")
