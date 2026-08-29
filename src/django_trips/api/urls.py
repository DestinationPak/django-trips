from django.urls import path
from drf_spectacular.views import (SpectacularAPIView, SpectacularRedocView,
                                   SpectacularSwaggerView)
from rest_framework.routers import DefaultRouter

from django_trips.api.views import (booking, category, host, review,
                                    testimonial, trip, trust_badge)
from django_trips.api.views.trip import (ActiveDestinationsWithSchedulesView,
                                         TripViewSet)

app_name = "trips-api"

router = DefaultRouter()
router.register(r"trips", TripViewSet, basename="trip")
router.register(
    r"trips/bookings", booking.TripBookingRetrieveUpdateViewSet, basename="booking"
)

app_urlpatterns = [
    path(
        "trips/upcoming/",
        trip.UpcomingTripsListAPIView.as_view(),
        name="upcoming-trips-list",
    ),
    path(
        "destinations/",
        trip.ActiveDestinationsWithSchedulesView.as_view(),
        name="destinations",
    ),
    path(
        "categories/",
        category.ActiveCategoriesListAPIView.as_view(),
        name="categories",
    ),
    path(
        "hosts/",
        host.ActiveHostsListAPIView.as_view(),
        name="hosts",
    ),
    path(
        "trust-badges/",
        trust_badge.ActiveTrustBadgesListAPIView.as_view(),
        name="trust-badges",
    ),
    path(
        "testimonials/",
        testimonial.ActiveTestimonialsListAPIView.as_view(),
        name="testimonials",
    ),
    # Trip Bookings endpoint.
    path(
        "trips/<int:trip_id>/bookings/",
        booking.TripBookingListView.as_view(),
        name="trip-bookings",
    ),
    path(
        "trips/<int:trip_id>/bookings/create/",
        booking.TripBookingCreateView.as_view(),
        name="trip-bookings-create",
    ),
    path(
        "trips/<int:trip_id>/reviews/",
        review.TripReviewListView.as_view(),
        name="trip-reviews",
    ),
    path(
        "trips/bookings/lookup/",
        booking.TripBookingLookupView.as_view(),
        name="trip-bookings-lookup",
    ),
    *router.urls,
]

schema_urls = [
    # urlconf pins the generator to this module alone - unset, drf-spectacular walks the
    # *host* project's ROOT_URLCONF by default, so this would describe every DRF view in
    # whatever project installs this app, not just the trips lib's own endpoints.
    # custom_settings makes the schema self-identifying regardless of the host's own
    # SPECTACULAR_SETTINGS (which may have any TITLE, or none at all, set for its own APIs).
    # This module lands at "schema/redoc/" under wherever the host mounts it plus this
    # app's own "v1/" (django_trips/urls.py) - e.g. destipak mounts at api/v1/trips/, giving
    # /api/v1/trips/v1/schema/redoc/.
    path(
        "schema/",
        SpectacularAPIView.as_view(
            urlconf="django_trips.api.urls",
            custom_settings={
                "TITLE": "Django Trips API",
                "DESCRIPTION": "Django Trips management restful API",
                "VERSION": "1.0.0",
            },
        ),
        name="schema",
    ),
    path(
        "schema/swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="trips-api:schema"),
        name="swagger-ui",
    ),
    path(
        "schema/redoc/",
        SpectacularRedocView.as_view(url_name="trips-api:schema"),
        name="redoc",
    ),
]

urlpatterns = [*app_urlpatterns, *schema_urls]
