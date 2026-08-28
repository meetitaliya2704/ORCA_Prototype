from datetime import UTC, date, datetime

import pytest

from app.schemas.pfz import (
    DiscoveredPFZSector,
    FailedPFZSector,
    PFZAdvisory,
    PFZCacheStatus,
    PFZLocation,
    PFZSectorErrorCode,
    PFZSnapshot,
    PFZSnapshotCompleteness,
    SuccessfulPFZSector,
)
from app.services.geospatial import (
    compass_direction,
    haversine_distance_km,
    initial_bearing_deg,
)
from app.services.pfz import (
    NoValidPFZError,
    PFZNearestService,
    normalize_pfz_validity,
)


QUERY_TIME = datetime(2026, 8, 27, 12, tzinfo=UTC)


def make_advisory(
    *,
    sector_code: str = "SEC001",
    region_name: str = "Gujarat",
    landing_centre: str = "Lakhi Bandar",
    latitude: float = 22.7167,
    longitude: float = 68.95,
    forecast_date: date = date(2026, 8, 27),
    valid_until: date = date(2026, 8, 27),
) -> PFZAdvisory:
    return PFZAdvisory(
        sector_code=sector_code,
        region_name=region_name,
        forecast_date=forecast_date,
        valid_until=valid_until,
        locations=[
            PFZLocation(
                landing_centre=landing_centre,
                direction="SE",
                bearing_deg=141,
                distance_min_km=122,
                distance_max_km=127,
                depth_min_m=2,
                depth_max_m=7,
                latitude=latitude,
                longitude=longitude,
            )
        ],
        source_url=f"https://incois.test/TextData?secid={sector_code}",
        fetched_at=QUERY_TIME,
    )


def make_snapshot(
    advisories: list[PFZAdvisory],
    *,
    cache_status: PFZCacheStatus = PFZCacheStatus.FRESH,
    partial: bool = False,
) -> PFZSnapshot:
    successes = [
        SuccessfulPFZSector(
            discovered_sector=DiscoveredPFZSector(
                sector_code=advisory.sector_code,
                display_label=f"Discovery {advisory.sector_code}",
            ),
            advisory=advisory,
        )
        for advisory in advisories
    ]
    failures = (
        [
            FailedPFZSector(
                discovered_sector=DiscoveredPFZSector(
                    sector_code="SEC099",
                    display_label="Unavailable sector",
                ),
                code=PFZSectorErrorCode.SOURCE_UNAVAILABLE,
                message="Sector unavailable",
            )
        ]
        if partial
        else []
    )
    discovered = [
        *(result.discovered_sector for result in successes),
        *(result.discovered_sector for result in failures),
    ]
    return PFZSnapshot(
        generated_at=QUERY_TIME,
        retrieved_at=QUERY_TIME,
        discovered_sector_count=len(discovered),
        successful_sector_count=len(successes),
        failed_sector_count=len(failures),
        discovered_sectors=discovered,
        successful_sectors=successes,
        failed_sectors=failures,
        total_location_count=sum(
            len(result.advisory.locations) for result in successes
        ),
        completeness=(
            PFZSnapshotCompleteness.PARTIAL
            if partial
            else PFZSnapshotCompleteness.COMPLETE
        ),
        cache_status=cache_status,
        warnings=["SEC099 unavailable"] if partial else [],
        source_url="https://incois.test/TextDataHome",
    )


class FakeSnapshotService:
    def __init__(self, snapshot: PFZSnapshot) -> None:
        self.snapshot = snapshot
        self.calls = 0

    async def get_snapshot(self) -> PFZSnapshot:
        self.calls += 1
        return self.snapshot


def make_nearest_service(
    snapshot: PFZSnapshot,
    *,
    now: datetime = QUERY_TIME,
) -> tuple[PFZNearestService, FakeSnapshotService]:
    snapshot_service = FakeSnapshotService(snapshot)
    return (
        PFZNearestService(
            snapshot_service=snapshot_service,
            now=lambda: now,
        ),
        snapshot_service,
    )


def test_same_point_haversine_distance_is_zero() -> None:
    assert haversine_distance_km(21.5, 69.5, 21.5, 69.5) == pytest.approx(0)


def test_one_degree_longitude_at_equator_is_about_111_195_km() -> None:
    assert haversine_distance_km(0, 0, 0, 1) == pytest.approx(
        111.195,
        abs=0.001,
    )


