from enum import Enum

from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    OpenApiTypes,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers

from django_trips.api.serializers import (
    CategoryListSerializer,
    DestinationWithSchedulesSerializer,
    HostListSerializer,
    TestimonialSerializer,
    TripBookingSerializer,
    TripDetailSerializer,
    TripListSerializer,
    TripReviewSerializer,
    TripWishlistToggleSerializer,
    TrustBadgeListSerializer,
)


# pylint:disable=all
class SchemaTags(Enum):
    TRIPS = ["Trips"]
    Bookings = ["Bookings"]
    CATEGORIES = ["Categories"]
    HOSTS = ["Hosts"]
    TRUST_BADGES = ["Trust Badges"]
    TESTIMONIALS = ["Testimonials"]


error_response_serializer = inline_serializer(
    name="ErrorResponse",
    fields={
        "detail": serializers.CharField(help_text="High-level error message"),
    },
)

trip_retrieve_schema = extend_schema(
    summary="Retrieve a Trip",
    description="Get detailed information of a trip by its ID or slug, including related itinerary, locations, "
    "facilities, and host info.",
    responses={200: TripDetailSerializer},
    parameters=[
        OpenApiParameter(
            "identifier",
            OpenApiTypes.STR,
            OpenApiParameter.PATH,
            description="Unique trip ID or slug to identify the trip.",
        )
    ],
    tags=SchemaTags.TRIPS.value,
)

trip_list_schema = extend_schema(
    summary="List Trips",
    description="Retrieve a paginated list of all available trips with summary information.",
    responses={200: TripListSerializer},
    tags=SchemaTags.TRIPS.value,
    parameters=[
        OpenApiParameter(
            name="date_from",
            description="Filter trips with a published schedule starting on or "
            "after this date (YYYY-MM-DD).",
            required=False,
            type=OpenApiTypes.DATE,
        ),
        OpenApiParameter(
            name="date_to",
            description="Filter trips with a published schedule ending on or "
            "before this date (YYYY-MM-DD).",
            required=False,
            type=OpenApiTypes.DATE,
        ),
        OpenApiParameter(
            name="price_from",
            description="Filter trips with a package priced at or above this "
            "value (still requires a published schedule to be bookable).",
            required=False,
            type=OpenApiTypes.NUMBER,
        ),
        OpenApiParameter(
            name="price_to",
            description="Filter trips with a package priced at or below this "
            "value (still requires a published schedule to be bookable).",
            required=False,
            type=OpenApiTypes.NUMBER,
        ),
        OpenApiParameter(
            name="category",
            description="Filter trips by a list of category slugs, e.g. "
            "?category=hiking,camping",
            required=False,
            type=OpenApiTypes.STR,
        ),
        OpenApiParameter(
            name="ordering",
            description="Ordering of results. Example: `name`, `-duration`, `price`, `-price`",
            required=False,
            type=OpenApiTypes.STR,
        ),
    ],
)


trip_wishlist_toggle_schema = extend_schema(
    summary="Toggle trip wishlist",
    description="Add the trip to the current user's wishlist if it isn't already "
    "wishlisted, otherwise remove it. Requires authentication.",
    request=None,
    responses={
        200: TripWishlistToggleSerializer,
        403: OpenApiResponse(description="Authentication required"),
        404: OpenApiResponse(description="Trip not found"),
    },
    parameters=[
        OpenApiParameter(
            "identifier",
            OpenApiTypes.STR,
            OpenApiParameter.PATH,
            description="Unique trip ID or slug to identify the trip.",
        )
    ],
    tags=SchemaTags.TRIPS.value,
)

upcoming_trips_list_schema = extend_schema(
    summary="Upcoming Trips",
    description="List all upcoming trips with filter.",
    tags=SchemaTags.TRIPS.value,
    responses={200: TripListSerializer},
    parameters=[
        OpenApiParameter(
            name="ordering",
            description="Ordering of results. Example: `start_date`, `-price`, `trip__duration`",
            required=False,
            type=OpenApiTypes.STR,
        ),
    ],
)
destinations_list_schema = extend_schema(
    summary="Get Trip Destinations",
    description="List all trip destinations, each annotated with a count "
    "of its currently active trips. Ordered by trip count descending.",
    responses={200: DestinationWithSchedulesSerializer},
    tags=SchemaTags.TRIPS.value,
)

categories_list_schema = extend_schema(
    summary="Get Trip Categories",
    description="List all active trip categories, each annotated with a "
    "count of its currently active trips. Ordered by trip count "
    "descending.",
    responses={200: CategoryListSerializer},
    tags=SchemaTags.CATEGORIES.value,
)

testimonials_list_schema = extend_schema(
    summary="Get Testimonials",
    description="List active, verified, curated site-wide testimonials for "
    "marketing/landing-page display.",
    responses={200: TestimonialSerializer},
    tags=SchemaTags.TESTIMONIALS.value,
)

