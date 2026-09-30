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
        import sys

        css_files = []
        js_files = []
        candidate_dirs = [
            "/app/superset/static",
            os.path.join(os.path.dirname(__file__), "static"),
        ]
        if "flask_appbuilder" in sys.modules:
            candidate_dirs.append(
                os.path.join(os.path.dirname(sys.modules["flask_appbuilder"].__file__), "static")
            )
        candidate_dirs.extend(
            glob.glob("/usr/local/lib/python*/site-packages/flask_appbuilder/static")
        )

        for static_dir in set(candidate_dirs):
            if os.path.exists(static_dir):
                css_files.extend(glob.glob(os.path.join(static_dir, "**", "*.css"), recursive=True))
                js_files.extend(glob.glob(os.path.join(static_dir, "**", "*.js"), recursive=True))

        guarded_replacements = [
            (
                "line-",
                re.compile(
                    r"(?<![-\w])line-(?=(?:list-style|padding|margin|overflow|text-align|min-width|max-width|min-height|line-height|font-size|border)\b)",
                    re.IGNORECASE,
                ),
                "line-height:1.5715;",
            ),
            (
                "line-",
                re.compile(r"(?<![-\w])line-(?=[;}])", re.IGNORECASE),
                "line-height:1.5715;",
            ),
            (
                "background-color:",
                re.compile(r"background-color:\s*none\b", re.IGNORECASE),
                "background-color: transparent",
            ),
            (
                "transform-3d",
                re.compile(r"@media\s*[^{};]*transform-3d[^{};]*", re.IGNORECASE),
                "@media all",
            ),
            (
                "padding-top:",
                re.compile(r"padding-top:\s*8(?=\s*[;}])", re.IGNORECASE),
                "padding-top:8px",
            ),
            (
                "padding-right:",
                re.compile(r"padding-right:\s*2(?=\s*[;}])", re.IGNORECASE),
                "padding-right:2px",
            ),
            (
                "box-shadow:",
                re.compile(r"(?<![-\w])box-shadow\s*:\s*0(?:px)?(?=\s*[;}])", re.IGNORECASE),
                "box-shadow: none",
            ),
            (
                "max-width:",
                re.compile(r"(?<![-\w])max-width\s*:\s*auto\b", re.IGNORECASE),
                "max-width: none",
            ),
            (
                "max-height:",
                re.compile(r"(?<![-\w])max-height\s*:\s*auto\b", re.IGNORECASE),
                "max-height: none",
            ),
            (
                "animation-fill-mode:",
                re.compile(
                    r"(?<![-\w])animation-fill-mode\s*:\s*(cubic-bezier\([^)]*\)|ease(?:-[a-z]+)*|linear)",
                    re.IGNORECASE,
                ),
                r"animation-timing-function:\1",
            ),
        ]

        guarded_patterns = [
            ("alpha", re.compile(r"filter:\s*alpha\([^)]*\);?", re.IGNORECASE)),
            (
                "DXImageTransform",
                re.compile(
                    r"filter:\s*progid:DXImageTransform\.Microsoft\.[^;}]*;?", re.IGNORECASE
                ),
            ),
            (
                "alpha",
                re.compile(
                    r"filter:\s*['\"][^'\"]*alpha\([^'\"]*['\"];?",
                    re.IGNORECASE,
                ),
            ),
            (
                "DXImageTransform",
                re.compile(
                    r"filter:\s*['\"][^'\"]*DXImageTransform[^'\"]*['\"];?",
                    re.IGNORECASE,
                ),
            ),
            ("-ms-filter", re.compile(r"-ms-filter:\s*['\"][^'\"]*['\"];?", re.IGNORECASE)),
            ("-moz-osx", re.compile(r"-moz-osx-font-smoothing:\s*[^;}]*;?", re.IGNORECASE)),
            (
                "-ms-input-placeholder",
                re.compile(r"[^{};]*:?-ms-input-placeholder\s*\{[^}]*\}", re.IGNORECASE),
            ),
            ("@-ms-viewport", re.compile(r"@-ms-viewport\s*\{[^}]*\}", re.IGNORECASE)),
            (
                "-webkit-text-size-adjust",
                re.compile(r"-webkit-text-size-adjust:\s*100%;?", re.IGNORECASE),
            ),
            ("-ms-text-size-adjust", re.compile(r"-ms-text-size-adjust:\s*100%;?", re.IGNORECASE)),
            (
                "-moz-focus-inner",
                re.compile(r"[^{};]*:?-moz-focus-inner\s*\{[^}]*\}", re.IGNORECASE),
            ),
            ("-moz-focusring", re.compile(r"[^{};]*:?-moz-focusring\s*\{[^}]*\}", re.IGNORECASE)),
            ("orphans", re.compile(r"orphans:\s*[^;}]*;?", re.IGNORECASE)),
            ("widows", re.compile(r"widows:\s*[^;}]*;?", re.IGNORECASE)),
            (
                "-webkit-focus-ring-color",
                re.compile(r"outline:\s*[^;}]*-webkit-focus-ring-color;?", re.IGNORECASE),
            ),
            ("-ms-expand", re.compile(r"[^{};]*:?-ms-expand\s*\{[^}]*\}", re.IGNORECASE)),
            ("-ms-clear", re.compile(r"[^{};]*:?-ms-(?:clear|reveal)\s*\{[^}]*\}", re.IGNORECASE)),
            ("-ms-reveal", re.compile(r"[^{};]*:?-ms-(?:clear|reveal)\s*\{[^}]*\}", re.IGNORECASE)),
            (
                "-ms-fullscreen",
                re.compile(r"[^{};]*_?:-ms-fullscreen[^{};]*,\s*", re.IGNORECASE),
            ),
            (
                "-ms-fullscreen",
                re.compile(r",\s*[^{};]*_?:-ms-fullscreen[^{};]*(?=\s*\{)", re.IGNORECASE),
            ),
            (
                "-ms-fullscreen",
                re.compile(r"[^{};]*_?:-ms-fullscreen[^{};]*\{[^}]*\}", re.IGNORECASE),
            ),
            (r"\9", re.compile(r"[a-z0-9-]+:\s*[^;}]*?\x5c9\s*;?", re.IGNORECASE)),
            ("height:", re.compile(r"(?<![-\w])height:\s*1\.5715\s*;?", re.IGNORECASE)),
            (
                "max-height:",
                re.compile(r"(?<![-\w])max-height:\s*-[0-9]+(?:px|em|rem|%)?\s*;?", re.IGNORECASE),
            ),
        ]

        media_feature_removals = ["-ms-high-contrast"]

        for f in set(css_files):
            try:
                if not f.endswith(".css"):
                    continue
                with open(f, encoding="utf-8", errors="ignore") as fp:
                    original = fp.read()
                modified = original

                for feature in media_feature_removals:
                    if feature not in modified:
                        continue
                    while True:
                        m = re.search(
                            rf"@media[^{{}}]*{re.escape(feature)}[^{{}}]*\{{",
                            modified,
                            re.IGNORECASE,
                        )
                        if not m:
                            break
                        start = m.start()
                        open_pos = m.end() - 1
                        brace_count = 1
                        curr = open_pos + 1
                        n = len(modified)
                        while curr < n and brace_count > 0:
                            next_open = modified.find("{", curr)
                            next_close = modified.find("}", curr)
                            if next_close == -1:
                                curr = n
                                break
                            if next_open != -1 and next_open < next_close:
                                brace_count += 1
                                curr = next_open + 1
                            else:
                                brace_count -= 1
                                curr = next_close + 1
                        modified = modified[:start] + modified[curr:]

                for kw, pat, repl in guarded_replacements:
                    if kw.lower() in modified.lower():
                        modified = pat.sub(repl, modified)
                for kw, pat in guarded_patterns:
                    if kw.lower() in modified.lower():
                        modified = pat.sub("", modified)

                if modified != original:
                    with open(f, "w", encoding="utf-8") as fp:
                        fp.write(modified)
            except Exception:
                continue

        js_replacements = [
            (
                "You should call configure",
                re.compile(
                    r"console\.warn\([\'\"][^\'\"]*You should call configure[^\'\"]*[\'\"]\)",
                    re.IGNORECASE,
                ),
                "void 0",
            ),
        ]

        for f in set(js_files):
            try:
                if not f.endswith(".js"):
                    continue
                with open(f, encoding="utf-8", errors="ignore") as fp:
                    original = fp.read()
                modified = original
                for kw, pat, repl in js_replacements:
                    if kw in modified:
                        modified = pat.sub(repl, modified)
                if modified != original:
                    with open(f, "w", encoding="utf-8") as fp:
                        fp.write(modified)
            except Exception:
                continue
    except Exception:
        pass


_sanitize_fab_static_assets()
