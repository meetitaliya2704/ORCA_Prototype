from argparse import Namespace
from datetime import UTC, datetime

import pytest

from app.jobs.profile_marine import (
    SOURCES,
    build_parser,
    build_request,
    parse_datetime,
)


def test_profile_source_selection_and_default_isolated_cold_mode():
    args = build_parser().parse_args(["--source", "sst"])
    assert args.source == "sst"
    assert args.mode == "cold"
    assert "conditions" in SOURCES


def test_profile_requests_use_reproducible_explicit_times():
    at = datetime(2026, 9, 1, 18, tzinfo=UTC)
    path, params = build_request("sst", 18.025, 70.525, at)
    assert path == "/v1/marine/sst"
    assert params == {
        "latitude": 18.025,
        "longitude": 70.525,
        "at": "2026-09-01T18:00:00Z",
    }
    event_path, event_params = build_request("sea_level_events", 18.025, 70.525, at)
    assert event_path.endswith("/events")
    assert event_params["hours"] == 48


def test_profile_rejects_naive_time():
    with pytest.raises(Exception):
        parse_datetime("2026-09-01T18:00:00")


def test_profile_output_location_is_user_selected_and_no_destructive_option_exists():
    actions = build_parser()._actions
    destinations = {action.dest for action in actions}
    assert "output" in destinations
    assert not destinations.intersection({"flush_redis", "delete_cache", "clear_cache"})
