import os
import urllib.parse

ROW_LIMIT = 50000
SECRET_KEY = os.getenv("SUPERSET_SECRET_KEY", "koridortj_superset_secret_key_9876543210abcdef")

# Superset metadata database
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres_dev_password")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB_SUPERSET = os.getenv("POSTGRES_DB_SUPERSET", "superset_meta")

_encoded_user = urllib.parse.quote_plus(POSTGRES_USER)
_encoded_password = urllib.parse.quote_plus(POSTGRES_PASSWORD)
SQLALCHEMY_DATABASE_URI = f"postgresql+psycopg2://{_encoded_user}:{_encoded_password}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB_SUPERSET}"

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
