import re
from flask import Flask, session, request
from config import Config
from app.extensions import db, migrate, login_manager, mail, bcrypt, babel, csrf
from flask_apscheduler import APScheduler

scheduler = APScheduler()


def _natsort_key(value):
    """Split a string into (text, number) chunks for natural ordering."""
    return [int(c) if c.isdigit() else c.lower()
            for c in re.split(r'(\d+)', str(value))]


def _natsort_filter(iterable, attribute=None):
    """Jinja2 filter: sort a list naturally ascending (handles embedded numbers)."""
    if attribute:
        return sorted(iterable, key=lambda x: _natsort_key(getattr(x, attribute, '')))
    return sorted(iterable, key=_natsort_key)


def _natsort_desc_filter(iterable, attribute=None):
    """Jinja2 filter: sort a list naturally descending (G12 → G11 → G10 …)."""
    if attribute:
        return sorted(iterable, key=lambda x: _natsort_key(getattr(x, attribute, '')), reverse=True)
    return sorted(iterable, key=_natsort_key, reverse=True)


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    app.jinja_env.filters['natsort']      = _natsort_filter
    app.jinja_env.filters['natsort_desc'] = _natsort_desc_filter

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail.init_app(app)
    bcrypt.init_app(app)
    babel.init_app(app, locale_selector=get_locale)
    csrf.init_app(app)

    scheduler.init_app(app)
    scheduler.start()
    scheduler.add_job(
        id="deadline_emails",
        func="app.tasks:check_and_send_deadline_emails",
        trigger="interval",
        minutes=5,
        misfire_grace_time=60,
    )

    from app.auth.routes import auth_bp
    from app.admin.routes import admin_bp
    from app.teacher.routes import teacher_bp
    from app.student.routes import student_bp
    from app.guardian.routes import guardian_bp
    from app.scheduling.routes import scheduling_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(teacher_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(guardian_bp)
    app.register_blueprint(scheduling_bp)

    from app.models import User

    @app.route("/")
    def index():
        from flask import redirect, url_for
        from flask_login import current_user
        if current_user.is_authenticated:
            role_map = {
                "admin": "admin.dashboard",
                "teacher": "teacher.dashboard",
                "guardian": "guardian.dashboard",
                "student": "student.dashboard",
            }
            return redirect(url_for(role_map.get(current_user.role, "auth.login")))
        return redirect(url_for("auth.login"))

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.errorhandler(403)
    def forbidden(e):
        from flask import render_template
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        from flask import render_template
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        from flask import render_template
        return render_template("errors/500.html"), 500

    return app


def get_locale():
    user_lang = session.get("lang")
    if user_lang in ["pt", "en"]:
        return user_lang
    return request.accept_languages.best_match(["pt", "en"], default="pt")
