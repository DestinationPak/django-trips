# pylint:disable=import-error
from drf_spectacular.utils import extend_schema_view
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticatedOrReadOnly

from django_trips.api.schema_meta import trust_badges_list_schema
from django_trips.api.serializers import TrustBadgeListSerializer
from django_trips.models import TrustBadge


@extend_schema_view(get=trust_badges_list_schema)
class ActiveTrustBadgesListAPIView(ListAPIView):
    """Public endpoint - no authentication required."""

    permission_classes = [IsAuthenticatedOrReadOnly]
    serializer_class = TrustBadgeListSerializer

    def get_queryset(self):
        return TrustBadge.objects.active().with_trip_counts()
