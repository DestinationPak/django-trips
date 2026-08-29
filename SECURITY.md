# Security Policy

## Supported Versions

Only the latest published release on [PyPI](https://pypi.org/project/django-trips/)
receives security fixes. There is no long-term-support branch at this stage.

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for a security vulnerability.

Instead, use one of:

- GitHub's private vulnerability reporting: open the "Security" tab on this
  repository and select "Report a vulnerability".
- Email awaisdar001@gmail.com with a description of the issue, steps to
  reproduce, and its potential impact.

This is a small, single-maintainer project - please allow a few days for an
initial response. Once a report is confirmed, a fix will be released as a new
PATCH version (or MINOR if a behavior change is unavoidable) and credited in
`CHANGELOG.md`, unless you ask to remain anonymous.

## Scope notes

`django_trips.TripBooking` stores guest-provided personal data (name, email).
This package itself has no multi-tenant membership layer of its own by design
(that layer belongs to whatever project installs this app - e.g. destipak's
`djangoapps/trip_hosts/`), but its own booking-lookup and authenticated
retrieve/update/cancel endpoints are squarely in scope: a report that one
guest's or host's booking data is reachable through this package's own API
without proper authorization is a real vulnerability, not an architectural
trade-off.
