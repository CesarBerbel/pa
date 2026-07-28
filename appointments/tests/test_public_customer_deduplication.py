from django.contrib.auth import get_user_model
from django.test import TestCase

from appointments.customer_services import find_or_create_customer
from appointments.models import Customer


class PublicCustomerDeduplicationTests(TestCase):
    # Public bookings run without an authenticated user. Each booking must reuse
    # the existing customer instead of creating a duplicate record.

    def test_guest_booking_with_known_email_reuses_customer(self):
        existing_customer = Customer.objects.create(
            full_name="Maria Silva",
            email="maria@test.com",
            phone="+351916666666",
            is_guest=True,
        )

        customer = find_or_create_customer(
            name="Maria Silva",
            phone="+351916666666",
            email="maria@test.com",
        )

        self.assertEqual(customer.pk, existing_customer.pk)
        self.assertEqual(Customer.objects.count(), 1)

    def test_guest_booking_with_known_phone_in_another_format_reuses_customer(self):
        existing_customer = Customer.objects.create(
            full_name="Maria Silva",
            email="",
            phone="+351916666666",
            is_guest=True,
        )

        customer = find_or_create_customer(
            name="Maria Silva",
            phone="916 666 666",
            email="",
        )

        self.assertEqual(customer.pk, existing_customer.pk)
        self.assertEqual(Customer.objects.count(), 1)

    def test_repeated_guest_bookings_do_not_duplicate_customer(self):
        for _ in range(3):
            find_or_create_customer(
                name="Maria Silva",
                phone="+351916666666",
                email="maria@test.com",
            )

        self.assertEqual(Customer.objects.count(), 1)

    def test_guest_booking_with_unknown_contact_creates_guest_customer(self):
        customer = find_or_create_customer(
            name="Cliente Novo",
            phone="+351916666666",
            email="novo@test.com",
        )

        self.assertEqual(Customer.objects.count(), 1)
        self.assertTrue(customer.is_guest)
        self.assertIsNone(customer.user)
        self.assertEqual(customer.phone, "+351916666666")

    def test_guest_booking_updates_name_and_stores_normalized_phone(self):
        existing_customer = Customer.objects.create(
            full_name="Maria",
            email="maria@test.com",
            phone="916666666",
            is_guest=True,
        )

        find_or_create_customer(
            name="Maria Silva",
            phone="916 666 666",
            email="MARIA@test.com",
        )

        existing_customer.refresh_from_db()

        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(existing_customer.full_name, "Maria Silva")
        self.assertEqual(existing_customer.phone, "+351916666666")
        self.assertEqual(existing_customer.email, "maria@test.com")

    def test_guest_booking_does_not_downgrade_registered_customer(self):
        user = get_user_model().objects.create_user(
            email="maria@test.com",
            password="testpass123",
            full_name="Maria Silva",
        )

        registered_customer = Customer.objects.create(
            full_name="Maria Silva",
            email="maria@test.com",
            phone="+351916666666",
            user=user,
            is_guest=False,
        )

        customer = find_or_create_customer(
            name="Maria Silva",
            phone="+351916666666",
            email="maria@test.com",
        )

        registered_customer.refresh_from_db()

        self.assertEqual(customer.pk, registered_customer.pk)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertFalse(registered_customer.is_guest)
        self.assertEqual(registered_customer.user, user)

    def test_guest_booking_without_email_keeps_stored_email(self):
        existing_customer = Customer.objects.create(
            full_name="Maria Silva",
            email="maria@test.com",
            phone="+351916666666",
            is_guest=True,
        )

        find_or_create_customer(
            name="Maria Silva",
            phone="+351916666666",
            email="",
        )

        existing_customer.refresh_from_db()

        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(existing_customer.email, "maria@test.com")

    def test_signup_links_existing_guest_customer_to_user(self):
        existing_customer = Customer.objects.create(
            full_name="Maria",
            email="maria@test.com",
            phone="+351916666666",
            is_guest=True,
        )

        user = get_user_model().objects.create_user(
            email="maria@test.com",
            password="testpass123",
            full_name="Maria Silva",
        )

        customer = find_or_create_customer(
            name="Maria Silva",
            phone="+351916666666",
            email="maria@test.com",
            user=user,
        )

        existing_customer.refresh_from_db()

        self.assertEqual(customer.pk, existing_customer.pk)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(existing_customer.user, user)
        self.assertFalse(existing_customer.is_guest)
        self.assertEqual(existing_customer.full_name, "Maria Silva")
