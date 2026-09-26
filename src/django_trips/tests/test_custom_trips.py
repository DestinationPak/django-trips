from datetime import date, time, timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.admin.sites import site
from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from django_trips.choices import (
    CustomTripDateMode,
    CustomTripStatus,
    CustomTripTransport,
    FoodPreference,
    LocationType,
    TripInterest,
    TripStatus,
)
from django_trips.models import CustomTrip
from django_trips.services import (
    DRAFT_NOT_IN_PROGRESS,
    DRAFT_NOT_RESTARTABLE,
    PLAN_NOT_REVISABLE,
    create_custom_trip,
    get_source_trips,
    mark_custom_trip_drafted,
    mark_custom_trip_failed,
    restart_custom_trip_drafting,
    revise_custom_trip_plan,
)
from django_trips.tests.factories import (
    CustomTripFactory,
    HostFactory,
    LocationFactory,
    TripFactory,
    TripItineraryFactory,
    UserFactory,
)


def next_month():
    today = timezone.localdate()
    return (today.replace(day=1) + timedelta(days=32)).replace(day=1)


def days_ahead(days):
    return timezone.localdate() + timedelta(days=days)


def valid_answers(**overrides):
    answers = {
        "region": LocationFactory(type=LocationType.REGION),
        "duration": "6_7",
        "date_mode": CustomTripDateMode.MONTH,
        "target_month": next_month(),
        "month_precision": "MONTH",
        "adults": 2,
        "children": 2,
        "children_ages": [6, 9],
        "infants": 0,
        "transport": CustomTripTransport.PRIVATE_DRIVER,
        "pickup_point": "DHA Lahore",
        "pickup_time": time(6, 0),
        "meals": "BREAKFAST_DINNER",
        "food_preferences": [FoodPreference.MILD_FOR_KIDS],
        "pace": "EASY",
        "interests": [TripInterest.NATURE, TripInterest.LOCAL_FOOD],
    }
    answers.update(overrides)
    return answers


