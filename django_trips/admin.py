from config_models.admin import ConfigurationModelAdmin
from django.contrib import admin

from django_trips.choices import LocationType
from django_trips.models import (
    BookingStatusEvent,
    CancellationPolicy,
    Category,
    Facility,
    Gear,
    Host,
    HostRating,
    HostType,
    Location,
    Testimonial,
    Trip,
    TripAvailability,
    TripBooking,
    TripImage,
    TripItinerary,
    TripPackage,
    TripPickupLocation,
    TripReview,
    TripReviewSummary,
    TripSchedule,
    TripStatusEvent,
    TripWishlist,
    TrustBadge,
)

# =============================================================================
# Locations
# =============================================================================


class LocationParentTypeFilter(admin.SimpleListFilter):
    """Base filter narrowing the Location changelist to children of a chosen
    parent of `location_type`. Region/Province below share the `parent` query
    param, so only one of the two is meant to be active at a time."""

    parameter_name = "parent"
    location_type = None

    def lookups(self, request, model_admin):
        parents = Location.objects.filter(type=self.location_type).order_by("name")
        return [(parent.pk, parent.name) for parent in parents]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(parent__id=self.value())
        return queryset


class RegionListFilter(LocationParentTypeFilter):
    title = "region"
    location_type = LocationType.REGION


class ProvinceListFilter(LocationParentTypeFilter):
    title = "province"
    location_type = LocationType.PROVINCE


class LocationChildInline(admin.TabularInline):
    """Inline listing of a Location's children (e.g. a region's cities)."""

    model = Location
    fk_name = "parent"
    extra = 0
    fields = ("name", "slug", "type", "is_active")
    show_change_link = True
    verbose_name = "Child location"
    verbose_name_plural = "Child locations"


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    """Location modal admin configuration"""

    list_display = ("name", "slug", "type", "parent")
    list_select_related = ("parent",)
    list_filter = ("is_active", "type", ProvinceListFilter, RegionListFilter)
    search_fields = ["name", "slug"]
    autocomplete_fields = ["parent"]
    prepopulated_fields = {"slug": ("name",)}
    inlines = [LocationChildInline]


# =============================================================================
# Hosts
# =============================================================================


class HostRatingInline(admin.StackedInline):
    model = HostRating
    extra = 0


@admin.action(
    description="Mark selected hosts as inactive (and deactivate their trips)"
)
def deactivate_hosts(modeladmin, request, queryset):
    trips_updated = Trip.objects.filter(host__in=queryset).update(is_active=False)
    hosts_updated = queryset.update(is_active=False)
    modeladmin.message_user(
        request,
        f"Deactivated {hosts_updated} host(s) and {trips_updated} of their trip(s).",
    )


