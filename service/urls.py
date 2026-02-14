# service/urls.py

from django.urls import path

from . import health_views, ticket_views, views

urlpatterns = [
    path("health/", health_views.health_check, name="health_check"),
    path("", views.home_redirect, name="home_redirect"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("nastavit-heslo/<uidb64>/<token>/", views.customer_set_password, name="customer_set_password"),
    path("moje-biky/", views.customer_home, name="customer_home"),
    path("moje-biky/<int:bike_id>/", views.bike_detail, name="bike_detail"),
    path("moj-profil/", views.customer_profile_view, name="customer_profile"),
    path("moj-profil/zmena-hesla/", views.customer_change_password, name="customer_change_password"),
    path("odmeny/", views.loyalty_landing, name="loyalty_landing"),
    path("servis-panel/", views.service_panel, name="service_panel"),
    path("servis-panel/orders/<int:order_id>/", views.service_order_admin_detail, name="service_order_admin_detail"),
    path("servis-panel/orders/<int:order_id>/protocol.pdf", views.service_order_protocol_pdf, name="service_order_protocol_pdf"),
    path("servis-panel/novy-zakaznik/", views.create_customer_with_bike, name="create_customer_with_bike"),
    path("servis-panel/quick-novy-zakaznik/", views.quick_create_customer_with_bike, name="quick_create_customer_with_bike"),
    path("servis-panel/novy-servis/", views.create_service_order, name="create_service_order"),
    path("moje-biky/tickety/", ticket_views.customer_ticket_list, name="customer_ticket_list"),
    path("moje-biky/tickety/<int:ticket_id>/", ticket_views.customer_ticket_detail, name="customer_ticket_detail"),
    path("moje-biky/servis/<int:order_id>/novy-ticket/", ticket_views.customer_ticket_create, name="customer_ticket_create"),
    path("servis-panel/tickety/", ticket_views.admin_ticket_list, name="admin_ticket_list"),
    path("servis-panel/tickety/<int:ticket_id>/", ticket_views.admin_ticket_detail, name="admin_ticket_detail"),
]
