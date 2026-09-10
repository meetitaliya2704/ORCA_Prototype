from __future__ import annotations

import math

EARTH_MEAN_RADIUS_KM = 6371.0088

COASTAL_REFERENCE_POINTS: list[tuple[str, float, float]] = [
    ("Koteshwar (Kutch)", 23.69, 68.53),
    ("Dwarka", 22.24, 68.96),
    ("Porbandar", 21.64, 69.60),
    ("Veraval", 20.90, 70.36),
    ("Diu", 20.71, 70.98),
    ("Jafarabad", 20.87, 71.37),
    ("Alang", 21.41, 72.20),
    ("Dahej", 21.70, 72.53),
    ("Hazira", 21.10, 72.65),
    ("Daman", 20.40, 72.83),
    ("Mumbai", 18.90, 72.81),
    ("Alibaug", 18.64, 72.87),
    ("Ratnagiri", 16.98, 73.28),
    ("Malvan", 16.06, 73.46),
    ("Panaji", 15.50, 73.83),
    ("Karwar", 14.81, 74.13),
    ("Bhatkal", 13.97, 74.55),
    ("Malpe", 13.35, 74.70),
    ("Mangalore", 12.87, 74.84),
    ("Kannur", 11.87, 75.37),
    ("Kozhikode", 11.25, 75.77),
    ("Kochi", 9.93, 76.26),
    ("Alappuzha", 9.49, 76.32),
    ("Kollam", 8.88, 76.59),
    ("Vizhinjam", 8.38, 76.99),
    ("Kanyakumari", 8.08, 77.55),
    ("Tuticorin", 8.80, 78.16),
    ("Rameswaram", 9.28, 79.31),
    ("Nagapattinam", 10.76, 79.84),
    ("Puducherry", 11.93, 79.83),
    ("Chennai", 13.08, 80.28),
    ("Krishnapatnam", 14.25, 80.12),
    ("Machilipatnam", 16.18, 81.14),
    ("Kakinada", 16.96, 82.25),
    ("Visakhapatnam", 17.68, 83.21),
    ("Gopalpur", 19.26, 84.90),
    ("Puri", 19.80, 85.82),
    ("Paradeep", 20.31, 86.61),
    ("Dhamra", 20.80, 86.95),
    ("Digha", 21.62, 87.51),
    ("Sagar Island", 21.65, 88.08),
    # Island territories
    ("Port Blair (Andaman)", 11.62, 92.73),
    ("Car Nicobar", 9.15, 92.78),
    ("Kavaratti (Lakshadweep)", 10.57, 72.64),
    ("Agatti (Lakshadweep)", 10.85, 72.19),
    ("Minicoy (Lakshadweep)", 8.28, 73.05),
]

WEST_COAST_PROFILE: list[tuple[float, float]] = [
    (8.08, 77.55),
    (8.5, 76.9),
    (9.0, 76.5),
    (10.0, 76.2),
    (11.0, 75.8),
    (12.0, 75.1),
    (13.0, 74.8),
    (14.0, 74.5),
    (15.0, 73.9),
    (16.0, 73.4),
    (17.0, 73.2),
    (18.0, 73.0),
    (19.0, 72.8),
    (20.0, 72.7),
    (20.8, 72.8),
]

