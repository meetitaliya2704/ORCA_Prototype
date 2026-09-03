from __future__ import annotations

import math

from app.snapshots.models import SnapshotCoverage, TileKey


EARTH_KM_PER_DEGREE = 111.195


def normalize_longitude(longitude: float) -> float:
    if not math.isfinite(longitude):
        raise ValueError("longitude must be finite")
    normalized = ((longitude + 180.0) % 360.0) - 180.0
    return -180.0 if normalized == 180.0 else normalized


def tile_for_coordinate(latitude: float, longitude: float, tile_size: float) -> TileKey:
    if not math.isfinite(latitude) or not -90 <= latitude <= 90:
        raise ValueError("latitude must be finite and between -90 and 90")
    if not math.isfinite(tile_size) or tile_size <= 0 or tile_size > 30:
        raise ValueError("tile size must be finite and between 0 and 30 degrees")
    longitude = normalize_longitude(longitude)
    latitude_slots = math.ceil(180.0 / tile_size)
    longitude_slots = math.ceil(360.0 / tile_size)
    latitude_index = min(latitude_slots - 1, math.floor((latitude + 90.0) / tile_size))
    longitude_index = min(longitude_slots - 1, math.floor((longitude + 180.0) / tile_size))
    minimum_latitude = -90.0 + latitude_index * tile_size
    maximum_latitude = min(90.0, minimum_latitude + tile_size)
    minimum_longitude = -180.0 + longitude_index * tile_size
    raw_maximum_longitude = minimum_longitude + tile_size
    wraps = raw_maximum_longitude > 180.0
    maximum_longitude = normalize_longitude(raw_maximum_longitude) if wraps else raw_maximum_longitude
    return TileKey(
        latitude_index=latitude_index,
        longitude_index=longitude_index,
        tile_size_degrees=tile_size,
        minimum_latitude=minimum_latitude,
        maximum_latitude=maximum_latitude,
        minimum_longitude=minimum_longitude,
        maximum_longitude=maximum_longitude,
        antimeridian_wrap=wraps,
    )


def logical_coverage(tile: TileKey) -> SnapshotCoverage:
    return SnapshotCoverage(
        minimum_latitude=tile.minimum_latitude,
        maximum_latitude=tile.maximum_latitude,
        minimum_longitude=tile.minimum_longitude,
        maximum_longitude=tile.maximum_longitude,
        antimeridian_wrap=tile.antimeridian_wrap,
    )


def padded_coverage(tile: TileKey, radius_km: float, grid_degrees: float = 0.05) -> SnapshotCoverage:
    # Radius plus one grid cell and a 10% margin avoids truncating a fallback ring.
    latitude_padding = radius_km / EARTH_KM_PER_DEGREE * 1.1 + grid_degrees
    edge_latitude = max(abs(tile.minimum_latitude), abs(tile.maximum_latitude))
    cosine = abs(math.cos(math.radians(min(edge_latitude, 89.999999))))
    longitude_padding = min(
        180.0,
        radius_km / (EARTH_KM_PER_DEGREE * cosine) * 1.1 + grid_degrees,
    )
    minimum_latitude = max(-90.0, tile.minimum_latitude - latitude_padding)
    maximum_latitude = min(90.0, tile.maximum_latitude + latitude_padding)
    minimum_longitude = tile.minimum_longitude - longitude_padding
    maximum_longitude = tile.maximum_longitude + longitude_padding
    wraps = tile.antimeridian_wrap or minimum_longitude < -180 or maximum_longitude > 180
    if not wraps:
        return SnapshotCoverage(
            minimum_latitude=minimum_latitude,
            maximum_latitude=maximum_latitude,
            minimum_longitude=minimum_longitude,
            maximum_longitude=maximum_longitude,
        )
    return SnapshotCoverage(
        minimum_latitude=minimum_latitude,
        maximum_latitude=maximum_latitude,
        minimum_longitude=normalize_longitude(minimum_longitude),
        maximum_longitude=normalize_longitude(maximum_longitude),
        antimeridian_wrap=True,
    )


def coverage_contains(coverage: SnapshotCoverage, latitude: float, longitude: float) -> bool:
    longitude = normalize_longitude(longitude)
    if not coverage.minimum_latitude <= latitude <= coverage.maximum_latitude:
        return False
    if coverage.antimeridian_wrap:
        return longitude >= coverage.minimum_longitude or longitude <= coverage.maximum_longitude
    return coverage.minimum_longitude <= longitude <= coverage.maximum_longitude