class CustomTripValidationTestCase(TestCase):
    """The cross-field rules `CustomTrip.clean()` enforces on the answers."""

    def assert_invalid(self, field, **overrides):
        custom_trip = CustomTrip(user=UserFactory(), **valid_answers(**overrides))
        with self.assertRaises(ValidationError) as caught:
            custom_trip.full_clean()
        self.assertIn(field, caught.exception.message_dict)

    def test_valid_answers_pass(self):
        CustomTrip(user=UserFactory(), **valid_answers()).full_clean()

    def test_needs_a_region_or_a_note(self):
        self.assert_invalid("region", region=None, region_note="")

    def test_region_note_alone_is_enough(self):
        CustomTrip(
            user=UserFactory(), **valid_answers(region=None, region_note="Kalash valleys")
        ).full_clean()

    def test_needs_an_adult(self):
        self.assert_invalid("adults", adults=0)

    def test_children_ages_must_match_children(self):
        self.assert_invalid("children_ages", children_ages=[6])

    def test_children_ages_must_be_between_two_and_eleven(self):
        self.assert_invalid("children_ages", children_ages=[1, 9])
        self.assert_invalid("children_ages", children_ages=[6, 12])

    @override_settings(
        DJANGO_TRIPS_CUSTOM_TRIP_CHILD_MIN_AGE=3,
        DJANGO_TRIPS_CUSTOM_TRIP_CHILD_MAX_AGE=15,
    )
    def test_child_age_range_comes_from_settings(self):
        CustomTrip(user=UserFactory(), **valid_answers(children_ages=[6, 15])).full_clean()
        self.assert_invalid("children_ages", children_ages=[2, 9])

    def test_party_size_is_capped(self):
        self.assert_invalid("adults", adults=17, children=2, children_ages=[6, 9], infants=2)

    def test_the_largest_party_passes(self):
        CustomTrip(
            user=UserFactory(), **valid_answers(adults=16, children_ages=[6, 9], infants=2)
        ).full_clean()

    @override_settings(DJANGO_TRIPS_CUSTOM_TRIP_MAX_TRAVELERS=4)
    def test_party_cap_comes_from_settings(self):
        self.assert_invalid("adults", adults=3)

    def test_month_cannot_be_in_the_past(self):
        last_month = (timezone.localdate().replace(day=1) - timedelta(days=1)).replace(day=1)
        self.assert_invalid("target_month", target_month=last_month)

    def test_this_month_is_allowed(self):
        CustomTrip(
            user=UserFactory(),
            **valid_answers(target_month=timezone.localdate().replace(day=1)),
        ).full_clean()

    def test_exact_dates_cannot_start_in_the_past(self):
        self.assert_invalid(
            "start_date",
            date_mode=CustomTripDateMode.EXACT,
            target_month=None,
            month_precision="",
            start_date=days_ahead(-1),
            end_date=days_ahead(5),
        )

    def test_month_mode_needs_a_month(self):
        self.assert_invalid("target_month", target_month=None)

    def test_target_month_is_the_first_of_the_month(self):
        self.assert_invalid("target_month", target_month=next_month().replace(day=5))

    def test_month_mode_needs_a_precision(self):
        self.assert_invalid("month_precision", month_precision="")

    def test_month_mode_rejects_exact_dates(self):
        self.assert_invalid("start_date", start_date=days_ahead(7))

    def test_exact_mode_needs_a_start_date(self):
        self.assert_invalid(
            "start_date",
            date_mode=CustomTripDateMode.EXACT,
            target_month=None,
            month_precision="",
            end_date=days_ahead(13),
        )

    def test_exact_mode_needs_both_dates(self):
        self.assert_invalid(
            "end_date",
            date_mode=CustomTripDateMode.EXACT,
            target_month=None,
            month_precision="",
            start_date=days_ahead(7),
        )

    def test_exact_mode_start_before_end(self):
        self.assert_invalid(
            "end_date",
            date_mode=CustomTripDateMode.EXACT,
            target_month=None,
            month_precision="",
            start_date=days_ahead(13),
            end_date=days_ahead(7),
        )

    def test_exact_mode_rejects_a_month(self):
        self.assert_invalid(
            "target_month",
            date_mode=CustomTripDateMode.EXACT,
            start_date=days_ahead(7),
            end_date=days_ahead(13),
        )

    def test_private_driver_needs_a_pickup_point(self):
        self.assert_invalid("pickup_point", pickup_point="")

    def test_other_transport_rejects_pickup(self):
        self.assert_invalid("pickup_point", transport=CustomTripTransport.SELF_DRIVE)

    def test_other_transport_without_pickup_passes(self):
        CustomTrip(
            user=UserFactory(),
            **valid_answers(
                transport=CustomTripTransport.SELF_DRIVE, pickup_point="", pickup_time=None
            ),
        ).full_clean()

    def test_unknown_food_preference_rejected(self):
        self.assert_invalid("food_preferences", food_preferences=["SPICY"])

    def test_repeated_interest_rejected(self):
        self.assert_invalid(
            "interests", interests=[TripInterest.NATURE, TripInterest.NATURE]
        )


class CustomTripReferenceTestCase(TestCase):
    """The public reference a custom trip gets on first save."""

    def test_reference_uses_the_default_prefix(self):
        self.assertRegex(CustomTripFactory().reference, r"^CT-\d{6}$")

    @override_settings(DJANGO_TRIPS_CUSTOM_TRIP_REFERENCE_PREFIX="DP-AI")
    def test_reference_prefix_comes_from_settings(self):
        self.assertRegex(CustomTripFactory().reference, r"^DP-AI-\d{6}$")

    def test_existing_reference_is_kept(self):
        custom_trip = CustomTripFactory()
        reference = custom_trip.reference
        custom_trip.save()
        self.assertEqual(custom_trip.reference, reference)

    def test_references_do_not_collide(self):
        references = {CustomTripFactory().reference for _ in range(20)}
        self.assertEqual(len(references), 20)

    def test_a_taken_reference_is_retried(self):
        CustomTripFactory(reference="CT-000001")
        with mock.patch("django_trips.models.random.randint", side_effect=[1, 2]):
            self.assertEqual(CustomTrip.generate_reference(), "CT-000002")

    def test_gives_up_when_every_attempt_is_taken(self):
        CustomTripFactory(reference="CT-000001")
        with mock.patch("django_trips.models.random.randint", return_value=1):
            with self.assertRaises(RuntimeError):
                CustomTrip.generate_reference()

    @override_settings(DJANGO_TRIPS_CUSTOM_TRIP_REFERENCE_ATTEMPTS=3)
    def test_number_of_attempts_comes_from_settings(self):
        CustomTripFactory(reference="CT-000001")
        with mock.patch(
            "django_trips.models.random.randint", return_value=1
        ) as randint:
            with self.assertRaises(RuntimeError):
                CustomTrip.generate_reference()
        self.assertEqual(randint.call_count, 3)


