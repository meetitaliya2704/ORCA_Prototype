from datetime import UTC, date, datetime

from pydantic import BaseModel, Field, model_validator


class PFZLocation(BaseModel):
    landing_centre: str = Field(min_length=1)
    direction: str | None = None
    bearing_deg: float | None = Field(default=None, ge=0, le=360)
    distance_min_km: float | None = Field(default=None, ge=0)
    distance_max_km: float | None = Field(default=None, ge=0)
    depth_min_m: float | None = Field(default=None, ge=0)
    depth_max_m: float | None = Field(default=None, ge=0)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

    @model_validator(mode="after")
    def ranges_are_ordered(self) -> "PFZLocation":
        pairs = (
            (self.distance_min_km, self.distance_max_km, "distance"),
            (self.depth_min_m, self.depth_max_m, "depth"),
        )
        for minimum, maximum, label in pairs:
            if minimum is not None and maximum is not None and minimum > maximum:
                raise ValueError(f"{label} minimum cannot exceed maximum")
        return self


class PFZAdvisory(BaseModel):
    sector_code: str = Field(pattern=r"^SEC\d{3}$")
    region_name: str = Field(min_length=1)
    forecast_date: date
    valid_until: date
    satellite_message: str | None = None
    locations: list[PFZLocation] = Field(min_length=1)
    parse_warnings: list[str] = Field(default_factory=list)
    source: str = "INCOIS"
    source_url: str
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validity_is_consistent(self) -> "PFZAdvisory":
        if self.valid_until < self.forecast_date:
            raise ValueError("valid_until cannot be before forecast_date")
        return self

