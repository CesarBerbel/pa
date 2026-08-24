from importlib import import_module

from django.apps import apps
from django.test import TestCase

from config.test_utils import ResetLanguageMixin
from django.utils import translation

from appointments.models import Service, ServiceCategory


class SeededCatalogTranslationTests(ResetLanguageMixin, TestCase):
    # Migration 0010 fills the English catalog fields. The test database runs
    # every migration, so the seeded catalog must come out already translated.

    def test_every_seeded_category_has_an_english_name(self):
        untranslated = list(
            ServiceCategory.objects.filter(name_en="").values_list("slug", flat=True)
        )

        self.assertEqual(untranslated, [])

    def test_every_seeded_service_has_an_english_name(self):
        untranslated = list(
            Service.objects.filter(name_en="").values_list("name", flat=True)
        )

        self.assertEqual(untranslated, [])

    def test_known_category_translations(self):
        expected = {
            # O `slug` continua `podologia`; o nome mudou para não afirmar
            # um título que em Portugal tem formação própria.
            "podologia": "Therapeutic Pedicure",
            "manicure": "Manicure",
            "pedicure": "Pedicure",
            "enfermagem": "Nursing",
        }

        for slug, name_en in expected.items():
            category = ServiceCategory.objects.get(slug=slug)

            with translation.override("en"):
                self.assertEqual(category.display_name, name_en)

            # "Manicure" e "Pedicure" escrevem-se igual nos dois idiomas, por
            # isso a comparação é contra o nome português e não contra o inglês.
            with translation.override("pt-pt"):
                self.assertEqual(category.display_name, category.name)

    def test_rerunning_the_migration_keeps_manual_translations(self):
        # The data function only fills empty fields, so a translation typed in
        # the admin must survive if the migration ever runs again.
        migration = import_module(
            "appointments.migrations.0010_translate_service_catalog"
        )

        category = ServiceCategory.objects.get(slug="podologia")
        category.name_en = "Foot care"
        category.save(update_fields=["name_en"])

        migration.apply_translations(apps, None)

        category.refresh_from_db()

        self.assertEqual(category.name_en, "Foot care")

    def test_english_catalog_reaches_the_public_page(self):
        response = self.client.get("/en/")

        self.assertContains(response, "Therapeutic Pedicure")
        self.assertContains(response, "Nursing")
        self.assertNotContains(response, "Enfermagem")
