"""Sphinx configuration for django-trips."""

from importlib.metadata import version as pkg_version

project = "django-trips"
author = "Awais Jibran"
copyright = "2026, Awais Jibran"
release = pkg_version("django-trips")
version = release

extensions = ["myst_parser"]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

html_theme = "furo"

# The included README links to CONTRIBUTING.md/CODE_OF_CONDUCT.md/SECURITY.md
# at the repo root (correct for GitHub, where the README actually lives) -
# those aren't part of this doc tree (only their docs/*.md mirrors are), so
# MyST's cross-reference resolution can't find them and warns. The links
# still render and work fine in the built HTML; only the build-time warning
# is spurious.
suppress_warnings = ["myst.xref_missing"]