@admin.register(Host)
class HostAdmin(admin.ModelAdmin):
    """Host modal admin configuration"""

    inlines = [HostRatingInline]
    actions = [deactivate_hosts]
    list_display = ("name", "description", "verified", "is_active")
    list_filter = ("verified", "is_active")
    search_fields = ["name", "description"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(HostType)
class HostTypeAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ["name"]


# =============================================================================
# Trips (core)
# Availabilities, schedules, packages, itinerary and the photo gallery all
# hang off Trip and are edited inline on TripAdmin rather than standalone.
# =============================================================================


class TripAvailabilityAdminInline(admin.TabularInline):
    """Trip availability inline modal admin"""

    model = TripAvailability
    extra = 0


class TripImageAdminInline(admin.TabularInline):
    """Trip photo gallery inline modal admin"""

    model = TripImage
    extra = 1


class TripItineraryAdminInline(admin.StackedInline):
    """Trip itinerary inline modal admin"""

    model = TripItinerary
    extra = 0


class TripScheduleAdminInline(admin.TabularInline):
    """Trip schedule inline modal admin"""

    model = TripSchedule
    extra = 0


class TripPackageAdminInline(admin.TabularInline):
    """Trip pricing package (tier) inline modal admin"""

    model = TripPackage
    extra = 0


class TripReviewSummaryInline(admin.StackedInline):
    model = TripReviewSummary
    extra = 0


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    """Trip modal admin configuration"""

    inlines = [
        TripAvailabilityAdminInline,
        TripImageAdminInline,
        TripItineraryAdminInline,
        TripScheduleAdminInline,
        TripPackageAdminInline,
        TripReviewSummaryInline,
    ]
    list_display = (
        "name",
        "host",
        "departure",
        "destination",
        "featured",
        "get_date",
    )
    list_select_related = ("host", "departure", "destination")
    list_filter = (
        "availabilities__type",
        "destination",
        "featured",
        "host",
    )
    search_fields = ["name", "description", "slug", "locations__name"]
    prepopulated_fields = {"slug": ("name",)}

    def get_queryset(self, request):
        # get_date() below walks each row's availabilities; prefetch once
        # here instead of a query per row.
        return super().get_queryset(request).prefetch_related("availabilities")

    @admin.display(description="Availability Up to")
    def get_date(self, trip):
        return [availability.end_date for availability in trip.availabilities.all()]


@admin.register(TripStatusEvent)
class TripStatusEventAdmin(admin.ModelAdmin):
    """Read-only audit trail of Trip status transitions."""

    list_display = (
        "trip",
        "old_status",
        "new_status",
        "changed_by",
        "reason",
        "created_at",
    )
    list_select_related = ("trip", "changed_by")
    list_filter = ("old_status", "new_status")
    search_fields = ("trip__name", "changed_by__username", "reason")
    readonly_fields = (
        "trip",
        "old_status",
        "new_status",
        "changed_by",
        "reason",
        "created_at",
    )


admin.site.register(CancellationPolicy, ConfigurationModelAdmin)


# =============================================================================
# Trip sub-entities
# Availability windows, dated schedules, pricing tiers, per-schedule pickup
# points, and the day-by-day itinerary - also manageable standalone.
# =============================================================================


@admin.register(TripAvailability)
class TripAvailabilityAdmin(admin.ModelAdmin):
    list_display = ("trip", "type", "price", "start_date", "end_date")
    list_select_related = ("trip",)
    list_filter = ("type", "start_date", "end_date")


@admin.register(TripSchedule)
class TripScheduleAdmin(admin.ModelAdmin):
    """Trip schedule admin configuration"""

    list_display = (
        "trip",
        "status",
        "additional_price",
        "additional_child_price",
        "start_date",
        "end_date",
    )
    list_select_related = ("trip",)
    list_filter = (
        "start_date",
        "end_date",
        "status",
        "additional_price",
    )
    search_fields = ("trip__name", "status")
    raw_id_fields = ("trip",)


@admin.register(TripPackage)
class TripPackageAdmin(admin.ModelAdmin):
    """Trip pricing package (Standard/Budget/Premium) admin configuration"""

    list_display = ("trip", "name", "base_price", "base_child_price")
    list_select_related = ("trip",)
    list_filter = ("name",)
    search_fields = ["trip__name"]


@admin.register(TripPickupLocation)
class TripPickupLocationAdmin(admin.ModelAdmin):
    list_display = ("schedule", "location", "additional_price")
    list_select_related = ("schedule__trip", "location")
    list_filter = ("location",)
    search_fields = ["schedule__trip__name"]


@admin.register(TripItinerary)
class TripItineraryAdmin(admin.ModelAdmin):
    """Trip itinerary modal admin configuration"""

    list_display = ("trip", "description")
    list_select_related = ("trip",)
    list_filter = ("trip",)
    search_fields = ["trip__name"]


# =============================================================================
# Bookings & wishlists
# =============================================================================


@admin.register(TripBooking)
class TripBookingSummaryAdmin(admin.ModelAdmin):
    list_display = ("number", "full_name", "schedule", "status", "phone_number", "message")
    list_select_related = ("schedule__trip",)
    search_fields = ["schedule__trip__name", "full_name", "number"]
    list_filter = ("status", "created", "terms_accepted")
    readonly_fields = ("number", "otp", "terms_accepted", "created_by")
    raw_id_fields = ("schedule",)

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        # Package/pickup choices are schedule-scoped, so narrow them to this
        # booking's own trip/schedule - otherwise the dropdown lists every
        # package across every trip, or every pickup point across every
        # schedule, most of which can never legitimately apply to this booking.
        if obj is not None and obj.schedule_id:
            form.base_fields["package"].queryset = TripPackage.objects.filter(
                trip_id=obj.schedule.trip_id
            )
            form.base_fields["pickup_location"].queryset = (
                TripPickupLocation.objects.filter(schedule_id=obj.schedule_id)
            )
        return form


@admin.register(BookingStatusEvent)
class BookingStatusEventAdmin(admin.ModelAdmin):
    """Read-only audit trail of TripBooking status transitions."""

    list_display = (
        "booking",
        "old_status",
        "new_status",
        "changed_by",
        "reason",
        "created_at",
    )
    list_select_related = ("booking", "changed_by")
    list_filter = ("old_status", "new_status")
    search_fields = ("booking__number", "changed_by__username", "reason")
    readonly_fields = (
        "booking",
        "old_status",
        "new_status",
        "changed_by",
        "reason",
        "created_at",
    )


@admin.register(TripWishlist)
class TripWishlistAdmin(admin.ModelAdmin):
    list_display = ("user", "trip", "created_at")
    list_select_related = ("user", "trip")
    search_fields = ["user__username", "trip__name"]
    list_filter = ("created_at",)


# =============================================================================
# Reviews & testimonials
# =============================================================================


@admin.register(TripReview)
class TripReviewAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "trip",
        "location",
        "meals",
        "accommodation",
        "transport",
        "value_for_money",
        "overall",
        "is_verified",
    )
    list_select_related = ("trip", "location")
    list_filter = ("is_verified", "trip", "overall")
    search_fields = ["trip__name", "name"]