class CustomTripQuerySetTestCase(TestCase):
    def test_for_user_returns_only_their_trips(self):
        user = UserFactory()
        own = CustomTripFactory(user=user)
        CustomTripFactory()
        self.assertEqual(list(CustomTrip.objects.for_user(user)), [own])

    def test_drafting_returns_only_drafting(self):
        drafting = CustomTripFactory()
        CustomTripFactory(status=CustomTripStatus.DRAFTED)
        self.assertEqual(list(CustomTrip.objects.drafting()), [drafting])


class CreateCustomTripTestCase(TestCase):
    def test_saves_the_answers_as_drafting(self):
        user = UserFactory()
        custom_trip = create_custom_trip(user, **valid_answers())
        custom_trip.refresh_from_db()
        self.assertEqual(custom_trip.user, user)
        self.assertEqual(custom_trip.status, CustomTripStatus.DRAFTING)
        self.assertEqual(custom_trip.children_ages, [6, 9])

    def test_invalid_answers_raise_and_save_nothing(self):
        with self.assertRaises(ValidationError):
            create_custom_trip(UserFactory(), **valid_answers(adults=0))
        self.assertFalse(CustomTrip.objects.exists())


class GetSourceTripsTestCase(TestCase):
    """Which host trips a custom trip is drafted from."""

    @classmethod
    def setUpTestData(cls):
        province = LocationFactory(name="Gilgit-Baltistan", type=LocationType.PROVINCE)
        cls.chip = LocationFactory(
            name="Hunza & Gilgit", type=LocationType.REGION, parent=province
        )
        cls.region = LocationFactory(name="Hunza", type=LocationType.REGION, parent=cls.chip)
        cls.town = LocationFactory(name="Karimabad", type=LocationType.CITY, parent=cls.region)
        cls.elsewhere = LocationFactory(name="Swat", type=LocationType.REGION)
        cls.host = HostFactory(verified=True)

    def make_trip(self, **kwargs):
        kwargs.setdefault("host", self.host)
        kwargs.setdefault("status", TripStatus.PUBLISHED)
        return TripFactory(trip_schedule=None, **kwargs)

    def test_includes_trips_to_the_region_and_every_level_below(self):
        to_chip = self.make_trip(destination=self.chip)
        to_region = self.make_trip(destination=self.region)
        to_town = self.make_trip(destination=self.town)
        custom_trip = CustomTripFactory(region=self.chip)
        self.assertCountEqual(get_source_trips(custom_trip), [to_chip, to_region, to_town])

    def test_includes_trips_that_pass_through_the_region(self):
        passing = self.make_trip(destination=self.elsewhere, locations=[self.town])
        custom_trip = CustomTripFactory(region=self.chip)
        self.assertEqual(list(get_source_trips(custom_trip)), [passing])

    def test_excludes_other_regions_drafts_and_inactive_trips(self):
        self.make_trip(destination=self.elsewhere)
        self.make_trip(destination=self.town, status=TripStatus.DRAFT)
        self.make_trip(destination=self.town, is_active=False)
        self.make_trip(destination=self.town, host=HostFactory(verified=False))
        custom_trip = CustomTripFactory(region=self.chip)
        self.assertEqual(list(get_source_trips(custom_trip)), [])

    def test_without_a_hierarchy_only_the_region_itself_counts(self):
        to_chip = self.make_trip(destination=self.chip)
        self.make_trip(destination=self.town)
        custom_trip = CustomTripFactory(region=self.chip)
        with mock.patch(
            "django_trips.services.location_model_supports_hierarchy", return_value=False
        ):
            self.assertEqual(list(get_source_trips(custom_trip)), [to_chip])

    def test_no_region_means_no_source_trips(self):
        self.make_trip(destination=self.town)
        custom_trip = CustomTripFactory(region=None, region_note="Somewhere quiet")
        self.assertEqual(list(get_source_trips(custom_trip)), [])

    def test_caps_the_number_of_trips(self):
        for _ in range(3):
            self.make_trip(destination=self.town)
        custom_trip = CustomTripFactory(region=self.chip)
        self.assertEqual(len(get_source_trips(custom_trip, limit=2)), 2)

    def test_query_count_is_flat(self):
        for _ in range(3):
            trip = self.make_trip(destination=self.town)
            TripItineraryFactory(trip=trip, location=self.town)
        custom_trip = CustomTripFactory(region=self.chip)
        with self.assertNumQueries(5):
            trips = list(get_source_trips(custom_trip))
            for trip in trips:
                str(trip.destination)
                str(trip.host)
                for day in trip.itinerary_days.all():
                    str(day.location)


