from django.test import TestCase
from django.urls import reverse


class HomeSalonAnnouncementTests(TestCase):
    # The DIVAH announcement must render on every homepage load. It keeps no
    # dismissal state on purpose, so a reload always shows it again.

    def test_homepage_shows_salon_announcement(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "salon-announcement")
        self.assertContains(response, "DIVAH")
        self.assertContains(response, "hora marcada")
        self.assertContains(response, "Av. Sá da Bandeira")
        self.assertContains(response, "Loja 108")

    def test_navigation_links_to_the_instagram_section(self):
        response = self.client.get(reverse("home"))
        html = response.content.decode()

        # The anchor must exist in the navigation and match a rendered section,
        # otherwise the menu entry scrolls nowhere.
        self.assertIn('href="/#instagram"', html)
        self.assertIn('<section id="instagram"', html)

    def test_salon_name_links_to_its_instagram(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, "https://www.instagram.com/divah.pt")
        self.assertContains(response, 'rel="noopener noreferrer"')

    def test_announcement_is_rendered_again_on_every_reload(self):
        self.client.get(reverse("home"))
        self.client.get(reverse("home"))

        response = self.client.get(reverse("home"))

        self.assertContains(response, "salon-announcement")
        self.assertContains(response, "DIVAH")
