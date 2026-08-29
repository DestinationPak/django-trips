# pylint:disable=import-error
from django.db.models import Count, Q
from drf_spectacular.utils import extend_schema_view
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticatedOrReadOnly

from django_trips.api.schema_meta import categories_list_schema
from django_trips.api.serializers import CategoryListSerializer
from django_trips.models import Category


@extend_schema_view(get=categories_list_schema)
class ActiveCategoriesListAPIView(ListAPIView):
    """Public endpoint - no authentication required."""

    permission_classes = [IsAuthenticatedOrReadOnly]
    serializer_class = CategoryListSerializer

    def get_queryset(self):
        return (
            Category.objects.active()
            .annotate(
                trips_count=Count(
                    "trips", filter=Q(trips__is_active=True), distinct=True
                )
            )
            .order_by("-trips_count", "name")
        )
