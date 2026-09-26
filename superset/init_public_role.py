"""Initialize Superset Admin User & Public / Guest Role Permissions for Embedded Dashboards."""

import os

from superset.app import create_app
from werkzeug.security import generate_password_hash

app = create_app()
with app.app_context():
    from superset import security_manager

    # 1. Ensure Admin User Exists
    admin_user = os.getenv("SUPERSET_ADMIN_USERNAME", "admin")
    admin_pass = os.getenv("SUPERSET_ADMIN_PASSWORD", "admin")
    admin_email = os.getenv("SUPERSET_ADMIN_EMAIL", "admin@koridortj.id")

    user = security_manager.find_user(username=admin_user)
    admin_role = security_manager.find_role("Admin")

    if not user:
        print(f"Creating Admin user '{admin_user}'...")
        security_manager.add_user(
            username=admin_user,
            first_name="Admin",
            last_name="User",
            email=admin_email,
            role=admin_role,
            password=admin_pass,
        )
        print(f"✅ Admin user '{admin_user}' created successfully.")
    else:
        print(f"Updating password for Admin user '{admin_user}'...")
        user.password = generate_password_hash(admin_pass)
        security_manager.get_session.merge(user)
        print(f"✅ Admin user '{admin_user}' password updated.")

    # 2. Configure Public Role Permissions for Embedded Guest Tokens
    pub = security_manager.find_role("Public")
    gamma = security_manager.find_role("Gamma")

    if gamma and pub:
        for p in gamma.permissions:
            security_manager.add_permission_role(pub, p)

    for p_name, vm_name in [
        ("all_datasource_access", "all_datasource_access"),
        ("all_database_access", "all_database_access"),
        ("can_read", "Dashboard"),
        ("can_read", "Chart"),
        ("can_read", "Dataset"),
        ("can_explore_json", "Superset"),
        ("can_dashboard", "Superset"),
        ("can_warm_up_cache", "Superset"),
        ("can_csrf_token", "Superset"),
    ]:
        pvm = security_manager.find_permission_view_menu(p_name, vm_name)
        if pvm and pub:
            security_manager.add_permission_role(pub, pvm)

    # 3. Ensure Embedded Dashboards Allow Embedding from Any Origin
    from superset.models.embedded_dashboard import EmbeddedDashboard

    for ed in security_manager.get_session.query(EmbeddedDashboard).all():
        if ed.allow_domain_list == "*" or ed.allow_domain_list == "['*']":
            ed.allow_domain_list = None
            security_manager.get_session.merge(ed)

    security_manager.get_session.commit()
    print(f"✅ Public role configured with {len(pub.permissions)} permissions.")
