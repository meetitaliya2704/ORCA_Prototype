import re
from datetime import date, datetime
from urllib.parse import parse_qsl, urlsplit

from bs4 import BeautifulSoup, Tag

from app.schemas.pfz import DiscoveredPFZSector, PFZAdvisory, PFZLocation


TEXT_MONTH_DATE_PATTERN = re.compile(
    r"\b(\d{1,2})[\s./-]+"
    r"(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*"
    r"[\s,./-]+(\d{4})\b",
    re.IGNORECASE,
)
NUMERIC_DMY_DATE_PATTERN = re.compile(
    r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b"
)
ISO_DATE_PATTERN = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")


class PFZParseError(ValueError):
    """Raised when a page is not a usable INCOIS PFZ data page."""

    def __init__(self, message: str, *, stage: str = "pfz_parsing") -> None:
        super().__init__(message)
        self.stage = stage


class NoSectorsDiscoveredError(PFZParseError):
    """Raised when TextDataHome contains no usable sector options."""

    def __init__(self) -> None:
        super().__init__(
            "No valid PFZ sector options found",
            stage="sector_discovery",
        )


def normalize_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def is_valid_pfz_sector_html(html: str) -> bool:
    markers = pfz_marker_presence(html)
    return markers["has_forecastdata"] and markers["has_satmsg"]


def pfz_marker_presence(html: str) -> dict[str, bool]:
    soup = BeautifulSoup(html, "html.parser")
    return {
        "has_forecastdata": soup.select_one("#forecastdata") is not None,
        "has_satmsg": soup.select_one("#satmsg") is not None,
        "has_sectorname": soup.select_one("#sectorname") is not None,
    }


def parse_pfz_sector_options(home_html: str) -> list[DiscoveredPFZSector]:
    """Return unique live sector options in their source order."""
    soup = BeautifulSoup(home_html, "html.parser")
    sectors: list[DiscoveredPFZSector] = []
    seen: set[str] = set()

    for option in soup.select("option[value]"):
        raw_value = str(option.get("value", "")).strip()
        normalized_value = raw_value.upper()
        if re.fullmatch(r"SEC\d+", normalized_value) is not None:
            sector_code = normalized_value
        else:
            sector_code = ""
            for key, value in parse_qsl(urlsplit(raw_value).query):
                candidate = value.strip().upper()
                if key.lower() == "secid" and re.fullmatch(
                    r"SEC\d+", candidate
                ):
                    sector_code = candidate
                    break

        if not sector_code or sector_code in seen:
            continue

        seen.add(sector_code)
        sectors.append(
            DiscoveredPFZSector(
                sector_code=sector_code,
                display_label=normalize_text(option.get_text(" ", strip=True)),
            )
        )

    if not sectors:
        raise NoSectorsDiscoveredError()
    return sectors


def dms_to_decimal(value: str) -> float:
    direction_match = re.search(r"[NSEW]", value, re.IGNORECASE)
    direction = direction_match.group(0).upper() if direction_match else None
    numbers = [float(number) for number in re.findall(r"-?\d+(?:\.\d+)?", value)]

    if len(numbers) < 2:
        raise ValueError(f"Invalid DMS coordinate: {value!r}")

    degrees = numbers[0]
    minutes = numbers[1]
    seconds = numbers[2] if len(numbers) >= 3 else 0.0

    if not 0 <= minutes < 60 or not 0 <= seconds < 60:
        raise ValueError(f"Invalid DMS coordinate: {value!r}")

    decimal = abs(degrees) + minutes / 60 + seconds / 3600
    if degrees < 0 or direction in {"S", "W"}:
        decimal *= -1
    return round(decimal, 7)


def parse_range(value: str) -> tuple[float | None, float | None]:
    numbers = [float(number) for number in re.findall(r"\d+(?:\.\d+)?", value)]
    if not numbers:
        return None, None
    if len(numbers) == 1:
        return numbers[0], numbers[0]
    return min(numbers[0], numbers[1]), max(numbers[0], numbers[1])


