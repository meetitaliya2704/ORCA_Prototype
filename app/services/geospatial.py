import math


EARTH_MEAN_RADIUS_KM = 6371.0088


def haversine_distance_km(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    """Return great-circle distance using the IUGG mean Earth radius."""
    lat_a = math.radians(latitude_a)
    lat_b = math.radians(latitude_b)
    delta_lat = lat_b - lat_a
    delta_lon = math.radians(longitude_b - longitude_a)

    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2) ** 2
    )
    central_angle = 2 * math.atan2(
        math.sqrt(haversine),
        math.sqrt(max(0.0, 1 - haversine)),
    )
    return EARTH_MEAN_RADIUS_KM * central_angle


def initial_bearing_deg(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    """Return the initial great-circle bearing normalized to [0, 360)."""
    lat_a = math.radians(latitude_a)
    lat_b = math.radians(latitude_b)
    delta_lon = math.radians(longitude_b - longitude_a)

    east_component = math.sin(delta_lon) * math.cos(lat_b)
    north_component = (
        math.cos(lat_a) * math.sin(lat_b)
        - math.sin(lat_a) * math.cos(lat_b) * math.cos(delta_lon)
    )
    return math.degrees(math.atan2(east_component, north_component)) % 360


def compass_direction(bearing_deg: float) -> str:
    """Map a bearing to eight clockwise, half-open compass sectors.

    Exact boundaries belong to the clockwise sector: 22.5 is NE, 67.5 is E,
    and so on. 337.5 maps to N. Input is normalized so 360 also maps to N.
    """
    directions = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
    normalized = bearing_deg % 360
    return directions[int((normalized + 22.5) // 45) % len(directions)]