hosts_list_schema = extend_schema(
    summary="Get Trip Hosts",
    description="List all verified trip hosts, each annotated with a "
    "count of its currently active trips. Ordered by trip count "
    "descending.",
    responses={200: HostListSerializer},
    tags=SchemaTags.HOSTS.value,
)

trust_badges_list_schema = extend_schema(
    summary="Get Trust Badges",
    description="List all active trust badges, each annotated with a "
    "count of its currently active trips. Ordered by trip count "
    "descending.",
    responses={200: TrustBadgeListSerializer},
    tags=SchemaTags.TRUST_BADGES.value,
)

trip_reviews_list_schema = extend_schema(
    summary="List a trip's reviews",
    description="Paginated list of a trip's verified individual reviews, "
    "newest first. Distinct from the aggregate `review_summary` rollup "
    "shown on the trip card/header.",
    responses={200: TripReviewSerializer},
    parameters=[
        OpenApiParameter(
            "trip_id",
            OpenApiTypes.INT,
            OpenApiParameter.PATH,
            description="Numeric trip ID to list reviews for.",
        )
    ],
    tags=SchemaTags.TRIPS.value,
)

booking_create_schema = extend_schema(
    summary="Book a trip",
    description="Creates a new booking for the specified trip. The response "
    "includes the one-time `otp` field, shown only here - save it alongside "
    "the booking `number` to use the guest lookup endpoint later.",
    request=TripBookingSerializer,
    responses={
        201: TripBookingSerializer,
        400: OpenApiResponse(
            response=error_response_serializer,
            description="Invalid input data",
        ),
        403: OpenApiResponse(description="User not authorized to create booking"),
    },
    tags=SchemaTags.Bookings.value,
)

booking_list_schema = extend_schema(
    summary="List bookings",
    description=(
        "**Permission:** Admin users only. "
        "Get paginated trip bookings with essential details. Includes filtering, sorting and searching.",
    ),
    responses={
        200: TripBookingSerializer(many=True),
        400: OpenApiResponse(
            response=error_response_serializer,
            description="Invalid input data",
        ),
    },
    tags=SchemaTags.Bookings.value,
)


booking_retrieve_schema = extend_schema(
    summary="Get booking details",
    description="""  
    Retrieve complete details of a specific booking including trip information, 
    payment status, and participant details.
    """,
    responses={
        200: TripBookingSerializer,
        400: OpenApiResponse(
            response=error_response_serializer,
            description="Invalid input data",
        ),
        404: OpenApiResponse(description="Booking not found"),
    },
    tags=SchemaTags.Bookings.value,
)

booking_update_schema = extend_schema(
    summary="Update booking details",
    description="""  
    Update details of a specific booking e.g. contact details, no of persons,
    target date, message.
    """,
    responses={
        200: TripBookingSerializer,
        400: OpenApiResponse(
            response=error_response_serializer,
            description="Invalid input data",
        ),
        404: OpenApiResponse(description="Booking not found"),
    },
    tags=SchemaTags.Bookings.value,
)

booking_lookup_schema = extend_schema(
    summary="Look up a booking (guest, no login)",
    description="Retrieve a booking by its reference `number` plus one of "
    "`otp` (the 4-digit code shown at booking creation) or `email` (the "
    "address the booking was made with) - no account required.",
    parameters=[
        OpenApiParameter(
            name="number",
            description="Booking reference number, e.g. DPT00012399",
            required=True,
            type=OpenApiTypes.STR,
        ),
        OpenApiParameter(
            name="otp",
            description="4-digit code shown once at booking creation. "
            "Either this or `email` is required.",
            required=False,
            type=OpenApiTypes.STR,
        ),
        OpenApiParameter(
            name="email",
            description="Email address the booking was made with. Either "
            "this or `otp` is required.",
            required=False,
            type=OpenApiTypes.STR,
        ),
    ],
    responses={
        200: TripBookingSerializer,
        400: OpenApiResponse(
            response=error_response_serializer,
            description="Missing `number`, or missing both `otp` and `email`.",
        ),
        404: OpenApiResponse(description="No matching booking found."),
    },
    tags=SchemaTags.Bookings.value,
)

booking_cancel_schema = extend_schema(
    summary="Cancel a trip booking",
    description="Cancel a booking identified by the number in the URL. Only allowed if the booking is not already cancelled and meets cancellation criteria.",
    responses={
        200: TripBookingSerializer,
        400: OpenApiResponse(
            response=error_response_serializer,
            description="Invalid input data",
        ),
        403: OpenApiResponse(description="Not authenticated or not permitted."),
        404: OpenApiResponse(description="Booking not found."),
    },
    tags=SchemaTags.Bookings.value,
)