def extract_dates(value: str) -> list[date]:
    """Extract supported INCOIS date formats in source order."""
    found: list[tuple[int, date]] = []

    for match in TEXT_MONTH_DATE_PATTERN.finditer(value):
        day, month_name, year = match.groups()
        month = datetime.strptime(month_name[:3].title(), "%b").month
        found.append((match.start(), date(int(year), month, int(day))))

    for match in NUMERIC_DMY_DATE_PATTERN.finditer(value):
        day, month, year = (int(part) for part in match.groups())
        found.append((match.start(), date(year, month, day)))

    for match in ISO_DATE_PATTERN.finditer(value):
        year, month, day = (int(part) for part in match.groups())
        found.append((match.start(), date(year, month, day)))

    unique_dates: list[date] = []
    for _, parsed in sorted(found, key=lambda item: item[0]):
        if parsed not in unique_dates:
            unique_dates.append(parsed)
    return unique_dates


def parse_date(value: str) -> date:
    dates = extract_dates(value)
    if not dates:
        raise PFZParseError(
            f"Date not found in: {value!r}",
            stage="date_parsing",
        )
    return dates[0]


def _find_labeled_date(soup: BeautifulSoup, label_pattern: str) -> date | None:
    label = soup.find(string=re.compile(label_pattern, re.IGNORECASE))
    if label is None:
        return None

    candidates: list[str] = []
    parent = label.parent
    if isinstance(parent, Tag):
        row = parent.find_parent("tr")
        if row is not None:
            candidates.append(row.get_text(" ", strip=True))

            label_cell = parent if parent.name in {"th", "td"} else parent.find_parent(
                ["th", "td"]
            )
            table = row.find_parent("table")
            if label_cell is not None and table is not None:
                header_cells = row.find_all(["th", "td"], recursive=False)
                try:
                    column_index = header_cells.index(label_cell)
                except ValueError:
                    column_index = -1

                if column_index >= 0:
                    later_row = row.find_next_sibling("tr")
                    while later_row is not None:
                        value_cells = later_row.find_all(
                            ["th", "td"], recursive=False
                        )
                        if column_index < len(value_cells):
                            candidates.append(
                                value_cells[column_index].get_text(" ", strip=True)
                            )
                        later_row = later_row.find_next_sibling("tr")
        candidates.append(parent.parent.get_text(" ", strip=True))

    for candidate in candidates:
        try:
            return parse_date(candidate)
        except PFZParseError:
            continue
    return None


def _extract_region_name(soup: BeautifulSoup) -> str:
    for selector in (
        "[data-region]",
        "#regionname",
        "#regionName",
        "#statename",
        "#stateName",
        "select#sector option[selected]",
        "select[name*=sector] option[selected]",
        "#sectorname"
    ):
        element = soup.select_one(selector)
        if element is not None:
            if element.has_attr("data-region"):
                value = str(element["data-region"])
            else:
                value = element.get_text(" ", strip=True)
            value = normalize_text(value)
            if value:
                return value

    heading = soup.find(
        ["h1", "h2", "h3", "h4"],
        string=re.compile(r"Gujarat|Maharashtra|Goa|Kerala|Tamil|Odisha|Bengal", re.I),
    )
    if heading is not None:
        return normalize_text(heading.get_text(" ", strip=True))

    raise PFZParseError(
        "Region name not found; mapping must not be guessed",
        stage="sector_name_parsing",
    )


def _header_index(headers: list[str], *keywords: str) -> int:
    for index, header in enumerate(headers):
        normalized = header.lower()
        if all(keyword in normalized for keyword in keywords):
            return index
    raise PFZParseError(
        f"PFZ table column not found: {' '.join(keywords)}",
        stage="pfz_location_parsing",
    )


def _find_pfz_table(soup: BeautifulSoup) -> tuple[Tag, list[str]]:
    for table in soup.find_all("table"):
        headers = [
            normalize_text(cell.get_text(" ", strip=True))
            for cell in table.find_all("th")
        ]
        joined = " ".join(headers).lower()
        if "latitude" in joined and "longitude" in joined and "bearing" in joined:
            return table, headers
    raise PFZParseError(
        "PFZ data table not found",
        stage="pfz_location_parsing",
    )


