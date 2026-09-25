from datetime import timedelta
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from django_trips.choices import BookingStatus, PackageTier
from django_trips.models import BookingStatusEvent, TripSchedule
from django_trips.services import (
    ALREADY_CANCELLED,
    CANNOT_BE_CANCELLED,
    cancel_trip_booking,
    create_trip,
    create_trip_booking,
    get_effective_price,
    toggle_trip_wishlist,
    update_trip,
    validate_trip_booking,
)
from django_trips.tests.factories import (
    CategoryFactory,
    FacilityFactory,
    HostFactory,
    LocationFactory,
    TripBookingFactory,
    TripFactory,
    TripItineraryFactory,
    TripPackageFactory,
    TripPickupLocationFactory,
    TripScheduleFactory,
    UserFactory,
)


class GetEffectivePriceTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.package = TripPackageFactory(
            name=PackageTier.PREMIUM, base_price=10000, base_child_price=6000
        )

    def test_no_schedule_or_pickup_returns_package_price(self):
        result = get_effective_price(self.package)
        self.assertEqual(result, {"price": 10000, "child_price": 6000})

    def test_schedule_only_adds_its_surcharge(self):
        schedule = TripScheduleFactory(
            trip=self.package.trip, additional_price=2000, additional_child_price=1000
        )
        result = get_effective_price(self.package, schedule=schedule)
        self.assertEqual(result, {"price": 12000, "child_price": 7000})

    def test_pickup_only_adds_flat_surcharge_to_both(self):
        schedule = TripScheduleFactory(
            trip=self.package.trip, additional_price=0, additional_child_price=0
        )
        pickup = TripPickupLocationFactory(schedule=schedule, additional_price=500)
        result = get_effective_price(self.package, pickup=pickup)
        self.assertEqual(result, {"price": 10500, "child_price": 6500})

    def test_schedule_and_pickup_combine(self):
        schedule = TripScheduleFactory(
            trip=self.package.trip, additional_price=2000, additional_child_price=1000
        )
        pickup = TripPickupLocationFactory(schedule=schedule, additional_price=500)
        result = get_effective_price(self.package, schedule=schedule, pickup=pickup)
        self.assertEqual(result, {"price": 12500, "child_price": 7500})


class ValidateTripBookingTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.trip = TripFactory(trip_schedule=None)
        self.schedule = TripScheduleFactory(trip=self.trip)
        self.other_trip = TripFactory(trip_schedule=None)

    def test_matching_selection_passes_without_queries(self):
        package = TripPackageFactory(trip=self.trip)
        pickup = TripPickupLocationFactory(schedule=self.schedule)
        with self.assertNumQueries(0):
            validate_trip_booking(
                self.trip, self.schedule, package=package, pickup_location=pickup
            )

    def test_schedule_from_another_trip_is_rejected(self):
        other_schedule = TripScheduleFactory(trip=self.other_trip)
        with self.assertRaises(ValidationError) as ctx:
            validate_trip_booking(self.trip, other_schedule)
        self.assertIn("schedule", ctx.exception.message_dict)

    def test_package_from_another_trip_is_rejected(self):
        package = TripPackageFactory(trip=self.other_trip)
        with self.assertRaises(ValidationError) as ctx:
            validate_trip_booking(self.trip, self.schedule, package=package)
        self.assertIn("package", ctx.exception.message_dict)

    def test_pickup_from_another_schedule_is_rejected(self):
        pickup = TripPickupLocationFactory(
            schedule=TripScheduleFactory(trip=self.trip)
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_trip_booking(self.trip, self.schedule, pickup_location=pickup)
        self.assertIn("pickup_location", ctx.exception.message_dict)


class CreateTripBookingTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.trip = TripFactory(trip_schedule=None)
        self.schedule = TripScheduleFactory(
            trip=self.trip,
            available_seats=10,
            booked_seats=0,
            additional_price=1000,
            additional_child_price=500,
        )
        self.guest = {
            "full_name": "Foo Bar",
            "email": "foo@bar.com",
            "phone_number": "+923331234567",
            "target_date": timezone.now() + timedelta(days=7),
            "terms_accepted": True,
        }

    def book(self, **kwargs):
        return create_trip_booking(
            self.trip, self.schedule, **{"adults": 2, **self.guest, **kwargs}
        )

    def test_prices_adults_and_children_from_package_schedule_and_pickup(self):
        package = TripPackageFactory(
            trip=self.trip, base_price=10000, base_child_price=6000
        )
        pickup = TripPickupLocationFactory(schedule=self.schedule, additional_price=200)

        booking = self.book(adults=2, children=1, package=package, pickup_location=pickup)

        self.assertEqual(booking.total_price, (10000 + 1000 + 200) * 2 + (6000 + 500 + 200))

    def test_without_a_package_uses_the_standard_package(self):
        booking = self.book()

        self.assertEqual(booking.package.name, PackageTier.STANDARD)
        self.assertEqual(booking.package.trip, self.trip)

    def test_adds_the_party_to_booked_seats(self):
        self.book(adults=2, children=3)

        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.booked_seats, 5)

    def test_records_who_booked(self):
        user = UserFactory()

        booking = self.book(created_by=user)

        self.assertEqual(booking.created_by, user)

    def test_rejects_a_party_larger_than_the_seats_left(self):
        with self.assertRaises(ValidationError) as ctx:
            self.book(adults=11)

        self.assertEqual(
            ctx.exception.message_dict, {"adults": ["Only 10 seat(s) left for this schedule."]}
        )
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.booked_seats, 0)

    def test_rejects_when_terms_are_not_accepted(self):
        with self.assertRaises(ValidationError) as ctx:
            self.book(terms_accepted=False)

        self.assertIn("terms_accepted", ctx.exception.message_dict)
        self.assertFalse(self.schedule.bookings.exists())

    def test_rejects_a_selection_from_another_trip(self):
        other_package = TripPackageFactory(trip=TripFactory(trip_schedule=None))

        with self.assertRaises(ValidationError) as ctx:
            self.book(package=other_package)

        self.assertIn("package", ctx.exception.message_dict)

    def test_locks_the_schedule_row_before_checking_seats(self):
        with mock.patch.object(
            TripSchedule.objects,
            "select_for_update",
            wraps=TripSchedule.objects.select_for_update,
        ) as select_for_update:
            self.book()

        select_for_update.assert_called_once_with()


class CancelTripBookingTestCase(TestCase):
    def make_booking(self, booked_seats, **kwargs):
        schedule = TripScheduleFactory(available_seats=20, booked_seats=booked_seats)
        return TripBookingFactory(schedule=schedule, adults=2, children=1, **kwargs)

    def test_cancels_and_gives_the_seats_back(self):
        booking = self.make_booking(booked_seats=10)

        cancel_trip_booking(booking)

        booking.refresh_from_db()
        booking.schedule.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.CANCELLED)
        self.assertIsNotNone(booking.cancelled_at)
        self.assertEqual(booking.schedule.booked_seats, 7)

    def test_records_who_cancelled_and_why(self):
        user = UserFactory()
        booking = self.make_booking(booked_seats=10)

        cancel_trip_booking(booking, changed_by=user, reason="Guest asked")

        event = BookingStatusEvent.objects.filter(booking=booking).latest("pk")
        self.assertEqual(event.changed_by, user)
        self.assertEqual(event.reason, "Guest asked")

    def test_booked_seats_never_go_below_zero(self):
        booking = self.make_booking(booked_seats=1)

        cancel_trip_booking(booking)

        booking.schedule.refresh_from_db()
        self.assertEqual(booking.schedule.booked_seats, 0)

    def test_rejects_an_already_cancelled_booking(self):
        booking = self.make_booking(booked_seats=10, status=BookingStatus.CANCELLED)

        with self.assertRaisesMessage(ValidationError, ALREADY_CANCELLED):
            cancel_trip_booking(booking)

        booking.schedule.refresh_from_db()
        self.assertEqual(booking.schedule.booked_seats, 10)

    def test_rejects_a_confirmed_booking(self):
        booking = self.make_booking(booked_seats=10, status=BookingStatus.CONFIRMED)

        with self.assertRaisesMessage(ValidationError, CANNOT_BE_CANCELLED):
            cancel_trip_booking(booking)

        booking.schedule.refresh_from_db()
        self.assertEqual(booking.schedule.booked_seats, 10)


class CreateTripTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.user = UserFactory()
        self.fields = {
            "name": "Hunza in autumn",
            "host": HostFactory(),
            "departure": LocationFactory(),
            "destination": LocationFactory(),
            "duration": timedelta(days=5),
        }

    def test_creates_the_trip_with_its_links_and_itinerary(self):
        facility = FacilityFactory()
        category = CategoryFactory()
        itinerary_category = CategoryFactory()

        trip = create_trip(
            created_by=self.user,
            facilities=[facility],
            categories=[category],
            tags=["mountains"],
            itinerary=[{"day_index": 1, "title": "Arrive", "category": itinerary_category}],
            **self.fields,
        )

        self.assertEqual(trip.created_by, self.user)
        self.assertEqual(list(trip.facilities.all()), [facility])
        self.assertEqual(set(trip.categories.all()), {category, itinerary_category})
        self.assertEqual(list(trip.tags.names()), ["mountains"])
        self.assertEqual(trip.itinerary_days.get().title, "Arrive")

    def test_without_links_creates_a_bare_trip(self):
        trip = create_trip(created_by=self.user, **self.fields)

        self.assertFalse(trip.facilities.exists())
        self.assertFalse(trip.itinerary_days.exists())


class UpdateTripTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.trip = TripFactory(trip_schedule=None)

    def test_updates_fields(self):
        update_trip(self.trip, name="Renamed")

        self.trip.refresh_from_db()
        self.assertEqual(self.trip.name, "Renamed")

    def test_categories_are_only_added_never_removed(self):
        kept = CategoryFactory()
        added = CategoryFactory()
        self.trip.categories.set([kept])

        update_trip(self.trip, categories=[added])

        self.assertEqual(set(self.trip.categories.all()), {kept, added})

    def test_a_given_link_list_replaces_the_current_one(self):
        self.trip.facilities.set([FacilityFactory()])
        replacement = FacilityFactory()

        update_trip(self.trip, facilities=[replacement])

        self.assertEqual(list(self.trip.facilities.all()), [replacement])

    def test_links_left_out_stay_as_they_are(self):
        facility = FacilityFactory()
        self.trip.facilities.set([facility])

        update_trip(self.trip, name="Renamed")

        self.assertEqual(list(self.trip.facilities.all()), [facility])

    def test_itinerary_is_upserted_by_day(self):
        TripItineraryFactory(trip=self.trip, day_index=1, title="Old day one")
        TripItineraryFactory(trip=self.trip, day_index=2, title="Day two")

        update_trip(self.trip, itinerary=[{"day_index": 1, "title": "New day one"}])

        titles = dict(self.trip.itinerary_days.values_list("day_index", "title"))
        self.assertEqual(titles, {1: "New day one", 2: "Day two"})


class ToggleTripWishlistTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.user = UserFactory()
        self.trip = TripFactory(trip_schedule=None)

    def test_adds_a_trip_that_is_not_wished(self):
        self.assertTrue(toggle_trip_wishlist(self.user, self.trip))
        self.assertTrue(self.trip.wishlisted_by.filter(user=self.user).exists())

    def test_removes_a_trip_that_is_already_wished(self):
        toggle_trip_wishlist(self.user, self.trip)

        self.assertFalse(toggle_trip_wishlist(self.user, self.trip))
        self.assertFalse(self.trip.wishlisted_by.filter(user=self.user).exists())
