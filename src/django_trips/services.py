"""Pricing calculations spanning TripSchedule/TripPackage/TripPickupLocation."""


def get_effective_price(package, schedule=None, pickup=None):
    """
    Resolve the final per-person price for a specific package.

    `package.base_price`/`base_child_price` are the tier's stable, absolute
    menu price. `schedule.additional_price`/`additional_child_price` is a
    flat per-date surcharge added on top of it (0 for a regular date, e.g.
    weekend/holiday/peak pricing). `pickup.additional_price` is a flat
    surcharge added to both the adult and child price alike.
    """
    surcharge_adult = schedule.additional_price if schedule else 0
    surcharge_child = schedule.additional_child_price if schedule else 0
    pickup_addl = pickup.additional_price if pickup else 0

    return {
        "price": package.base_price + surcharge_adult + pickup_addl,
        "child_price": package.base_child_price + surcharge_child + pickup_addl,
    }
