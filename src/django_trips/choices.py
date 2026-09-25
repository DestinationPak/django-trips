from django.db import models


class PackageTier(models.TextChoices):
    STANDARD = "STANDARD", "Standard Package"
    BUDGET = "BUDGET", "Budget Package"
    PREMIUM = "PREMIUM", "Premium Package"


class Difficulty(models.TextChoices):
    EASY = "EASY", "Easy"
    MODERATE = "MODERATE", "Moderate"
    CHALLENGING = "CHALLENGING", "Challenging"


class FeaturedType(models.TextChoices):
    BESTSELLER = "BESTSELLER", "Bestseller"
    POPULAR = "POPULAR", "Popular"
    TOP_RATED = "TOP_RATED", "Top Rated"
    TRENDING = "TRENDING", "Trending"
    NEW = "NEW", "New"


class LocationType(models.TextChoices):
    PROVINCE = "PROVINCE", "Province"
    REGION = "REGION", "Region"
    CITY = "CITY", "City"


class AvailabilityType(models.TextChoices):
    DAILY = "DAILY", "Daily"
    WEEKLY = "WEEKLY", "Weekly"
    MONTHLY = "MONTHLY", "Monthly"
    FIX_DATE = "FIX_DATE", "Fix Date"


class TripStatus(models.TextChoices):
    """
    Editorial state of a Trip, independent of `is_active` (which is soft-delete/
    visibility, not workflow). DRAFT lets an operator build a trip's content before
    it's ready to appear in the public catalog; PUBLISHED is the current, only-ever
    behaviour for existing rows.
    """

    DRAFT = "DRAFT", "Draft"
    PUBLISHED = "PUBLISHED", "Published"


class ScheduleStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    CANCELLED = "cancelled", "Cancelled"
    FULL = "full", "Fully Booked"


class BookingStatus(models.TextChoices):
    """
    Represents the lifecycle states of a booking with allowed transitions.

    Status Flow (guest, out-of-band-payment booking model):
    └── PENDING ("NEW" in the UI - booking request submitted, not yet actioned)
        ├── CONFIRMED (staff called the traveler, advance payment received)
        │   ├── READY (remaining balance collected on arrival / fully paid)
        │   │   ├── COMPLETED (after trip completion)
        │   │   └── CANCELLED (admin-initiated only)
        │   └── CANCELLED (admin-initiated only)
        └── CANCELLED (user- or admin-initiated while pending)

    Legacy states (pre-dating the out-of-band-payment model; not part of the
    current flow above, kept for backward compatibility with existing rows):
    - WAITING_PAYMENT, PARTIAL_PAYMENT

    Restrictions:
    - CONFIRMED/READY/COMPLETED bookings cannot be automatically cancelled
    - Only admin can cancel these bookings
    - PENDING bookings can be user-cancelled
    """

    PENDING = "PENDING", "Pending"
    WAITING_PAYMENT = "WAITING_PAYMENT", "Awaiting Payment"

    # Cannot cancel the trip automatically.
    CONFIRMED = "CONFIRMED", "Confirmed"
    READY = "READY", "Ready"
    COMPLETED = "COMPLETED", "Completed"
    PARTIAL_PAYMENT = "PARTIAL_PAYMENT", "Partial Payment"

    CANCELLED = "CANCELLED", "Cancelled"

    @classmethod
    def is_cancelled(cls, status):
        return status == cls.CANCELLED

    @classmethod
    def can_be_cancelled(cls, status):
        return status in (
            cls.PENDING,
            cls.WAITING_PAYMENT,
            cls.CANCELLED,
        )


class CustomTripStatus(models.TextChoices):
    """Where a traveler's custom trip is in being drafted."""

    DRAFTING = "DRAFTING", "Drafting"
    DRAFTED = "DRAFTED", "Drafted"
    FAILED = "FAILED", "Failed"


class CustomTripDuration(models.TextChoices):
    DAYS_4_5 = "4_5", "4-5 days"
    DAYS_6_7 = "6_7", "6-7 days"
    DAYS_8_10 = "8_10", "8-10 days"


class CustomTripDateMode(models.TextChoices):
    MONTH = "MONTH", "A month or season"
    EXACT = "EXACT", "Exact dates"


class MonthPrecision(models.TextChoices):
    """Whether a custom trip's target month is that month or the season it starts."""

    MONTH = "MONTH", "Month"
    SEASON = "SEASON", "Season"


class CustomTripTransport(models.TextChoices):
    PRIVATE_DRIVER = "PRIVATE_DRIVER", "Private car and driver"
    SELF_DRIVE = "SELF_DRIVE", "Driving themselves"
    OWN_WAY = "OWN_WAY", "Reaching the region themselves"


class CustomTripMeals(models.TextChoices):
    BREAKFAST_DINNER = "BREAKFAST_DINNER", "Breakfast and dinner"
    BREAKFAST = "BREAKFAST", "Breakfast only"
    EAT_OUT = "EAT_OUT", "Eating out"


class CustomTripPace(models.TextChoices):
    EASY = "EASY", "Easy"
    BALANCED = "BALANCED", "Balanced"
    PACKED = "PACKED", "Packed"


class FoodPreference(models.TextChoices):
    MILD_FOR_KIDS = "MILD_FOR_KIDS", "Mild food for the kids"
    VEGETARIAN = "VEGETARIAN", "Vegetarian"
    NO_BEEF = "NO_BEEF", "No beef"
    ALLERGIES = "ALLERGIES", "Allergies"
    LOCAL_DISHES = "LOCAL_DISHES", "Try local dishes"


class TripInterest(models.TextChoices):
    NATURE = "NATURE", "Nature and lakes"
    CULTURE = "CULTURE", "Culture and forts"
    SHORT_HIKES = "SHORT_HIKES", "Short hikes"
    PHOTOGRAPHY = "PHOTOGRAPHY", "Photography"
    LOCAL_FOOD = "LOCAL_FOOD", "Local food"
    SHOPPING = "SHOPPING", "Shopping"
    QUIET_TIME = "QUIET_TIME", "Quiet time"
