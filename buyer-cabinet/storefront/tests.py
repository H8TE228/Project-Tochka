from django.test import SimpleTestCase
from rest_framework.test import APIClient


class HealthCheckTests(SimpleTestCase):
    def test_health_check_returns_ok(self):
        response = APIClient().get("/api/v1/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"service": "buyer-cabinet", "status": "ok"})
