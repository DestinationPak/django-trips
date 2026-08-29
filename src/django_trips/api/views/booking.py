# pylint:disable=import-error,too-many-ancestors

from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema_view
from rest_framework import filters, generics, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework_simplejwt.authentication import JWTAuthentication

from django_trips.api.filters import TripBookingFilterSet
from django_trips.api.paginators import TripBookingsPagination
from django_trips.api.schema_meta import (
    booking_cancel_schema,
    booking_create_schema,
    booking_list_schema,
    booking_lookup_schema,
    booking_retrieve_schema,
    booking_update_schema,
)
from django_trips.api.serializers import TripBookingSerializer
from django_trips.choices import BookingStatus
from django_trips.models import TripBooking


@extend_schema_view(
    retrieve=booking_retrieve_schema,
    update=booking_update_schema,
    cancel=booking_cancel_schema,
)
class TripBookingRetrieveUpdateViewSet(GenericViewSet, generics.RetrieveUpdateAPIView):
    queryset = TripBooking.objects.all()
    permission_classes = [IsAuthenticated]
    authentication_classes = [SessionAuthentication, JWTAuthentication]
    serializer_class = TripBookingSerializer

    http_method_names = ["get", "post", "put"]

    lookup_field = "number"

    def get_queryset(self):
        return TripBooking.objects.filter(created_by=self.request.user)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        return {**context, **self.kwargs}

    def get_object(self):
        trip_booking: "TripBooking" = super().get_object()
        self.kwargs["trip_id"] = trip_booking.schedule.trip.id
        return trip_booking

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, *args, **kwargs):  # pylint:disable=unused-argument
        booking = self.get_object()
        if BookingStatus.is_cancelled(booking.status):
            return Response(
                {"detail": "Booking is already cancelled"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not booking.can_be_cancelled():
            return Response(
                {"detail": "Automatic cancellation not allowed at this time."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Perform cancellation
        booking.cancel()

        # Send notifications, process refunds, etc.
        # send_cancellation_email(booking)

        serializer = self.get_serializer(booking)
        return Response(serializer.data, status=status.HTTP_200_OK)


class TripBookingBaseViewSet(generics.GenericAPIView):
    queryset = TripBooking.objects.all()
    permission_classes = [IsAuthenticated]
    authentication_classes = [SessionAuthentication, JWTAuthentication]
    serializer_class = TripBookingSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        return {**context, **self.kwargs}


@extend_schema_view(get=booking_list_schema)
class TripBookingListView(TripBookingBaseViewSet, generics.ListAPIView):
    pagination_class = TripBookingsPagination
    permission_classes = (IsAdminUser,)
    serializer_class = TripBookingSerializer

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    search_fields = [
        "number",
        "schedule__trip__name",
        "full_name",
        "phone_number",
    ]
    filterset_class = TripBookingFilterSet
    ordering_fields = ["full_name", "target_date", "created", "adults", "children"]
    ordering = ["-created"]

    def get_queryset(self):
        return TripBooking.objects.filter(schedule__trip__id=self.kwargs["trip_id"])


@extend_schema_view(post=booking_create_schema)
class TripBookingCreateView(TripBookingBaseViewSet, generics.CreateAPIView):
    pagination_class = TripBookingsPagination
    # Guest-first: booking is a request, not a paid transaction, so it must
    # work for anonymous users. `created_by` is set from `request.user` when
    # authenticated, else left null (see TripBookingSerializer.validate()).
    permission_classes = (AllowAny,)
    serializer_class = TripBookingSerializer


@extend_schema_view(get=booking_lookup_schema)
class TripBookingLookupView(generics.RetrieveAPIView):
    """
    Anonymous "look up my booking" endpoint.

    Scoped to a booking `number` AND one more proof-of-ownership factor -
    either its 4-digit `otp` or its `email` - not `number` alone, so a
    guessed or leaked reference number can't be used to pull up someone
    else's booking. Accounts don't exist yet in this release, so one of
    these pairs is the only thing a guest has to prove they own a booking.
    """

    queryset = TripBooking.objects.all()
    serializer_class = TripBookingSerializer
    permission_classes = (AllowAny,)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        return {**context, **self.kwargs}

    def get_object(self):
        number = self.request.query_params.get("number")
        otp = self.request.query_params.get("otp")
        email = self.request.query_params.get("email")

        if not number or not (otp or email):
            raise ValidationError(
                {
                    "detail": "`number` and one of `otp` or `email` query "
                    "parameters are required."
                }
            )

        bookings = TripBooking.objects.filter(number=number).prefetch_related(
            "status_events"
        )
        if otp:
            bookings = bookings.filter(otp=otp)
        else:
            bookings = bookings.filter(email__iexact=email)

        booking = get_object_or_404(bookings)
        self.kwargs["trip_id"] = booking.schedule.trip.id
        return booking