class MarkCustomTripDraftedTestCase(TestCase):
    def test_saves_the_plan_and_what_it_was_built_from(self):
        custom_trip = CustomTripFactory(metadata={"attempts": 1})
        source = TripFactory(trip_schedule=None)
        mark_custom_trip_drafted(
            custom_trip,
            plan={"title": "Hunza with the kids"},
            title="Hunza with the kids",
            estimate_min=Decimal("385000"),
            estimate_max=Decimal("460000"),
            source_trips=[source],
            metadata={"model": "claude-sonnet-5"},
        )
        custom_trip.refresh_from_db()
        self.assertEqual(custom_trip.status, CustomTripStatus.DRAFTED)
        self.assertEqual(custom_trip.title, "Hunza with the kids")
        self.assertEqual(custom_trip.estimate_max, Decimal("460000"))
        self.assertIsNotNone(custom_trip.drafted_at)
        self.assertEqual(list(custom_trip.source_trips.all()), [source])
        self.assertEqual(custom_trip.metadata, {"attempts": 1, "model": "claude-sonnet-5"})

    def test_refuses_a_trip_that_is_not_drafting(self):
        custom_trip = CustomTripFactory(status=CustomTripStatus.FAILED)
        with self.assertRaisesMessage(ValidationError, DRAFT_NOT_IN_PROGRESS):
            mark_custom_trip_drafted(
                custom_trip,
                plan={},
                title="",
                estimate_min=None,
                estimate_max=None,
                source_trips=[],
            )


