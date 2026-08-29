""" Model mixins """

from django.utils.text import slugify


# pylint:disable=protected-access,unused-argument,keyword-arg-before-vararg
class SlugMixin:
    """Slug mixin class"""

    def create_slug(self, slug_field="name", value=None, *args, **kwargs):
        """long stuff to ensure the slug is unique"""
        if value is None:
            value = getattr(self, slug_field)
        unique_slugify(self, value)

    def save(self, *args, **kwargs):
        """Override save method for instance"""
        self.create_slug(value=self.slug, *args, **kwargs)
        return super().save(*args, **kwargs)


def unique_slugify(
    instance, value, slug_field_name="slug", queryset=None, separator="-"
):
    """Make unique slug."""
    slug_field = instance._meta.get_field(slug_field_name)
    max_length = slug_field.max_length
    slug = slugify(value)[:max_length].strip(separator)

    if not queryset:
        queryset = instance.__class__._default_manager.all()
    if instance.pk:
        queryset = queryset.exclude(pk=instance.pk)

    unique_slug = slug
    counter = 2
    while queryset.filter(**{slug_field_name: unique_slug}).exists():
        suffix = f"{separator}{counter}"
        trimmed_slug = slug[: max_length - len(suffix)].strip(separator)
        unique_slug = f"{trimmed_slug}{suffix}"
        counter += 1

    setattr(instance, slug_field.attname, unique_slug)
