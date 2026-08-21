from datetime import timedelta
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from django.db.models.fields.files import FieldFile


def resolve_media_url(
    upload_file: Optional["FieldFile"], url: Optional[str], context: dict
) -> Optional[str]:
    """
    Absolute URL for an "upload or external URL" media pair, or None if
    neither is set.

    `upload_file` (e.g. an ImageField) takes priority over `url` (a plain
    URLField/string) when both are set. `upload_file.url` is relative to
    MEDIA_URL, so it needs `request` from the serializer context to become
    an absolute URL matching `url`'s shape.
    """
    if upload_file:
        request = context.get("request")
        file_url = upload_file.url
        return request.build_absolute_uri(file_url) if request else file_url
    return url or None


def format_trip_duration(duration: Optional[timedelta]) -> Optional[str]:
    """
    Formats a trip's duration as a human-readable "N Days M Nights" string.

    A single-day trip has no overnight stay, so it's rendered without a
    nights component.

    Example:
        >>> format_trip_duration(timedelta(days=7))
        '7 Days 6 Nights'
        >>> format_trip_duration(timedelta(days=1))
        '1 Day'
    """
    if not duration:
        return None

    days = duration.days
    if days <= 0:
        return None
    if days == 1:
        return "1 Day"

    nights = days - 1
    night_label = "Night" if nights == 1 else "Nights"
    return f"{days} Days {nights} {night_label}"
