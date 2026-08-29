from rest_framework.pagination import (LimitOffsetPagination,
                                       PageNumberPagination)
from rest_framework.response import Response


class CustomLimitOffsetPaginator(LimitOffsetPagination):
    max_limit = 100


class TripResponsePagination(PageNumberPagination):
    """
    API Custom paginator for trips listing.
    """

    page_size = 10

    def get_paginated_response(self, data):
        """
        Return custom paginated response as
        {
        'next': next page
        'previous': previous page
        'count': Total records
        'current': Current Page
        'pages': Total number of pages
        'data': data returned by API
        }
        """
        return Response(
            {
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "count": self.page.paginator.count,
                "current": self.page.number,
                "pages": self.page.paginator.num_pages,
                "results": data,
            }
        )


class TripBookingsPagination(PageNumberPagination):
    """
    API Custom paginator for trip bookings
    """

    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 100
