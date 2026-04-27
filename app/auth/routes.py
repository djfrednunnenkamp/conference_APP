from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from flask_babel import _
from app.extensions import db, bcrypt
from app.models import User
from app.auth.forms import LoginForm, SetPasswordForm, ForgotPasswordForm, ResetPasswordForm, ChangePasswordForm
from app.utils import generate_token, verify_token, send_reset_email

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(_role_dashboard())
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower().strip()).first()
        if user and user.password_hash and bcrypt.check_password_hash(user.password_hash, form.password.data):
            login_user(user)
            next_page = request.args.get("next")
            return redirect(next_page or _role_dashboard())
        flash(_("E-mail ou senha inválidos."), "danger")
    return render_template("auth/login.html", form=form)


@auth_bp.route("/set-password/<token>", methods=["GET", "POST"])
def set_password(token):
    email = verify_token(token, salt="invite", max_age=72 * 3600)
    if not email:
        flash(_("Este link é inválido ou expirou. Entre em contato com o administrador."), "danger")
        return redirect(url_for("auth.login"))
    user = User.query.filter_by(email=email).first_or_404()
    if user.password_hash:
        flash(_("Sua conta já está configurada. Faça o login."), "info")
        return redirect(url_for("auth.login"))
    form = SetPasswordForm()
    if form.validate_on_submit():
        user.password_hash = bcrypt.generate_password_hash(form.password.data).decode("utf-8")
        user.preferred_language = form.language.data
        user.invite_token = None
        db.session.commit()
        flash(_("Senha criada com sucesso! Você já pode fazer o login."), "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/set_password.html", form=form)


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower().strip()).first()
        if user and user.password_hash:
            token = generate_token(user.email, salt="reset")
            try:
                send_reset_email(user, token)
            except Exception:
                pass
        flash(_("Se este e-mail estiver cadastrado, você receberá um link de redefinição."), "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/forgot_password.html", form=form)


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    email = verify_token(token, salt="reset", max_age=3600)
    if not email:
        flash(_("Este link é inválido ou expirou."), "danger")
        return redirect(url_for("auth.forgot_password"))
    user = User.query.filter_by(email=email).first_or_404()
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.password_hash = bcrypt.generate_password_hash(form.password.data).decode("utf-8")
        db.session.commit()
        flash(_("Senha redefinida com sucesso. Você já pode fazer o login."), "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/reset_password.html", form=form)


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not bcrypt.check_password_hash(current_user.password_hash, form.current_password.data):
            flash(_("Senha atual incorreta."), "danger")
        else:
            current_user.password_hash = bcrypt.generate_password_hash(form.new_password.data).decode("utf-8")
            db.session.commit()
            flash(_("Senha alterada com sucesso."), "success")
            return redirect(_role_dashboard())
    return render_template("auth/change_password.html", form=form)


@auth_bp.route("/preferences", methods=["POST"])
@login_required
def update_preferences():
    first_name = request.form.get("first_name", "").strip()
    last_name  = request.form.get("last_name",  "").strip()
    email      = request.form.get("email",      "").lower().strip()
    language   = request.form.get("language",   "")
    next_url   = request.form.get("next") or _role_dashboard()

    if not first_name or not last_name or not email:
        flash(_("Todos os campos são obrigatórios."), "danger")
        return redirect(next_url)

    clash = User.query.filter(User.email == email, User.id != current_user.id).first()
    if clash:
        flash(_("Já existe um usuário com este e-mail."), "danger")
        return redirect(next_url)

    current_user.first_name = first_name
    current_user.last_name  = last_name
    current_user.email      = email
    if language in ("pt", "en"):
        current_user.preferred_language = language
        session["lang"] = language          # reflect immediately in UI
    db.session.commit()
    flash(_("Preferências salvas."), "success")
    return redirect(next_url)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@auth_bp.route("/lang/<lang>")
def set_language(lang):
    if lang in ["pt", "en"]:
        session["lang"] = lang
    return redirect(request.referrer or url_for("auth.login"))


def _role_dashboard():
    role_map = {
        "admin": "admin.dashboard",
        "teacher": "teacher.dashboard",
        "guardian": "guardian.dashboard",
        "student": "student.dashboard",
    }
    return url_for(role_map.get(current_user.role, "auth.login"))
