from .views_auth import (
    customer_change_password,
    customer_set_password,
    home_redirect,
    login_view,
    logout_view,
)
from .views_customer import bike_detail, customer_home, customer_profile_view, loyalty_landing
from .views_staff import (
    create_customer_with_bike,
    create_service_order,
    quick_create_customer_with_bike,
    service_order_admin_detail,
    service_order_protocol_pdf,
    service_panel,
)

__all__ = [
    "home_redirect",
    "login_view",
    "logout_view",
    "customer_set_password",
    "customer_change_password",
    "customer_home",
    "bike_detail",
    "customer_profile_view",
    "loyalty_landing",
    "service_panel",
    "service_order_protocol_pdf",
    "service_order_admin_detail",
    "create_customer_with_bike",
    "quick_create_customer_with_bike",
    "create_service_order",
]