@pytest.mark.parametrize(
    ("destination", "expected"),
    [
        ((1, 0), 0),
        ((0, 1), 90),
        ((-1, 0), 180),
        ((0, -1), 270),
    ],
)
def test_cardinal_initial_bearings(
    destination: tuple[float, float],
    expected: float,
) -> None:
    assert initial_bearing_deg(0, 0, *destination) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("bearing", "expected"),
    [
        (0, "N"),
        (22.499999, "N"),
        (22.5, "NE"),
        (67.5, "E"),
        (112.5, "SE"),
        (157.5, "S"),
        (202.5, "SW"),
        (247.5, "W"),
        (292.5, "NW"),
        (337.5, "N"),
        (359.999999, "N"),
        (360, "N"),
    ],
)
def test_compass_direction_boundaries(bearing: float, expected: str) -> None:
    assert compass_direction(bearing) == expected


def test_asia_kolkata_date_window_is_converted_to_utc() -> None:
    validity = normalize_pfz_validity(
        date(2026, 8, 27),
        date(2026, 8, 27),
    )

    assert validity == (
        datetime(2026, 8, 26, 18, 30, tzinfo=UTC),
        datetime(2026, 8, 27, 18, 29, 59, 999999, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_nearest_selection_uses_all_valid_locations() -> None:
    farther = make_advisory(
        sector_code="SEC001",
        landing_centre="Farther",
        latitude=1,
        longitude=1,
    )
    nearer = make_advisory(
        sector_code="SEC002",
        region_name="Maharashtra",
        landing_centre="Nearest",
        latitude=0,
        longitude=0.1,
    )
    service, snapshot_service = make_nearest_service(
        make_snapshot([farther, nearer])
    )

    result = await service.get_nearest(latitude=0, longitude=0, at=QUERY_TIME)

    assert result.nearest_pfz.sector_code == "SEC002"
    assert result.nearest_pfz.landing_centre == "Nearest"
    assert result.nearest_pfz.distance_km == pytest.approx(11.12, abs=0.001)
    assert snapshot_service.calls == 1
    assert not hasattr(service, "client")


@pytest.mark.asyncio
async def test_equal_distance_uses_deterministic_sector_tie_break() -> None:
    second = make_advisory(
        sector_code="SEC002",
        landing_centre="Second",
        latitude=0,
        longitude=1,
    )
    first = make_advisory(
        sector_code="SEC001",
        landing_centre="First",
        latitude=0,
        longitude=1,
    )
    service, _ = make_nearest_service(make_snapshot([second, first]))

    result = await service.get_nearest(latitude=0, longitude=0, at=QUERY_TIME)

    assert result.nearest_pfz.sector_code == "SEC001"


@pytest.mark.asyncio
async def test_selection_uses_raw_distance_before_response_rounding() -> None:
    farther_but_lexically_first = make_advisory(
        sector_code="SEC001",
        landing_centre="Farther",
        latitude=0,
        longitude=1.000001,
    )
    nearer = make_advisory(
        sector_code="SEC002",
        landing_centre="Nearer",
        latitude=0,
        longitude=1.0,
    )
    service, _ = make_nearest_service(
        make_snapshot([farther_but_lexically_first, nearer])
    )

    result = await service.get_nearest(latitude=0, longitude=0, at=QUERY_TIME)

    assert result.nearest_pfz.sector_code == "SEC002"
    assert round(
        haversine_distance_km(0, 0, 0, 1.000001),
        3,
    ) == round(haversine_distance_km(0, 0, 0, 1.0), 3)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query_time",
    [
        datetime(2026, 8, 25, 12, tzinfo=UTC),
        datetime(2026, 8, 28, 12, tzinfo=UTC),
    ],
)
async def test_future_and_expired_advisories_are_excluded(
    query_time: datetime,
) -> None:
    service, _ = make_nearest_service(make_snapshot([make_advisory()]))

    with pytest.raises(NoValidPFZError):
        await service.get_nearest(latitude=0, longitude=0, at=query_time)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query_time",
    [
        datetime(2026, 8, 26, 18, 30, tzinfo=UTC),
        datetime(2026, 8, 27, 18, 29, 59, 999999, tzinfo=UTC),
    ],
)
async def test_validity_boundaries_are_inclusive(query_time: datetime) -> None:
    service, _ = make_nearest_service(make_snapshot([make_advisory()]))

    result = await service.get_nearest(latitude=0, longitude=0, at=query_time)

    assert result.nearest_pfz.sector_code == "SEC001"