class CustomTripStaleCopyTestCase(TestCase):
    """The services check and write the row itself, not the caller's copy."""

    def stale_copy(self, **row_changes):
        custom_trip = CustomTripFactory(metadata={"drafts": [1]})
        stale = CustomTrip.objects.get(pk=custom_trip.pk)
        CustomTrip.objects.filter(pk=custom_trip.pk).update(**row_changes)
        return stale

    def mark_drafted(self, custom_trip):
        mark_custom_trip_drafted(
            custom_trip,
            plan={"title": "Late"},
            title="Late",
            estimate_min=None,
            estimate_max=None,
            source_trips=[],
        )

    def test_a_late_run_cannot_draft_a_trip_already_drafted(self):
        stale = self.stale_copy(status=CustomTripStatus.DRAFTED, plan={"title": "First"})
        with self.assertRaisesMessage(ValidationError, DRAFT_NOT_IN_PROGRESS):
            self.mark_drafted(stale)
        self.assertEqual(CustomTrip.objects.get(pk=stale.pk).plan, {"title": "First"})

    def test_a_late_run_cannot_fail_a_trip_already_drafted(self):
        stale = self.stale_copy(status=CustomTripStatus.DRAFTED, plan={"title": "First"})
        with self.assertRaisesMessage(ValidationError, DRAFT_NOT_IN_PROGRESS):
            mark_custom_trip_failed(stale, "late")
        self.assertEqual(CustomTrip.objects.get(pk=stale.pk).status, CustomTripStatus.DRAFTED)

    def test_metadata_merges_into_the_row_not_the_copy(self):
        stale = self.stale_copy(metadata={"drafts": [1, 2]})
        mark_custom_trip_failed(stale, "refusal", metadata={"reason": "x"})
        self.assertEqual(
            CustomTrip.objects.get(pk=stale.pk).metadata, {"drafts": [1, 2], "reason": "x"}
        )

    def test_only_the_changed_fields_are_written(self):
        stale = self.stale_copy(title="Kept")
        mark_custom_trip_failed(stale, "refusal")
        self.assertEqual(CustomTrip.objects.get(pk=stale.pk).title, "Kept")

    def test_the_callers_copy_matches_what_was_saved(self):
        custom_trip = CustomTripFactory()
        self.mark_drafted(custom_trip)
        self.assertEqual(custom_trip.status, CustomTripStatus.DRAFTED)
        self.assertEqual(custom_trip.plan, {"title": "Late"})
        self.assertEqual(
            custom_trip.updated_at, CustomTrip.objects.get(pk=custom_trip.pk).updated_at
        )

    def test_each_service_locks_the_row(self):
        original = QuerySet.select_for_update
        calls = [
            lambda trip: self.mark_drafted(trip),
            lambda trip: mark_custom_trip_failed(trip, "x"),
        ]
        for call in calls:
            with mock.patch.object(
                QuerySet, "select_for_update", autospec=True, side_effect=original
            ) as select_for_update:
                call(CustomTripFactory())
            select_for_update.assert_called_once()
            self.assertIs(select_for_update.call_args.args[0].model, CustomTrip)


class ReviseCustomTripPlanTestCase(TestCase):
    """Replacing the plan of a custom trip that has already been drafted."""

    def drafted_trip(self):
        return CustomTripFactory(
            status=CustomTripStatus.DRAFTED,
            plan={"title": "Draft 1"},
            title="Draft 1",
            estimate_min=Decimal("100000"),
            estimate_max=Decimal("120000"),
            metadata={"drafts": [{"model": "claude-sonnet-5"}]},
            drafted_at=timezone.now() - timedelta(hours=1),
        )

    def test_replaces_the_plan_title_and_estimate(self):
        custom_trip = self.drafted_trip()
        revise_custom_trip_plan(
            custom_trip,
            plan={"title": "Draft 2"},
            title="Draft 2",
            estimate_min=Decimal("90000"),
            estimate_max=None,
            metadata={"chat": [{"model": "claude-sonnet-5"}]},
        )
        custom_trip.refresh_from_db()
        self.assertEqual(custom_trip.plan, {"title": "Draft 2"})
        self.assertEqual(custom_trip.title, "Draft 2")
        self.assertEqual(custom_trip.estimate_min, Decimal("90000"))
        self.assertIsNone(custom_trip.estimate_max)
        self.assertEqual(custom_trip.status, CustomTripStatus.DRAFTED)

    def test_merges_metadata(self):
        custom_trip = self.drafted_trip()
        revise_custom_trip_plan(
            custom_trip,
            plan={},
            title="",
            estimate_min=None,
            estimate_max=None,
            metadata={"chat": [1]},
        )
        custom_trip.refresh_from_db()
        self.assertEqual(
            custom_trip.metadata,
            {"drafts": [{"model": "claude-sonnet-5"}], "chat": [1]},
        )

    def test_keeps_when_it_was_first_drafted(self):
        custom_trip = self.drafted_trip()
        drafted_at = custom_trip.drafted_at
        revise_custom_trip_plan(
            custom_trip, plan={}, title="", estimate_min=None, estimate_max=None
        )
        custom_trip.refresh_from_db()
        self.assertEqual(custom_trip.drafted_at, drafted_at)

    def test_refuses_a_trip_that_is_not_drafted(self):
        for status in (CustomTripStatus.DRAFTING, CustomTripStatus.FAILED):
            custom_trip = CustomTripFactory(status=status)
            with self.assertRaisesMessage(ValidationError, PLAN_NOT_REVISABLE):
                revise_custom_trip_plan(
                    custom_trip,
                    plan={},
                    title="",
                    estimate_min=None,
                    estimate_max=None,
                )


