from typing import Annotated

from fastapi import Query


LatitudeQuery = Annotated[
    float,
    Query(
        ge=-90.0,
        le=90.0,
        description="Latitude in decimal degrees",
        json_schema_extra={"format": "double"},
    ),
]

LongitudeQuery = Annotated[
    float,
    Query(
        ge=-180.0,
        le=180.0,
        description="Longitude in decimal degrees",
        json_schema_extra={"format": "double"},
    ),
]
