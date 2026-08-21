# pylint:disable=import-error
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Min, Prefetch, Q
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema_view
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework_simplejwt.authentication import JWTAuthentication

from django_trips.api.filters import TripFilter, UpcomingTripsFilter
from django_trips.api.paginators import CustomLimitOffsetPaginator
from django_trips.api.schema_meta import (
    destinations_list_schema,
    trip_list_schema,
    trip_retrieve_schema,
    trip_wishlist_toggle_schema,
    upcoming_trips_list_schema,
)
from django_trips.api.serializers import (
    DestinationWithSchedulesSerializer,
    TripDetailSerializer,
    TripListSerializer,
    TripWishlistToggleSerializer,
    UpcomingTripListSerializer,
)
from django_trips.choices import LocationType, ScheduleStatus
from django_trips.models import (
    Trip,
    TripPackage,
    TripReview,
    TripSchedule,
    TripWishlist,
    get_active_locations_queryset,
    location_model_supports_hierarchy,
)


@extend_schema_view(
    list=trip_list_schema,
    retrieve=trip_retrieve_schema,
    wishlist=trip_wishlist_toggle_schema,
)
class TripViewSet(ReadOnlyModelViewSet):  # pylint:disable=too-many-ancestors
    """
    Public, read-only catalog of Trips.

    | Action    | HTTP Method | URL Pattern        | Reverse     | Description        |
    |-----------|-------------|--------------------|-------------|--------------------|
    | List      | GET         | /trips/            | trip-list   | Retrieve all trips |
    | Retrieve  | GET         | /trips/<id>/       | trip-detail | Retrieve a trip    |

    Notes:
    - Lookup field supports ID or slug as `{id}`.
    - List/retrieve (GET) are public. Trip management (create/update/delete) is not
      part of this surface - it lives in the tenancy-aware operator API (destipak),
      which imports TripCreateSerializer from this module directly.
    - `post` stays in http_method_names for the `wishlist` extra action below (a
      separate, detail-level URL) - it's checked once, class-wide, by Django's base
      View.dispatch() before DRF ever resolves which action a request maps to, so
      dropping it here would 405 the wishlist toggle too. create/update/destroy are
      still unreachable: ReadOnlyModelViewSet doesn't implement them, so the router
      never binds "post"/"put"/"delete" to the plain list/detail routes in the first
      place (SimpleRouter.get_method_map() only binds a verb when hasattr(view, action)).

    Authentication: Session and JWT
    """

    authentication_classes = [SessionAuthentication, JWTAuthentication]
    permission_classes = [IsAuthenticatedOrReadOnly]
    http_method_names = ["get", "post"]
    pagination_class = CustomLimitOffsetPaginator

    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = TripFilter
    # DRF's OrderingFilter validates/orders by the literal client-supplied term
    # (a 2-tuple only supplies a display label, it isn't an alias) so the
    # annotation below must be named exactly `price` to make `?ordering=price`
    # work. It's still distinct from the `starting_price` model property:
    # annotating under that name would make Django try to setattr() a value
    # onto a property with no setter, raising AttributeError per row.
    ordering_fields = ["name", "duration", "price"]
    queryset = Trip.objects.active()

    serializer_class = TripDetailSerializer

    lookup_field = "identifier"

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action == "list":
            # annotate() with an aggregate silently drops Trip.Meta's default
            # ordering (Django stops applying it once GROUP BY is involved),
            # so re-assert it explicitly here. Otherwise, with no ?ordering=
            # param, row order is whatever MySQL's query plan happens to
            # produce for that particular filter combination — same rows,
            # different order, from one request to the next.
            queryset = (
                queryset.annotate(price=Min("packages__base_price"))
                .distinct()
                .order_by(*Trip._meta.ordering)
            )  # pylint:disable=protected-access
            # Single-valued relations TripListSerializer renders per row
            # (destination, its parent for Location.region, the review
            # summary, and the host -> host.type/host.ratings chain) - safe
            # to select_related alongside the annotate()/distinct() above
            # since none of these add extra rows, unlike the M2M/reverse-FK
            # relations below.
            select_related_fields = [
                "destination",
                "host",
                "host__type",
                "host__ratings",
                "review_summary",
            ]
            if location_model_supports_hierarchy():
                select_related_fields.append("destination__parent")
            queryset = queryset.select_related(*select_related_fields)
            # Backs TripListSerializer.schedules - prefetched once per page here
            # (to_attr caches it off each trip instance) rather than one query per
            # row inside the serializer.
            queryset = queryset.prefetch_related(
                Prefetch(
                    "schedules",
                    queryset=TripSchedule.objects.upcoming()
                    .filter(status=ScheduleStatus.PUBLISHED)
                    .order_by("start_date"),
                    to_attr="_prefetched_upcoming_schedules",
                ),
                # Backs TripListSerializer.get_starting_price - same to_attr
                # trick as schedules above, since the model's starting_price
                # property builds its own fresh `.order_by().first()` query
                # that a plain prefetch_related("packages") wouldn't satisfy.
                Prefetch(
                    "packages",
                    queryset=TripPackage.objects.order_by("base_price"),
                    to_attr="_prefetched_packages_by_price",
                ),
                # Backs get_trip_review_summary_data's reviews_count - same
                # reasoning as packages above (trip.reviews.filter(...).count()
                # is a fresh query the ORM can't satisfy from a bare prefetch).
                Prefetch(
                    "reviews",
                    queryset=TripReview.objects.filter(is_verified=True),
                    to_attr="_prefetched_verified_reviews",
                ),
                "images",
                "categories",
                "facilities",
                "trust_badges",
            )
        return queryset

    def get_serializer_class(self):
        if self.action == "retrieve":
            return TripDetailSerializer
        return TripListSerializer

    def get_object(self):
        identifier = self.kwargs.get("identifier")
        if identifier.isdigit():
            return get_object_or_404(Trip, pk=int(identifier))
        return get_object_or_404(Trip, slug=identifier)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        user = self.request.user
        context["wished_trip_ids"] = (
            set(
                TripWishlist.objects.filter(user=user).values_list("trip_id", flat=True)
            )
            if user.is_authenticated
            else set()
        )
        return context

    @action(
        detail=True,
        methods=["post"],
        url_path="wishlist",
        permission_classes=[IsAuthenticated],
    )
    def wishlist(self, request, *args, **kwargs):  # pylint:disable=unused-argument
        """Toggle the current user's wishlist membership for this trip."""
        trip = self.get_object()
        wishlist_entry, created = TripWishlist.objects.get_or_create(
            user=request.user, trip=trip
        )
        if not created:
            wishlist_entry.delete()

        serializer = TripWishlistToggleSerializer({"is_wished": created})
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema_view(get=upcoming_trips_list_schema)
class UpcomingTripsListAPIView(ListAPIView):
    """
    API view to list upcoming (not-yet-started) trip schedules with optional filtering.

    Supports filtering trips by name, price range, date range, destination slug,
    and trip duration. Returns paginated list of trips with their schedule details.

    Public endpoint - no authentication required.

    Query parameters:
      - name: partial trip name (case-insensitive)
      - price_from: minimum resolved price - cheapest package's base_price
        plus this schedule's surcharge (inclusive)
      - price_to: maximum resolved price, same basis as price_from (inclusive)
      - date_from: trips starting on or after this date (YYYY-MM-DD)
      - date_to: trips ending on or before this date (YYYY-MM-DD)
      - destination: exact slug of destination (case-insensitive)
      - duration_from: minimum trip duration in days (inclusive)
      - duration_to: maximum trip duration in days (inclusive)
    """

    authentication_classes = [SessionAuthentication, JWTAuthentication]
    pagination_class = CustomLimitOffsetPaginator
    permission_classes = [IsAuthenticatedOrReadOnly]

    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = UpcomingTripsFilter
    # Same annotation-name-must-match-ordering-field convention as
    # TripViewSet.ordering_fields/get_queryset() above - `price` here is the
    # per-schedule fully resolved price (cheapest package + this schedule's
    # surcharge), not a literal model field (TripSchedule has no field named
    # `price` since the pricing reversal).
    ordering_fields = [
        "trip__name",
        "price",
        "start_date",
        "trip__duration",
    ]

    serializer_class = UpcomingTripListSerializer
    queryset = TripSchedule.objects.upcoming()

    def get_queryset(self):
        # A schedule's fully resolved price is its trip's cheapest package
        # base_price plus this specific date's surcharge - packages aren't
        # date-bound, so this is the same "cheapest tier" a traveler would
        # see if they picked this date, not an arbitrary reference price.
        return (
            super()
            .get_queryset()
            .annotate(
                trip_min_base_price=Min("trip__packages__base_price"),
            )
            .annotate(
                price=ExpressionWrapper(
                    F("trip_min_base_price") + F("additional_price"),
                    output_field=DecimalField(),
                )
            )
        )