@admin.register(TripReviewSummary)
class TripReviewSummaryAdmin(admin.ModelAdmin):
    list_display = (
        "trip",
        "meals",
        "accommodation",
        "transport",
        "value_for_money",
        "overall",
    )
    list_select_related = ("trip",)
    list_filter = ("overall",)
    search_fields = ["trip__name"]


@admin.action(description="Mark selected testimonials as active")
def activate_testimonials(modeladmin, request, queryset):
    updated = queryset.update(is_active=True)
    modeladmin.message_user(request, f"Marked {updated} testimonial(s) as active.")


@admin.action(description="Mark selected testimonials as inactive")
def deactivate_testimonials(modeladmin, request, queryset):
    updated = queryset.update(is_active=False)
    modeladmin.message_user(request, f"Marked {updated} testimonial(s) as inactive.")


@admin.action(description="Mark selected testimonials as verified")
def verify_testimonials(modeladmin, request, queryset):
    updated = queryset.update(is_verified=True)
    modeladmin.message_user(request, f"Marked {updated} testimonial(s) as verified.")


@admin.action(description="Mark selected testimonials as unverified")
def unverify_testimonials(modeladmin, request, queryset):
    updated = queryset.update(is_verified=False)
    modeladmin.message_user(request, f"Marked {updated} testimonial(s) as unverified.")


@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ("name", "location", "is_verified", "is_active", "created_at")
    list_select_related = ("location",)
    list_filter = ("is_verified", "is_active")
    search_fields = ["name", "quote"]
    actions = [
        activate_testimonials,
        deactivate_testimonials,
        verify_testimonials,
        unverify_testimonials,
    ]


# =============================================================================
# Taxonomy / lookup tables
# =============================================================================


@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    """Facility modal admin configuration"""

    list_display = ("name", "slug", "icon")
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(TrustBadge)
class TrustBadgeAdmin(admin.ModelAdmin):
    """Trust badge modal admin configuration"""

    list_display = ("name", "slug", "icon")
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "icon")
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Gear)
class GearAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}
