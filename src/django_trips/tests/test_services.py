from django.test import TestCase

from django_trips.choices import PackageTier
from django_trips.services import get_effective_price
from django_trips.tests.factories import (
    TripPackageFactory,
    TripPickupLocationFactory,
    TripScheduleFactory,
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
