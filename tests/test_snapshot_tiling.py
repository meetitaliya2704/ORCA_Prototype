import math

import pytest

from app.snapshots.tiling import coverage_contains, padded_coverage, tile_for_coordinate


@pytest.mark.parametrize(
    ("latitude", "longitude", "lat_index", "lon_index"),
    [(18.025, 70.525, 54, 125), (-18.025, -70.525, 35, 54), (90, 180, 89, 0)],
)
def test_tile_mapping_is_deterministic(latitude, longitude, lat_index, lon_index):
    tile = tile_for_coordinate(latitude, longitude, 2.0)
    assert (tile.latitude_index, tile.longitude_index) == (lat_index, lon_index)
    assert tile == tile_for_coordinate(latitude, longitude, 2.0)


def test_exact_boundary_belongs_to_the_tile_starting_at_boundary():
    assert tile_for_coordinate(0, 0, 2).latitude_index == 45
    assert tile_for_coordinate(0, 0, 2).longitude_index == 90


def test_antimeridian_is_one_meridian_and_poles_are_clipped():
    assert tile_for_coordinate(0, 180, 2).safe_id == tile_for_coordinate(0, -180, 2).safe_id
    north = tile_for_coordinate(90, 0, 2)
    assert north.maximum_latitude == 90
    assert coverage_contains(padded_coverage(north, 50), 90, 0)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_coordinates_are_rejected(value):
    with pytest.raises(ValueError):
        tile_for_coordinate(value, 0, 2)
    with pytest.raises(ValueError):
        tile_for_coordinate(0, value, 2)


def test_padding_exceeds_logical_tile_without_changing_membership():
    tile = tile_for_coordinate(18.025, 70.525, 2)
    padded = padded_coverage(tile, 50)
    assert padded.minimum_latitude < tile.minimum_latitude
    assert padded.maximum_longitude > tile.maximum_longitude
    assert not coverage_contains(
        __import__("app.snapshots.tiling", fromlist=["logical_coverage"]).logical_coverage(tile),
        tile.maximum_latitude + 0.01,
        70.525,
    )


def test_tile_size_changes_identity():
    assert tile_for_coordinate(18, 70, 2).model_dump() != tile_for_coordinate(18, 70, 1).model_dump()
