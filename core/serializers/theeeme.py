"""
Theeeme serializers for OIUEEI.
"""

from rest_framework import serializers

from core.models import Theeeme

THEEEME_ROLES = ("color_01", "color_02", "color_03", "color_04", "color_05", "color_06")


def theeeme_colors(theeeme):
    """A palette as the ``color_01``..``color_06`` map of HDS token names a page paints
    with, or ``None`` when there is none."""
    if theeeme is None:
        return None
    return {role: getattr(theeeme, role) for role in THEEEME_ROLES}


class TheeemeSerializer(serializers.ModelSerializer):
    """Read-only serializer for listing theeemes."""

    class Meta:
        model = Theeeme
        fields = [
            "code",
            "name",
            "color_01",
            "color_02",
            "color_03",
            "color_04",
            "color_05",
            "color_06",
        ]