@extend_schema_view(get=destinations_list_schema)
class ActiveDestinationsWithSchedulesView(ListAPIView):
    """Public endpoint - no authentication required."""

    permission_classes = [IsAuthenticatedOrReadOnly]
    serializer_class = DestinationWithSchedulesSerializer

    def get_queryset(self):
        # A REGION-type location (e.g. "Galiyat") may have no trips of its
        # own - trips are booked to its child towns (e.g. "Nathia Gali").
        # It still needs to appear here (with a rolled-up trips_count) since
        # travelers search for the region name, not each child town - see
        # expand_destination_slugs() in api/filters.py for the matching
        # search-side behavior.
        #
        # Scoped to type=REGION specifically (not e.g. a PROVINCE, which is
        # also technically a "parent") - otherwise every province would
        # inherit its regions'/cities' trips too and show up as a giant
        # catch-all pseudo-destination, which isn't what a province is for.
        #
        # This hierarchy rollup is django_trips' own Location concept
        # (parent/type), not part of the adapter contract - it only works
        # when DJANGO_TRIPS_LOCATION_MODEL is unswapped (the default model).
        # A swapped-in model isn't guaranteed to have parent/type at all
        # (querying/annotating a field it doesn't have raises FieldError),
        # so this falls back to a plain per-destination count with no
        # region rollup rather than assuming that shape exists.
        queryset = get_active_locations_queryset()
        if not location_model_supports_hierarchy():
            return (
                queryset.filter(destination_trips__isnull=False)
                .annotate(
                    trips_count=Count(
                        "destination_trips",
                        filter=Q(destination_trips__is_active=True),
                        distinct=True,
                    )
                )
                .distinct()
                .prefetch_related("destination_trips")
                .order_by("-trips_count", "name")
            )
        return (
            queryset.filter(
                Q(destination_trips__isnull=False)
                | Q(type=LocationType.REGION, children__destination_trips__isnull=False)
            )
            .annotate(
                trips_count=Count(
                    "destination_trips",
                    filter=Q(destination_trips__is_active=True),
                    distinct=True,
                )
                + Count(
                    "children__destination_trips",
                    filter=Q(
                        children__destination_trips__is_active=True,
                        type=LocationType.REGION,
                    ),
                    distinct=True,
                )
            )
            .distinct()
            .prefetch_related("destination_trips", "children__destination_trips")
            .order_by("-trips_count", "name")
        )