def _parse_locations(soup: BeautifulSoup) -> tuple[list[PFZLocation], list[str]]:
    table, headers = _find_pfz_table(soup)

    centre_index = _header_index(headers, "coast")
    direction_index = _header_index(headers, "direction")
    bearing_index = _header_index(headers, "bearing")
    distance_index = _header_index(headers, "distance")
    depth_index = _header_index(headers, "depth")
    latitude_index = _header_index(headers, "latitude")
    longitude_index = _header_index(headers, "longitude")
    required_max_index = max(
        centre_index,
        direction_index,
        bearing_index,
        distance_index,
        depth_index,
        latitude_index,
        longitude_index,
    )

    locations: list[PFZLocation] = []
    warnings: list[str] = []

    for row_number, row in enumerate(table.find_all("tr"), start=1):
        cells = [
            normalize_text(cell.get_text(" ", strip=True))
            for cell in row.find_all("td")
        ]
        if not cells:
            continue

        try:
            if len(cells) <= required_max_index:
                raise ValueError("not enough columns")

            distance_min, distance_max = parse_range(cells[distance_index])
            depth_min, depth_max = parse_range(cells[depth_index])
            bearing_values = re.findall(r"\d+(?:\.\d+)?", cells[bearing_index])

            locations.append(
                PFZLocation(
                    landing_centre=cells[centre_index],
                    direction=cells[direction_index] or None,
                    bearing_deg=(
                        float(bearing_values[0]) if bearing_values else None
                    ),
                    distance_min_km=distance_min,
                    distance_max_km=distance_max,
                    depth_min_m=depth_min,
                    depth_max_m=depth_max,
                    latitude=dms_to_decimal(cells[latitude_index]),
                    longitude=dms_to_decimal(cells[longitude_index]),
                )
            )
        except (ValueError, TypeError) as exc:
            warnings.append(f"Rejected table row {row_number}: {exc}")

    if not locations:
        raise PFZParseError(
            "PFZ table contained no valid locations",
            stage="pfz_location_parsing",
        )
    return locations, warnings


def parse_pfz_advisory(
    *,
    sector_html: str,
    home_html: str,
    sector_code: str,
    source_url: str,
) -> PFZAdvisory:
    if not is_valid_pfz_sector_html(sector_html):
        raise PFZParseError(
            "Missing #forecastdata or #satmsg page markers",
            stage="page_marker_validation",
        )

    sector_soup = BeautifulSoup(sector_html, "html.parser")
    home_soup = BeautifulSoup(home_html, "html.parser")
    satellite_element = sector_soup.select_one("#satmsg")
    assert satellite_element is not None
    satellite_message = normalize_text(
        satellite_element.get_text(" ", strip=True)
    )

    valid_until = _find_labeled_date(home_soup, r"Valid\s*(?:upto|until)")
    if valid_until is None:
        valid_until = parse_date(satellite_message)

    forecast_date = _find_labeled_date(home_soup, r"Forecast\s*Date")
    if forecast_date is None:
        forecast_date = _find_labeled_date(sector_soup, r"Forecast\s*Date")
    if forecast_date is None:
        # Some live INCOIS versions place the values in JavaScript, hidden
        # elements, or a table structure not connected to the visible label.
        # Search the raw home HTML, then choose the closest earlier date to the
        # independently parsed validity date. Never invent a missing date.
        page_dates = extract_dates(home_html)
        candidates = [value for value in page_dates if value < valid_until]
        if candidates:
            forecast_date = max(candidates)

    if forecast_date is None:
        detected = ", ".join(item.isoformat() for item in extract_dates(home_html))
        raise PFZParseError(
            "Forecast date not found"
            + (f"; detected home dates: {detected}" if detected else ""),
            stage="forecast_date_parsing",
        )

    locations, warnings = _parse_locations(sector_soup)
    try:
        return PFZAdvisory(
            sector_code=sector_code.upper(),
            region_name=_extract_region_name(sector_soup),
            forecast_date=forecast_date,
            valid_until=valid_until,
            satellite_message=satellite_message,
            locations=locations,
            parse_warnings=warnings,
            source_url=source_url,
        )
    except ValueError as exc:
        raise PFZParseError(
            f"Invalid normalized PFZ advisory: {exc}",
            stage="advisory_normalization",
        ) from exc
