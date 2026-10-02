import os

from flask import g
from superset.security import SupersetSecurityManager

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


ENABLE_CORS = True
CORS_OPTIONS = {
    "supports_credentials": True,
    "allow_headers": ["*"],
    "resources": ["*"],
    "origins": ["*"],
}


# SQL Lab & Webserver Timeout Configurations
SQLLAB_TIMEOUT = 300
SUPERSET_WEBSERVER_TIMEOUT = 300
SQLLAB_BACKEND_PERSISTENCE = False
DISPLAY_MAX_ROW = 50000


# Custom Security Manager to safely handle detached SQLAlchemy session states during SQL Lab query filtering
class CustomSecurityManager(SupersetSecurityManager):
    def _has_view_access(self, user, permission_name, view_name):
        try:
            _ = user.roles
        except Exception:
            if hasattr(user, "id") and user.id:
                reloaded = self.get_session.query(self.user_model).get(user.id)
                if reloaded:
                    user = reloaded
        return super()._has_view_access(user, permission_name, view_name)

    def get_user_roles(self, user=None):
        if not user:
            user = g.user
        try:
            _ = user.roles
        except Exception:
            if hasattr(user, "id") and user.id:
                reloaded = self.get_session.query(self.user_model).get(user.id)
                if reloaded:
                    user = reloaded
        return super().get_user_roles(user)


CUSTOM_SECURITY_MANAGER = CustomSecurityManager
