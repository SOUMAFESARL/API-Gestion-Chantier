"""Pagination unique du produit — 20 éléments par page (US-036)."""

from collections import OrderedDict

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class PaginationStandard(PageNumberPagination):
    page_size = 20
    page_size_query_param = "taille_page"
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response(
            OrderedDict(
                [
                    ("total", self.page.paginator.count),
                    ("page", self.page.number),
                    ("nombre_pages", self.page.paginator.num_pages),
                    ("suivant", self.get_next_link()),
                    ("precedent", self.get_previous_link()),
                    ("resultats", data),
                ]
            )
        )
