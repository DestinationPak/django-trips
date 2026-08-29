# pylint:disable=import-error
from drf_spectacular.utils import extend_schema_view
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticatedOrReadOnly

from django_trips.api.paginators import TripResponsePagination
from django_trips.api.schema_meta import trip_reviews_list_schema
from django_trips.api.serializers import TripReviewSerializer
from django_trips.models import TripReview


@extend_schema_view(get=trip_reviews_list_schema)
class TripReviewListView(ListAPIView):
    """
    Public endpoint - no authentication required. Only verified reviews are
    shown, matching the `reviews_count` scoping in `get_trip_review_summary_data`
    - an unverified review shouldn't count toward the summary yet also show
    up in the list.
    """

    # Class-level queryset lets drf-spectacular introspect the model for
    # schema generation without calling get_queryset() (which needs
    # self.kwargs["trip_id"] from a real request) - see TripBookingBaseViewSet
    # for the same pattern.
    queryset = TripReview.objects.all()
    permission_classes = [IsAuthenticatedOrReadOnly]
    serializer_class = TripReviewSerializer
    pagination_class = TripResponsePagination

    def get_queryset(self):
        return (
            TripReview.objects.filter(trip_id=self.kwargs["trip_id"], is_verified=True)
            .select_related("location")
            .order_by("-created_at")
        )