@pytest.mark.asyncio
async def test_omitted_time_uses_injected_timezone_aware_utc_now() -> None:
    service, _ = make_nearest_service(
        make_snapshot([make_advisory()]),
        now=QUERY_TIME,
    )

    result = await service.get_nearest(latitude=0, longitude=0)

    assert result.query.at == QUERY_TIME


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cache_status",
    [PFZCacheStatus.FRESH, PFZCacheStatus.REFRESHED, PFZCacheStatus.STALE],
)
async def test_cache_status_is_propagated(cache_status: PFZCacheStatus) -> None:
    service, _ = make_nearest_service(
        make_snapshot([make_advisory()], cache_status=cache_status)
    )

    result = await service.get_nearest(latitude=0, longitude=0, at=QUERY_TIME)

    assert result.cache_status == cache_status


@pytest.mark.asyncio
async def test_partial_snapshot_failures_and_warnings_are_preserved() -> None:
    service, _ = make_nearest_service(
        make_snapshot([make_advisory()], partial=True)
    )

    result = await service.get_nearest(latitude=0, longitude=0, at=QUERY_TIME)

    assert result.completeness == "partial"
    assert result.failed_sectors[0].discovered_sector.sector_code == "SEC099"
    assert "SEC099 unavailable" in result.warnings
    assert any("partial snapshot" in warning for warning in result.warnings)


@pytest.mark.asyncio
async def test_unusable_validity_is_excluded_with_warning() -> None:
    unusable = make_advisory(
        sector_code="SEC001",
        landing_centre="Invalid validity",
        latitude=0,
        longitude=0.01,
    ).model_copy(update={"valid_until": None})
    valid = make_advisory(
        sector_code="SEC002",
        landing_centre="Valid",
        latitude=0,
        longitude=1,
    )
    snapshot = make_snapshot([valid])
    unusable_discovery = DiscoveredPFZSector(
        sector_code="SEC001",
        display_label="Legacy invalid advisory",
    )
    unusable_success = SuccessfulPFZSector.model_construct(
        discovered_sector=unusable_discovery,
        advisory=unusable,
    )
    snapshot = snapshot.model_copy(
        update={
            "discovered_sector_count": 2,
            "successful_sector_count": 2,
            "discovered_sectors": [
                unusable_discovery,
                *snapshot.discovered_sectors,
            ],
            "successful_sectors": [
                unusable_success,
                *snapshot.successful_sectors,
            ],
            "total_location_count": 2,
        }
    )
    service, _ = make_nearest_service(snapshot)

    result = await service.get_nearest(latitude=0, longitude=0, at=QUERY_TIME)

    assert result.nearest_pfz.sector_code == "SEC002"
    assert any("SEC001: excluded advisory" in item for item in result.warnings)


@pytest.mark.asyncio
async def test_stale_snapshot_must_still_be_valid() -> None:
    service, _ = make_nearest_service(
        make_snapshot(
            [make_advisory()],
            cache_status=PFZCacheStatus.STALE,
        )
    )

    with pytest.raises(NoValidPFZError):
        await service.get_nearest(
            latitude=0,
            longitude=0,
            at=datetime(2026, 8, 28, 12, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_stale_snapshot_warning_is_preserved() -> None:
    snapshot = make_snapshot(
        [make_advisory()],
        cache_status=PFZCacheStatus.STALE,
    ).model_copy(update={"warnings": ["Using stale PFZ snapshot"]})
    service, _ = make_nearest_service(snapshot)

    result = await service.get_nearest(latitude=0, longitude=0, at=QUERY_TIME)

    assert result.cache_status == "stale"
    assert result.warnings == ["Using stale PFZ snapshot"]


@pytest.mark.asyncio
async def test_geojson_coordinates_are_longitude_then_latitude() -> None:
    advisory = make_advisory(latitude=22.7167, longitude=68.95)
    service, _ = make_nearest_service(make_snapshot([advisory]))

    result = await service.get_nearest(latitude=21.6417, longitude=69.6293)

    assert result.geojson.geometry.coordinates == (68.95, 22.7167)
