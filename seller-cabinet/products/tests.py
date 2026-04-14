from django.test import TestCase

from products.models import Category, Seller


class DatabaseSmokeTests(TestCase):
    """Ensures migrations applied and ORM works against the test database."""

    def test_seller_and_category_roundtrip(self):
        seller = Seller.objects.create(auth_user_id="550e8400-e29b-41d4-a716-446655440000", name="Test Seller")
        cat = Category.objects.create(name="Test Category", slug="test-category", parent=None)
        self.assertEqual(seller.name, "Test Seller")
        self.assertEqual(cat.slug, "test-category")
        self.assertIsNotNone(cat.id)
