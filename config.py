import os
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()


def _parse_base_url(raw: str):
    """Return (server_name, scheme) from APP_BASE_URL, e.g. 'http://192.168.1.55:5001'."""
    if not raw:
        return None, "http"
    parsed = urlparse(raw if "://" in raw else f"http://{raw}")
    host = parsed.hostname or "localhost"
    port = parsed.port
    scheme = parsed.scheme or "http"
    server_name = f"{host}:{port}" if port else host
    return server_name, scheme


_base_url = os.environ.get("APP_BASE_URL", "")
_server_name, _url_scheme = _parse_base_url(_base_url)


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret")
    SQLALCHEMY_DATABASE_URI = os.environ.get("SQLALCHEMY_DATABASE_URI", "sqlite:///conference.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # External URL generation (used in email links).
    # Set APP_BASE_URL in .env to the address other devices use to reach this machine,
    # e.g.  APP_BASE_URL=http://192.168.1.55:5001
    # Leave blank to keep Flask's default (localhost).
    if _server_name:
        SERVER_NAME          = _server_name
        PREFERRED_URL_SCHEME = _url_scheme

    MAIL_SERVER = "smtp.resend.com"
    MAIL_PORT = 465
    MAIL_USE_SSL = True
    MAIL_USERNAME = "resend"
    MAIL_PASSWORD = os.environ.get("RESEND_API_KEY", "")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "noreply@yourschool.com")

    BABEL_DEFAULT_LOCALE = "pt"
    BABEL_SUPPORTED_LOCALES = ["pt", "en"]
    LANGUAGES = ["pt", "en"]
    BABEL_TRANSLATION_DIRECTORIES = os.path.join(os.path.dirname(__file__), "translations")
