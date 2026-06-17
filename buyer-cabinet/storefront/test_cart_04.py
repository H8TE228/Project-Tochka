"""US-CART-04: баннеры на главной + CTR-аналитика.

DoD-обязательные тесты (имена нельзя менять):
- active_banners_returned_sorted_by_priority
- no_active_banners_returns_200_empty
- click_on_unknown_banner_returns_400
"""
import uuid
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from .models import Banner, BannerEvent


BANNERS_URL = "/api/v1/catalog/banners"


@override_settings(
    SECRET_KEY="test-secret-key-for-jwt-that-is-long-enough",
)
class HomeBannersTests(TestCase):
    """GET /api/v1/catalog/banners — публичный, фильтры и сортировка."""

    def setUp(self):
        self.client = APIClient()  # анонимный — endpoint публичный

    # -------------- happy: active_banners_returned_sorted_by_priority --------------
    def test_active_banners_returned_sorted_by_priority(self):
        """
        Только is_active=True и попадающие в расписание баннеры.
        Сортировка по priority DESC (10 → 5 → 1).
        Неактивные и вне расписания — отфильтрованы.
        """
        now = timezone.now()

        # Видимые: разные priority, попадают в расписание
        b_low = Banner.objects.create(
            title="Low priority", image_url="/i/low.jpg", target_url="/promo/low",
            priority=1, is_active=True,
            starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=10),
        )
        b_high = Banner.objects.create(
            title="High priority", image_url="/i/high.jpg", target_url="/promo/high",
            priority=10, is_active=True,
            starts_at=None, ends_at=None,  # бессрочный → виден
        )
        b_mid = Banner.objects.create(
            title="Mid", image_url="/i/mid.jpg", target_url="/promo/mid",
            priority=5, is_active=True,
        )

        # Невидимые
        Banner.objects.create(
            title="Inactive", image_url="/i/no.jpg", target_url="/no",
            priority=100, is_active=False,  # выключен
        )
        Banner.objects.create(
            title="Not yet", image_url="/i/future.jpg", target_url="/future",
            priority=99, is_active=True,
            starts_at=now + timedelta(days=5),  # ещё не начался
        )
        Banner.objects.create(
            title="Expired", image_url="/i/past.jpg", target_url="/past",
            priority=99, is_active=True,
            ends_at=now - timedelta(days=1),  # закончился
        )

        resp = self.client.get(BANNERS_URL)
        assert resp.status_code == 200, resp.content
        ids = [item["id"] for item in resp.data]
        # Только 3 активных + в расписании
        assert len(ids) == 3
        # Сортировка по priority DESC
        assert ids == [str(b_high.id), str(b_mid.id), str(b_low.id)]

    # -------------- unhappy: no_active_banners_returns_200_empty --------------
    def test_no_active_banners_returns_200_empty(self):
        """Нет активных баннеров → 200 OK с пустым списком (не 404)."""
        # Создадим только неактивные/просроченные баннеры
        Banner.objects.create(
            title="Off", image_url="/i/x.jpg", target_url="/x",
            priority=10, is_active=False,
        )
        Banner.objects.create(
            title="Expired", image_url="/i/y.jpg", target_url="/y",
            priority=10, is_active=True,
            ends_at=timezone.now() - timedelta(days=1),
        )

        resp = self.client.get(BANNERS_URL)
        assert resp.status_code == 200
        assert resp.data == []

    def test_get_banners_does_not_require_auth(self):
        """Эндпоинт публичный — JWT не нужен."""
        Banner.objects.create(
            title="Public", image_url="/i/p.jpg", target_url="/p",
            priority=1, is_active=True,
        )
        client = APIClient()  # никакого токена
        resp = client.get(BANNERS_URL)
        assert resp.status_code == 200
        assert len(resp.data) == 1


@override_settings(
    SECRET_KEY="test-secret-key-for-jwt-that-is-long-enough",
)
class BannerEventsTests(TestCase):
    """POST /api/v1/banner-events — приём CTR-событий."""

    def setUp(self):
        self.client = APIClient()
        self.banner = Banner.objects.create(
            title="Promo", image_url="/i/p.jpg", target_url="/p",
            priority=10, is_active=True,
        )

    def test_click_event_recorded_returns_204(self):
        """Happy: клик по существующему баннеру → 204 и запись в БД."""
        resp = self.client.post(
            "/api/v1/banner-events",
            {"banner_id": str(self.banner.id), "event_type": "click"},
            format="json",
        )
        assert resp.status_code == 204
        assert BannerEvent.objects.filter(
            banner=self.banner, event_type="click"
        ).count() == 1

    # -------------- unhappy: click_on_unknown_banner_returns_400 --------------
    def test_click_on_unknown_banner_returns_400(self):
        """Событие по несуществующему баннеру → 400 INVALID_REQUEST, в БД ничего не пишется."""
        unknown_id = uuid.uuid4()
        resp = self.client.post(
            "/api/v1/banner-events",
            {"banner_id": str(unknown_id), "event_type": "click"},
            format="json",
        )
        assert resp.status_code == 400, resp.content
        assert resp.data["code"] == "INVALID_REQUEST"
        assert BannerEvent.objects.count() == 0

    def test_invalid_event_type_returns_400(self):
        """Невалидный event_type → 400."""
        resp = self.client.post(
            "/api/v1/banner-events",
            {"banner_id": str(self.banner.id), "event_type": "scrolled_past"},
            format="json",
        )
        assert resp.status_code == 400
        assert BannerEvent.objects.count() == 0