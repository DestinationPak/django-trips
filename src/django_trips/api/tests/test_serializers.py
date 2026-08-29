from django.core.files.base import ContentFile
from django.test import RequestFactory, TestCase
from rest_framework import serializers

from django_trips.api.serializers import (
    HostSerializer,
    TripCreateSerializer,
    resolve_media_url,
)
from django_trips.models import HostRating
from django_trips.tests.factories import HostFactory, LocationFactory


class HostSerializerRatingTestCase(TestCase):
    def test_rating_defaults_to_zero_without_host_rating(self):
        host = HostFactory()
        data = HostSerializer(host).data
        self.assertEqual(data["rating"], {"rating_count": 0, "rated_by": 0})

    def test_rating_reflects_host_rating_when_present(self):
        host = HostFactory()
        HostRating.objects.create(host=host, rating_count=25, rated_by=5)
        data = HostSerializer(host).data
        self.assertEqual(data["rating"], {"rating_count": 25, "rated_by": 5})


class TripCreateSerializerValidateTestCase(TestCase):
    def test_raises_for_empty_body(self):
        with self.assertRaises(serializers.ValidationError):
            TripCreateSerializer().validate({})


class ResolveMediaUrlTestCase(TestCase):
    """Unit tests for the shared upload-vs-URL resolver used by every
    poster/image field (Location.poster, Trip.poster, TripImage.image)."""

    def setUp(self):
        super().setUp()
        self.location = LocationFactory()
        self.addCleanup(self.location.poster_image.delete, save=False)

    def test_neither_set_returns_none(self):
        self.assertIsNone(resolve_media_url(self.location.poster_image, None, {}))

    def test_url_only_returns_url(self):
        result = resolve_media_url(
            self.location.poster_image, "https://example.com/a.jpg", {}
        )
        self.assertEqual(result, "https://example.com/a.jpg")

    def test_upload_only_without_request_returns_relative_url(self):
        self.location.poster_image.save(
            "a.jpg", ContentFile(b"fake-image-bytes"), save=True
        )
        result = resolve_media_url(self.location.poster_image, None, {})
        self.assertFalse(result.startswith("http"))
        self.assertIn("a.jpg", result)

    def test_upload_with_request_returns_absolute_url(self):
        self.location.poster_image.save(
            "a.jpg", ContentFile(b"fake-image-bytes"), save=True
        )
        request = RequestFactory().get("/")
        result = resolve_media_url(
            self.location.poster_image, None, {"request": request}
        )
        self.assertTrue(result.startswith("http://testserver/"))
        self.assertIn("a.jpg", result)

    def test_upload_prioritized_over_url(self):
        self.location.poster_image.save(
            "a.jpg", ContentFile(b"fake-image-bytes"), save=True
        )
        result = resolve_media_url(
            self.location.poster_image, "https://example.com/a.jpg", {}
        )
        self.assertNotEqual(result, "https://example.com/a.jpg")
        self.assertIn("a.jpg", result)