EAST_COAST_PROFILE: list[tuple[float, float]] = [
    (8.08, 77.55),
    (8.8, 78.1),
    (9.5, 78.9),
    (10.5, 79.8),
    (11.5, 79.8),
    (12.5, 80.0),
    (13.0, 80.3),
    (14.0, 80.1),
    (15.0, 80.0),
    (16.0, 81.1),
    (17.0, 82.3),
    (18.0, 83.4),
    (19.0, 84.7),
    (20.0, 86.6),
    (21.0, 87.0),
    (21.8, 87.8),
    (22.2, 88.5),
]


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r_lat1, r_lon1, r_lat2, r_lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = r_lat2 - r_lat1
    dlon = r_lon2 - r_lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(r_lat1) * math.cos(r_lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_MEAN_RADIUS_KM * math.asin(math.sqrt(max(0.0, min(1.0, a))))


def _interpolate_lon(lat: float, profile: list[tuple[float, float]]) -> float:
    if lat <= profile[0][0]:
        return profile[0][1]
    if lat >= profile[-1][0]:
        return profile[-1][1]
    for i in range(len(profile) - 1):
        lat1, lon1 = profile[i]
        lat2, lon2 = profile[i + 1]
        if lat1 <= lat <= lat2:
            t = (lat - lat1) / (lat2 - lat1)
            return lon1 + t * (lon2 - lon1)
    return profile[-1][1]


def find_nearest_coast(latitude: float, longitude: float) -> tuple[str, float]:
    """Return the nearest coastal reference point name and distance in km."""
    best_dist = float("inf")
    best_name = "Indian Coast"
    for name, c_lat, c_lon in COASTAL_REFERENCE_POINTS:
        d = _haversine_km(latitude, longitude, c_lat, c_lon)
        if d < best_dist:
            best_dist = d
            best_name = name
    return best_name, best_dist


def is_land_coordinate(latitude: float, longitude: float) -> tuple[bool, str, float]:
    """Determine whether the coordinate is on land.

    Returns:
        (is_land, nearest_coast_name, distance_to_coast_km)
    """
    best_coast, dist_km = find_nearest_coast(latitude, longitude)

    # 1. Close to known coastal reference (within 25 km): coastal waters/harbour
    if dist_km <= 25.0:
        return False, best_coast, dist_km

    # 2. South of Kanyakumari (open Indian Ocean)
    if latitude < 8.0:
        return False, best_coast, dist_km

    # 3. North India / Continental interior (north of 24.5N)
    if latitude > 24.5:
        if longitude < 67.5:
            return False, best_coast, dist_km
        return True, best_coast, dist_km

    # 4. Gujarat / Kutch / Kathiawar region (20.0 <= latitude <= 24.5, 68.0 <= longitude <= 73.0)
    if 20.0 <= latitude <= 24.5 and 68.0 <= longitude <= 73.0:
        if latitude >= 22.3 and longitude >= 72.1:
            if dist_km > 30.0:
                return True, best_coast, dist_km
        if 21.0 <= latitude <= 22.4 and 70.0 <= longitude <= 71.8:
            if dist_km > 30.0:
                return True, best_coast, dist_km
        if 23.1 <= latitude <= 24.2 and 69.2 <= longitude <= 71.0:
            if dist_km > 30.0:
                return True, best_coast, dist_km
        if longitude > 73.0 and latitude > 21.0:
            return True, best_coast, dist_km
        return False, best_coast, dist_km

    # 5. Peninsular India (8.0 <= latitude <= 22.0)
    w_lon = _interpolate_lon(latitude, WEST_COAST_PROFILE)
    e_lon = _interpolate_lon(latitude, EAST_COAST_PROFILE)

    # Open Arabian Sea
    if longitude < w_lon - 0.25:
        return False, best_coast, dist_km

    # Open Bay of Bengal
    if longitude > e_lon + 0.25:
        return False, best_coast, dist_km

    # Between west and east coast inside mainland India
    if (w_lon + 0.15) <= longitude <= (e_lon - 0.15):
        return True, best_coast, dist_km

    # Coastal margin buffer
    if dist_km > 30.0:
        return True, best_coast, dist_km

    return False, best_coast, dist_km


def decimal_to_dms(val: float, is_lat: bool) -> str:
    """Format decimal degrees to human-readable DMS string (e.g. 20° 53' 24" N)."""
    direction = ("N" if val >= 0 else "S") if is_lat else ("E" if val >= 0 else "W")
    val_abs = abs(val)
    degrees = int(val_abs)
    minutes_float = (val_abs - degrees) * 60
    minutes = int(minutes_float)
    seconds = round((minutes_float - minutes) * 60)
    if seconds == 60:
        minutes += 1
        seconds = 0
    if minutes == 60:
        degrees += 1
        minutes = 0
    return f"{degrees:02d}° {minutes:02d}' {seconds:02d}\" {direction}"
