# pylint:disable=import-error
from drf_spectacular.utils import extend_schema_view
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticatedOrReadOnly

from django_trips.api.schema_meta import testimonials_list_schema
from django_trips.api.serializers import TestimonialSerializer
from django_trips.models import Testimonial


@extend_schema_view(get=testimonials_list_schema)
class ActiveTestimonialsListAPIView(ListAPIView):
    """Public endpoint - no authentication required."""

    permission_classes = [IsAuthenticatedOrReadOnly]
    serializer_class = TestimonialSerializer

    def get_queryset(self):
        return (
            Testimonial.objects.active()
            .verified()
            .select_related("location")
        )
