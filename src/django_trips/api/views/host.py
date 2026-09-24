# pylint:disable=import-error
from drf_spectacular.utils import extend_schema_view
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticatedOrReadOnly

from django_trips.api.schema_meta import hosts_list_schema
from django_trips.api.serializers import HostListSerializer
from django_trips.models import Host


@extend_schema_view(get=hosts_list_schema)
class ActiveHostsListAPIView(ListAPIView):
    """Public endpoint - no authentication required."""

    permission_classes = [IsAuthenticatedOrReadOnly]
    serializer_class = HostListSerializer

    def get_queryset(self):
        return Host.objects.active().with_trip_counts()
