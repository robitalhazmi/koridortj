import os

ROW_LIMIT = 50000
SECRET_KEY = os.getenv("SUPERSET_SECRET_KEY", "koridortj_superset_secret_key_9876543210abcdef")

# Superset metadata database
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres_dev_password")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB_SUPERSET = os.getenv("POSTGRES_DB_SUPERSET", "superset_meta")

SQLALCHEMY_DATABASE_URI = f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB_SUPERSET}"

# CSRF & Embedding Configuration
WTF_CSRF_ENABLED = False
TALISMAN_ENABLED = False

FEATURE_FLAGS = {
    "EMBEDDED_SUPERSET": True,
    "ENABLE_TEMPLATE_PROCESSING": True,
}

HTTP_HEADERS = {
    "X-Frame-Options": "ALLOWALL",
}

GUEST_ROLE_NAME = "Public"
GUEST_TOKEN_JWT_SECRET = os.getenv(
    "SUPERSET_GUEST_TOKEN_JWT_SECRET", "koridortj_guest_token_jwt_secret_abcdef123456"
)
GUEST_TOKEN_JWT_AUDIENCE = os.getenv("SUPERSET_GUEST_TOKEN_JWT_AUDIENCE", "koridortj-superset")
GUEST_TOKEN_JWT_ALGO = "HS256"
GUEST_TOKEN_JWT_EXP_SECONDS = 3600


CORS_OPTIONS = {
    "supports_credentials": True,
    "allow_headers": ["*"],
    "resources": ["*"],
    "origins": ["*"],
}


# Sanitize legacy non-standard vendor CSS properties in bundled Flask-AppBuilder assets
def _sanitize_fab_static_assets():
    try:
        import flask_appbuilder

        fab_dir = os.path.dirname(flask_appbuilder.__file__)
        fa_css = os.path.join(
            fab_dir, "static", "appbuilder", "css", "fontawesome", "fontawesome.min.css"
        )
        if os.path.exists(fa_css):
            with open(fa_css, encoding="utf-8") as f:
                content = f.read()
            if "-moz-osx-font-smoothing" in content:
                cleaned = content.replace("-moz-osx-font-smoothing:grayscale;", "").replace(
                    "-moz-osx-font-smoothing: grayscale;", ""
                )
                with open(fa_css, "w", encoding="utf-8") as f:
                    f.write(cleaned)
    except Exception:
        pass


_sanitize_fab_static_assets()
