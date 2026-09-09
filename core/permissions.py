"""
DRF permission classes for OIUEEI.

Object-level permissions for Things and Collections.
"""

from rest_framework.permissions import BasePermission


class IsThingOwner(BasePermission):
    """Object-level: request user is the Thing owner."""

    def has_object_permission(self, request, view, obj):
        return obj.is_owner(request.user.code)


class IsCollectionOwner(BasePermission):
    """Object-level: request user is the Collection owner."""

    def has_object_permission(self, request, view, obj):
        return obj.is_owner(request.user.code)


class IsCollectionCurator(BasePermission):
    """Object-level: request user is the Collection owner or a co-owner.

    The admin tier — everything except deleting the collection, which stays
    `IsCollectionOwner` (the CASCADE-delete root). Promoting and demoting a
    co-curator is curator-wide now (2026-09, co-curators in PROPRIETARY).
    """

    def has_object_permission(self, request, view, obj):
        return obj.is_curator(request.user.code)
