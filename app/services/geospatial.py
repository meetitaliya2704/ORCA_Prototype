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


def point_in_polygon(lon: float, lat: float, ring: list[list[float]] | tuple) -> bool:
    """Ray-casting point-in-polygon test for a 2D ring of [lon, lat] coordinates."""
    inside = False
    n = len(ring)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _orientation(p: tuple[float, float], q: tuple[float, float], r: tuple[float, float]) -> int:
    """Return orientation: 0 -> collinear, 1 -> clockwise, 2 -> counterclockwise."""
    val = (q[1] - p[1]) * (r[0] - q[0]) - (q[0] - p[0]) * (r[1] - q[1])
    if abs(val) < 1e-12:
        return 0
    return 1 if val > 0 else 2


def _on_segment(p: tuple[float, float], q: tuple[float, float], r: tuple[float, float]) -> bool:
    """Check if point q lies on segment pr."""
    return (
        q[0] <= max(p[0], r[0]) + 1e-12
        and q[0] >= min(p[0], r[0]) - 1e-12
        and q[1] <= max(p[1], r[1]) + 1e-12
        and q[1] >= min(p[1], r[1]) - 1e-12
    )


def line_segment_intersects(
    p1: tuple[float, float],
    p2: tuple[float, float],
    q1: tuple[float, float],
    q2: tuple[float, float],
) -> bool:
    """Check if 2D line segment p1-p2 intersects segment q1-q2."""
    o1 = _orientation(p1, p2, q1)
    o2 = _orientation(p1, p2, q2)
    o3 = _orientation(q1, q2, p1)
    o4 = _orientation(q1, q2, p2)

    # General case
    if o1 != o2 and o3 != o4:
        return True

    # Special Cases (collinear and point lies on segment)
    if o1 == 0 and _on_segment(p1, q1, p2):
        return True
    if o2 == 0 and _on_segment(p1, q2, p2):
        return True
    if o3 == 0 and _on_segment(q1, p1, q2):
        return True
    if o4 == 0 and _on_segment(q1, p2, q2):
        return True

    return False


def line_intersects_polygon(
    line_points: list[tuple[float, float]] | tuple[tuple[float, float], ...],
    polygon_geometry: dict | list,
) -> bool:
    """Deterministic check whether a line (sequence of [lon, lat]) intersects a GeoJSON polygon.
    
    Supports GeoJSON geometry dict {"type": "Polygon"|"MultiPolygon", "coordinates": ...}
    or raw coordinates list.
    """
    if isinstance(polygon_geometry, dict):
        coords = polygon_geometry.get("coordinates", [])
        geom_type = polygon_geometry.get("type", "Polygon")
    else:
        coords = polygon_geometry
        geom_type = "MultiPolygon" if coords and isinstance(coords[0][0][0], (list, tuple)) else "Polygon"

    # Normalize to list of polygon exterior rings
    rings: list[list[list[float]]] = []
    if geom_type == "Polygon":
        if coords:
            rings.append(coords[0])
    elif geom_type == "MultiPolygon":
        for poly in coords:
            if poly:
                rings.append(poly[0])

    for ring in rings:
        if not ring or len(ring) < 3:
            continue
        # 1. Endpoint containment check
        for pt in line_points:
            if point_in_polygon(pt[0], pt[1], ring):
                return True

        # 2. Segment intersection check
        for i in range(len(line_points) - 1):
            lp1 = (line_points[i][0], line_points[i][1])
            lp2 = (line_points[i + 1][0], line_points[i + 1][1])
            n = len(ring)
            for j in range(n):
                rp1 = (ring[j][0], ring[j][1])
                rp2 = (ring[(j + 1) % n][0], ring[(j + 1) % n][1])
                if line_segment_intersects(lp1, lp2, rp1, rp2):
                    return True

    return False


def point_to_segment_distance_km(
    p_lon: float,
    p_lat: float,
    a_lon: float,
    a_lat: float,
    b_lon: float,
    b_lat: float,
) -> float:
    """Return the minimum great-circle distance (in km) from point P to line segment AB."""
    if abs(a_lon - b_lon) < 1e-9 and abs(a_lat - b_lat) < 1e-9:
        return haversine_distance_km(p_lat, p_lon, a_lat, a_lon)

    mid_lat_rad = math.radians((a_lat + b_lat) / 2.0)
    cos_mid = math.cos(mid_lat_rad)

    ax, ay = a_lon * cos_mid, a_lat
    bx, by = b_lon * cos_mid, b_lat
    px, py = p_lon * cos_mid, p_lat

    dx = bx - ax
    dy = by - ay
    seg_len_sq = dx * dx + dy * dy

    if seg_len_sq < 1e-18:
        return haversine_distance_km(p_lat, p_lon, a_lat, a_lon)

    t = ((px - ax) * dx + (py - ay) * dy) / seg_len_sq
    t = max(0.0, min(1.0, t))

    closest_lon = a_lon + t * (b_lon - a_lon)
    closest_lat = a_lat + t * (b_lat - a_lat)

    return haversine_distance_km(p_lat, p_lon, closest_lat, closest_lon)