class MarkCustomTripFailedTestCase(TestCase):
    def test_records_the_reason_and_usage(self):
        custom_trip = CustomTripFactory()
        mark_custom_trip_failed(custom_trip, "refusal", metadata={"model": "claude-sonnet-5"})
        custom_trip.refresh_from_db()
        self.assertEqual(custom_trip.status, CustomTripStatus.FAILED)
        self.assertEqual(custom_trip.failure_reason, "refusal")
        self.assertEqual(custom_trip.metadata, {"model": "claude-sonnet-5"})

    def test_refuses_a_trip_that_is_not_drafting(self):
        custom_trip = CustomTripFactory(status=CustomTripStatus.DRAFTED)
        with self.assertRaisesMessage(ValidationError, DRAFT_NOT_IN_PROGRESS):
            mark_custom_trip_failed(custom_trip, "refusal")


class RestartCustomTripDraftingTestCase(TestCase):
    stuck_after = timedelta(minutes=10)

    def test_restarts_a_failed_draft(self):
        custom_trip = CustomTripFactory(status=CustomTripStatus.FAILED, failure_reason="x")
        restart_custom_trip_drafting(custom_trip, stuck_after=self.stuck_after)
        custom_trip.refresh_from_db()
        self.assertEqual(custom_trip.status, CustomTripStatus.DRAFTING)
        self.assertEqual(custom_trip.failure_reason, "")

    def test_restarts_a_stuck_draft(self):
        custom_trip = CustomTripFactory()
        CustomTrip.objects.filter(pk=custom_trip.pk).update(
            updated_at=timezone.now() - timedelta(minutes=11)
        )
        custom_trip.refresh_from_db()
        restart_custom_trip_drafting(custom_trip, stuck_after=self.stuck_after)
        custom_trip.refresh_from_db()
        self.assertGreater(custom_trip.updated_at, timezone.now() - timedelta(minutes=1))

    def test_refuses_a_draft_still_in_progress(self):
        custom_trip = CustomTripFactory()
        with self.assertRaisesMessage(ValidationError, DRAFT_NOT_RESTARTABLE):
            restart_custom_trip_drafting(custom_trip, stuck_after=self.stuck_after)

    def test_refuses_a_finished_draft(self):
        custom_trip = CustomTripFactory(status=CustomTripStatus.DRAFTED)
        with self.assertRaisesMessage(ValidationError, DRAFT_NOT_RESTARTABLE):
            restart_custom_trip_drafting(custom_trip, stuck_after=self.stuck_after)


class CustomTripAdminTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = UserFactory(is_staff=True, is_superuser=True)
        cls.custom_trip = CustomTripFactory(
            plan={"title": "Hunza"}, metadata={"model": "claude-sonnet-5"}
        )

    def setUp(self):
        self.client.force_login(self.admin_user)

    def test_changelist_loads(self):
        response = self.client.get(reverse("admin:django_trips_customtrip_changelist"))
        self.assertContains(response, self.custom_trip.reference)

    def test_change_page_loads(self):
        response = self.client.get(
            reverse("admin:django_trips_customtrip_change", args=[self.custom_trip.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_plan_estimate_and_metadata_are_read_only(self):
        model_admin = site._registry[CustomTrip]  # pylint:disable=protected-access
        readonly = model_admin.get_readonly_fields(None)
        for field in ("plan", "estimate_min", "estimate_max", "metadata", "reference"):
            self.assertIn(field, readonly)
