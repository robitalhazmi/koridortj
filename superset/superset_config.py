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


# Sanitize legacy non-standard vendor CSS properties in bundled static assets
def _sanitize_fab_static_assets():
    try:
        import glob
        import re

        import flask_appbuilder

        css_files = []
        fab_dir = os.path.dirname(flask_appbuilder.__file__)
        css_files.extend(glob.glob(os.path.join(fab_dir, "static", "**", "*.css"), recursive=True))

        for static_dir in [
            "/app/superset/static",
            os.path.join(os.path.dirname(__file__), "static"),
        ]:
            if os.path.exists(static_dir):
                css_files.extend(glob.glob(os.path.join(static_dir, "**", "*.css"), recursive=True))

        try:
            import superset

            superset_dir = os.path.dirname(superset.__file__)
            css_files.extend(
                glob.glob(os.path.join(superset_dir, "static", "**", "*.css"), recursive=True)
            )
        except Exception:
            pass

        patterns = [
            re.compile(r"filter:\s*alpha\([^)]*\);?", re.IGNORECASE),
            re.compile(r"filter:\s*progid:DXImageTransform\.Microsoft\.[^;}]*;?", re.IGNORECASE),
            re.compile(
                r"filter:\s*['\"][^'\"]*alpha\([^'\"]*['\"];?",
                re.IGNORECASE,
            ),
            re.compile(
                r"filter:\s*['\"][^'\"]*DXImageTransform[^'\"]*['\"];?",
                re.IGNORECASE,
            ),
            re.compile(r"-ms-filter:\s*['\"][^'\"]*['\"];?", re.IGNORECASE),
            re.compile(r"-moz-osx-font-smoothing:\s*[^;}]*;?", re.IGNORECASE),
            re.compile(r"[^{};]*:?-ms-input-placeholder\s*\{[^}]*\}", re.IGNORECASE),
            re.compile(r"@-ms-viewport\s*\{[^}]*\}", re.IGNORECASE),
            re.compile(r"-webkit-text-size-adjust:\s*100%;?", re.IGNORECASE),
            re.compile(r"-ms-text-size-adjust:\s*100%;?", re.IGNORECASE),
            re.compile(r"[^{};]*:?-moz-focus-inner\s*\{[^}]*\}", re.IGNORECASE),
            re.compile(r"[^{};]*:?-moz-focusring\s*\{[^}]*\}", re.IGNORECASE),
            re.compile(r"orphans:\s*[^;}]*;?", re.IGNORECASE),
            re.compile(r"widows:\s*[^;}]*;?", re.IGNORECASE),
            re.compile(r"outline:\s*[^;}]*-webkit-focus-ring-color;?", re.IGNORECASE),
            re.compile(r"[^{};]*:?-ms-expand\s*\{[^}]*\}", re.IGNORECASE),
            re.compile(r"[^{};]*:?-ms-(?:clear|reveal)\s*\{[^}]*\}", re.IGNORECASE),
            re.compile(r"[^{};]*_?:-ms-fullscreen[^{};]*,\s*", re.IGNORECASE),
            re.compile(r",\s*[^{};]*_?:-ms-fullscreen[^{};]*(?=\s*\{)", re.IGNORECASE),
            re.compile(r"[^{};]*_?:-ms-fullscreen[^{};]*\{[^}]*\}", re.IGNORECASE),
            re.compile(r"[a-z0-9-]+:\s*[^;}]*\\9\s*;?", re.IGNORECASE),
        ]

        replacements = [
            (
                re.compile(r"background-color:\s*none\b", re.IGNORECASE),
                "background-color: transparent",
            ),
            (
                re.compile(r"@media\s*[^{};]*transform-3d[^{};]*", re.IGNORECASE),
                "@media all",
            ),
            (
                re.compile(r"padding-top:\s*8(?=\s*[;}])", re.IGNORECASE),
                "padding-top:8px",
            ),
            (
                re.compile(r"padding-right:\s*2(?=\s*[;}])", re.IGNORECASE),
                "padding-right:2px",
            ),
        ]

        media_feature_removals = ["-ms-high-contrast"]

        for f in set(css_files):
            try:
                with open(f, encoding="utf-8", errors="ignore") as fp:
                    original = fp.read()
                modified = original
                for feature in media_feature_removals:
                    while True:
                        m = re.search(
                            rf"@media[^{{}}]*{re.escape(feature)}[^{{}}]*\{{",
                            modified,
                            re.IGNORECASE,
                        )
                        if not m:
                            break
                        start = m.start()
                        brace_count = 0
                        end = len(modified)
                        for i in range(m.end() - 1, len(modified)):
                            if modified[i] == "{":
                                brace_count += 1
                            elif modified[i] == "}":
                                brace_count -= 1
                                if brace_count == 0:
                                    end = i + 1
                                    break
                        modified = modified[:start] + modified[end:]
                for pat in patterns:
                    modified = pat.sub("", modified)
                for pat, repl in replacements:
                    modified = pat.sub(repl, modified)
                if modified != original:
                    with open(f, "w", encoding="utf-8") as fp:
                        fp.write(modified)
            except Exception:
                continue
    except Exception:
        pass


_sanitize_fab_static_assets()
