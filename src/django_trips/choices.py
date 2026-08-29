from django.db import models


class PackageTier(models.TextChoices):
    STANDARD = "STANDARD", "Standard Package"
    BUDGET = "BUDGET", "Budget Package"
    PREMIUM = "PREMIUM", "Premium Package"


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
