from pathlib import Path

import pytest

from app.parsers.pfz_html import (
    PFZParseError,
    dms_to_decimal,
    parse_date,
    parse_pfz_advisory,
)


FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_dms_to_decimal() -> None:
    assert dms_to_decimal("22 43 00 N") == pytest.approx(22.7166667)
    assert dms_to_decimal("68° 57' 00\" E") == pytest.approx(68.95)
    assert dms_to_decimal("10 30 00 S") == pytest.approx(-10.5)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("27 AUG 2026", "2026-08-27"),
        ("27-Aug-2026", "2026-08-27"),
        ("27/08/2026", "2026-08-27"),
        ("2026-08-27", "2026-08-27"),
    ],
)
def test_parse_supported_date_formats(source: str, expected: str) -> None:
    assert parse_date(source).isoformat() == expected


def test_parse_valid_pfz_advisory_and_reject_bad_row() -> None:
    advisory = parse_pfz_advisory(
        home_html=load_fixture("incois_home.html"),
        sector_html=load_fixture("incois_sec001.html"),
        sector_code="SEC001",
        source_url="https://incois.test/TextData?secid=SEC001",
    )

    assert advisory.region_name == "Gujarat"
    assert advisory.forecast_date.isoformat() == "2026-08-27"
    assert advisory.valid_until.isoformat() == "2026-08-28"
    assert len(advisory.locations) == 1
    assert advisory.locations[0].landing_centre == "Lakhi Bandar"
    assert advisory.locations[0].distance_max_km == 127
    assert advisory.locations[0].latitude == pytest.approx(22.7166667)
    assert len(advisory.parse_warnings) == 1


def test_invalid_session_page_is_rejected() -> None:
    with pytest.raises(PFZParseError, match="page markers"):
        parse_pfz_advisory(
            home_html=load_fixture("incois_home.html"),
            sector_html=load_fixture("invalid_session.html"),
            sector_code="SEC001",
            source_url="https://incois.test/MarineFisheryAdvisory",
        )


def test_parse_forecast_date_from_raw_live_page_variant() -> None:
    advisory = parse_pfz_advisory(
        home_html=load_fixture("incois_home_live_variant.html"),
        sector_html=load_fixture("incois_sec001.html"),
        sector_code="SEC001",
        source_url="https://incois.test/TextData?secid=SEC001",
    )

    assert advisory.forecast_date.isoformat() == "2026-08-27"
    assert advisory.valid_until.isoformat() == "2026-08-28"


def test_parse_region_name_from_sectorname_variant() -> None:
    advisory = parse_pfz_advisory(
        home_html=load_fixture("incois_home.html"),
        sector_html=load_fixture("incois_sectorname_variant.html"),
        sector_code="SEC003",
        source_url="https://incois.test/TextData?secid=SEC003",
    )

    assert advisory.region_name == "Odisha"
    assert advisory.locations[0].landing_centre == "Paradip"
