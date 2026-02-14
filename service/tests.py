from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .models import Bike, CustomerProfile, ServiceOrder
from .view_common import _get_or_create_customer_user
from .views_staff import _invite_customer_to_portal


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PasswordSecurityTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_created_customer_user_has_unusable_password(self):
        user, created = _get_or_create_customer_user(email="new@example.com", full_name="New User")
        self.assertTrue(created)
        self.assertTrue(user.has_usable_password() is False)

    def test_invite_email_contains_set_password_link_without_plaintext_password(self):
        profile = CustomerProfile.objects.create(
            full_name="Invite User",
            email="invite@example.com",
            phone_number="",
        )
        request = self.factory.get("/")
        request.META["HTTP_HOST"] = "testserver"
        request.META["wsgi.url_scheme"] = "http"

        ok = _invite_customer_to_portal(request, profile)

        self.assertTrue(ok)
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        self.assertIn("Nastavenie hesla", body)
        self.assertIn("/nastavit-heslo/", body)
        self.assertNotIn("Heslo:", body)

    def test_set_password_view_sets_password_and_allows_authentication(self):
        user = User.objects.create_user(
            username="token@example.com",
            email="token@example.com",
            password=None,
        )
        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        url = reverse("customer_set_password", kwargs={"uidb64": uidb64, "token": token})

        resp = self.client.post(
            url,
            {"new_password": "StrongPass123!", "new_password2": "StrongPass123!"},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)

        user.refresh_from_db()
        self.assertTrue(user.has_usable_password())
        self.assertIsNotNone(authenticate(username="token@example.com", password="StrongPass123!"))


class ServicePanelKpiTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="staff@example.com",
            email="staff@example.com",
            password="StrongPass123!",
            is_staff=True,
        )
        self.client.force_login(self.staff)

        profile = CustomerProfile.objects.create(
            full_name="Test Customer",
            email="customer@example.com",
            phone_number="",
        )
        bike = Bike.objects.create(
            customer=profile,
            brand="Trek",
            model="Domane",
            serial_number="SN-1",
        )

        ServiceOrder.objects.create(bike=bike, status=ServiceOrder.Status.NEW)
        ServiceOrder.objects.create(bike=bike, status=ServiceOrder.Status.IN_PROGRESS)
        ServiceOrder.objects.create(bike=bike, status=ServiceOrder.Status.DONE)

    def test_service_panel_context_contains_unfinished_count(self):
        response = self.client.get(reverse("service_panel"))
        self.assertEqual(response.status_code, 200)

        expected = ServiceOrder.objects.exclude(status=ServiceOrder.Status.DONE).count()
        self.assertEqual(response.context["unfinished_count"], expected)

    def test_service_panel_unfinished_kpi_links_to_admin_ticket_list_without_filters(self):
        response = self.client.get(reverse("service_panel"))
        self.assertEqual(response.status_code, 200)

        tickets_url = reverse("admin_ticket_list")
        self.assertContains(response, f'<a class="tile-link" href="{tickets_url}">', html=False)
        self.assertContains(response, "Nedokončené")

    def test_service_panel_smart_search_finds_by_service_code_prefix(self):
        target = ServiceOrder.objects.exclude(status=ServiceOrder.Status.DONE).first()
        target.service_code = "ABC-777"
        target.save(update_fields=["service_code"])

        response = self.client.get(reverse("service_panel"), {"q": "#777"})
        self.assertEqual(response.status_code, 200)
        orders = list(response.context["orders"])
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].id, target.id)

    def test_service_panel_quick_status_update_to_done_sets_completed_at(self):
        order = ServiceOrder.objects.filter(status=ServiceOrder.Status.NEW).first()
        response = self.client.post(
            reverse("service_panel"),
            {
                "action": "row_update_status",
                "order_id": order.id,
                "new_status": ServiceOrder.Status.DONE,
                "tab": "active",
            },
        )
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, ServiceOrder.Status.DONE)
        self.assertIsNotNone(order.completed_at)

    def test_apply_service_package_updates_order_fields(self):
        order = ServiceOrder.objects.filter(status=ServiceOrder.Status.NEW).first()
        response = self.client.post(
            reverse("service_order_admin_detail", kwargs={"order_id": order.id}),
            {
                "action": "apply_service_package",
                "service_package": "basic",
            },
        )
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(str(order.price), "29.00")
        self.assertIn("Základná kontrola bicykla", order.work_done)
        self.assertTrue(order.checklist.get("brakes"))


class CreateServiceOrderDedupTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="staff2@example.com",
            email="staff2@example.com",
            password="StrongPass123!",
            is_staff=True,
        )
        self.client.force_login(self.staff)

    def test_create_service_order_reuses_existing_customer_by_phone(self):
        profile = CustomerProfile.objects.create(
            full_name="Existujuci",
            email="exist@example.com",
            phone_number="0900123456",
        )

        response = self.client.post(
            reverse("create_service_order"),
            {
                "new_full_name": "Novy Meno",
                "new_email": "newmail@example.com",
                "new_phone_number": "0900123456",
                "new_brand": "Trek",
                "new_model": "X-Caliber",
                "new_serial_number": "SN-X",
                "issue_description": "Test vada",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CustomerProfile.objects.count(), 1)
        profile.refresh_from_db()
        self.assertEqual(profile.phone_number, "0900123456")
        self.assertEqual(ServiceOrder.objects.count(), 1)
