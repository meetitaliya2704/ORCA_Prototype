from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import logging
from typing import Any

from app.clients.imd_client import IMDClient, IMDClientError
from app.schemas.imd import (
    HazardFeatureProperties,
    HazardGeoJSONFeature,
    IMDCoastalBulletinItem,
    IMDCoastalBulletinResponse,
    IMDCycloneWarningResponse,
    IMDMarineHazardFeatureCollection,
    IMDPortWarningItem,
    IMDPortWarningResponse,
    IMDWarnSeverity,
)


logger = logging.getLogger(__name__)


class CachedEntry:
    def __init__(self, data: Any, ttl_seconds: int) -> None:
        self.data = data
        self.created_at = datetime.now(UTC)
        self.expires_at = self.created_at + timedelta(seconds=ttl_seconds)

    @property
    def is_expired(self) -> bool:
        return datetime.now(UTC) > self.expires_at


class IMDMarineService:
    """Service coordinating official IMD marine observations, bulletins, and GeoJSON hazard layers.
    
    Implements cache-aside architecture with stale-fallback support.
    """

    def __init__(
        self,
        client: IMDClient | None = None,
        bulletin_ttl_seconds: int = 1800,  # 30 minutes
        cyclone_ttl_seconds: int = 900,    # 15 minutes
        port_ttl_seconds: int = 1800,      # 30 minutes
    ) -> None:
        self.client = client
        self.bulletin_ttl_seconds = bulletin_ttl_seconds
        self.cyclone_ttl_seconds = cyclone_ttl_seconds
        self.port_ttl_seconds = port_ttl_seconds

        self._port_cache: CachedEntry | None = None
        self._bulletin_cache: CachedEntry | None = None
        self._cyclone_cache: CachedEntry | None = None

    async def get_port_warnings(self) -> tuple[IMDPortWarningResponse, str]:
        """Return (response, cache_status) where cache_status is 'fresh', 'refreshed', or 'stale'."""
        if self._port_cache and not self._port_cache.is_expired:
            return self._port_cache.data, "fresh"

        if not self.client:
            if self._port_cache:
                return self._port_cache.data, "stale"
            raise RuntimeError("IMD client not configured and no cached port warnings available")

        try:
            raw = await self.client.get_port_warnings()
            normalized = self._normalize_port_warnings(raw)
            self._port_cache = CachedEntry(normalized, self.port_ttl_seconds)
            return normalized, "refreshed"
        except Exception as exc:
            logger.warning("Failed to refresh IMD port warnings: %s", exc)
            if self._port_cache:
                return self._port_cache.data, "stale"
            raise

    def _normalize_port_warnings(self, raw: Any) -> IMDPortWarningResponse:
        # If already formatted as IMDPortWarningResponse dict
        if isinstance(raw, dict) and "warnings" in raw:
            return IMDPortWarningResponse.model_validate(raw)

        # Handle live IMD array: [{"Port Name": "...", "Signal": "LC3", "Latitude": "...", ...}]
        items: list[IMDPortWarningItem] = []
        raw_list = raw if isinstance(raw, list) else raw.get("data", []) if isinstance(raw, dict) else []

        for entry in raw_list:
            if not isinstance(entry, dict):
                continue
            port_name = entry.get("Port Name") or entry.get("port_name", "Unknown Port")
            port_id = entry.get("ID") or entry.get("id") or port_name
            state = entry.get("State") or entry.get("Issued By") or ""
            
            lat_str = entry.get("Latitude")
            lon_str = entry.get("Longitude")
            try:
                lat = float(lat_str) if lat_str is not None else None
                lon = float(lon_str) if lon_str is not None else None
            except (ValueError, TypeError):
                lat, lon = None, None

            signal_str = str(entry.get("Signal") or entry.get("signal") or "No Warning").strip()
            # Extract number e.g. "LC3" -> 3, "DS5" -> 5, "GDS10" -> 10, "No Warning" -> 0
            digits = "".join(filter(str.isdigit, signal_str))
            sig_num = int(digits) if digits else 0

            date_str = entry.get("Date of Issue") or entry.get("date_of_issue")
            time_str = entry.get("Time of Issue") or entry.get("time_of_issue")
            try:
                if date_str and time_str:
                    issue_dt = datetime.fromisoformat(f"{date_str}T{time_str}").replace(tzinfo=UTC)
                elif date_str:
                    issue_dt = datetime.fromisoformat(date_str).replace(tzinfo=UTC)
                else:
                    issue_dt = datetime.now(UTC)
            except Exception:
                issue_dt = datetime.now(UTC)

            warning_desc = str(entry.get("Warning") or "").strip()

            items.append(
                IMDPortWarningItem(
                    port_id=port_id,
                    port_name=port_name,
                    state=state,
                    latitude=lat,
                    longitude=lon,
                    signal_number=sig_num,
                    signal_type=signal_str,
                    signal_description=warning_desc if warning_desc != "NIL" else "",
                    issue_time=issue_dt,
                )
            )

        return IMDPortWarningResponse(
            status="success",
            issued_at=datetime.now(UTC),
            warnings=items,
        )

    async def get_coastal_bulletins(self) -> tuple[IMDCoastalBulletinResponse, str]:
        """Return (response, cache_status) for coastal & fishermen bulletins."""
        if self._bulletin_cache and not self._bulletin_cache.is_expired:
            return self._bulletin_cache.data, "fresh"

        if not self.client:
            if self._bulletin_cache:
                return self._bulletin_cache.data, "stale"
            raise RuntimeError("IMD client not configured and no cached bulletins available")

        try:
            raw = await self.client.get_coastal_bulletin()
            normalized = self._normalize_coastal_bulletin(raw)
            self._bulletin_cache = CachedEntry(normalized, self.bulletin_ttl_seconds)
            return normalized, "refreshed"
        except Exception as exc:
            logger.warning("Failed to refresh IMD coastal bulletin: %s", exc)
            if self._bulletin_cache:
                return self._bulletin_cache.data, "stale"
            raise

    def _normalize_coastal_bulletin(self, raw: Any) -> IMDCoastalBulletinResponse:
        if isinstance(raw, dict) and "bulletins" in raw:
            return IMDCoastalBulletinResponse.model_validate(raw)

        items: list[IMDCoastalBulletinItem] = []
        raw_list = raw if isinstance(raw, list) else raw.get("data", []) if isinstance(raw, dict) else []

        now = datetime.now(UTC)
        for entry in raw_list:
            if not isinstance(entry, dict):
                continue
            
            # IMD keys: "Layer" (e.g. "North Tamilnadu coast"), "Area", "Zone"
            zone = (
                entry.get("Layer")
                or entry.get("Area")
                or entry.get("Coast")
                or entry.get("Zone")
                or entry.get("coastal_zone")
                or "Indian Coastal Waters"
            )

            # IMD keys: "Synoptic Situation", "Weather", "Port Signal", "TTT Warning", "Warning"
            synoptic = entry.get("Synoptic Situation") or ""
            weather = entry.get("Weather") or ""
            port_sig = entry.get("Port Signal") or ""
            ttt = entry.get("TTT Warning") or ""
            advisory = (
                entry.get("Warning")
                or synoptic
                or weather
                or "Normal coastal conditions."
            )
            if port_sig and "NIL" not in port_sig:
                advisory = f"{advisory}\n{port_sig.strip()}"

            sea_cond = entry.get("Sea Condition") or entry.get("sea_condition") or "moderate"
            wind_str = entry.get("Wind") or ""

            # Check if fishermen should not venture
            is_warn = (
                "not to venture" in advisory.lower()
                or "rough" in str(sea_cond).lower()
                or "deep depression" in advisory.lower()
                or "lc-iii" in advisory.lower()
                or "lc3" in advisory.lower()
            )

            # Parse validity timestamps from IMD: "Valid From": "2026-09-22 22:00:00", "Validity": "12"
            valid_from_str = entry.get("Valid From") or entry.get("Date of Observation")
            validity_hours = 12
            try:
                if entry.get("Validity"):
                    validity_hours = int(entry.get("Validity"))
            except Exception:
                validity_hours = 12

            try:
                if valid_from_str:
                    v_from = datetime.fromisoformat(valid_from_str.strip().replace(" ", "T")).replace(tzinfo=UTC)
                else:
                    v_from = now
            except Exception:
                v_from = now

            v_to = v_from + timedelta(hours=validity_hours)

            items.append(
                IMDCoastalBulletinItem(
                    coastal_zone=zone,
                    wind_direction=wind_str if wind_str else None,
                    sea_condition=str(sea_cond).strip(),
                    fishermen_warning=is_warn,
                    advisory_text=advisory.strip(),
                    valid_from=v_from,
                    valid_to=v_to,
                )
            )

        return IMDCoastalBulletinResponse(
            status="success",
            issued_at=now,
            bulletins=items,
        )



    async def get_cyclone_warnings(self) -> tuple[IMDCycloneWarningResponse | None, str]:
        """Return (response, cache_status) for active cyclones."""
        if self._cyclone_cache and not self._cyclone_cache.is_expired:
            return self._cyclone_cache.data, "fresh"

        if not self.client:
            if self._cyclone_cache:
                return self._cyclone_cache.data, "stale"
            return None, "fresh"

        try:
            raw = await self.client.get_cyclone_cone()
            if not raw or raw.get("status") == "no_active_cyclone":
                self._cyclone_cache = CachedEntry(None, self.cyclone_ttl_seconds)
                return None, "refreshed"
            normalized = IMDCycloneWarningResponse.model_validate(raw)
            self._cyclone_cache = CachedEntry(normalized, self.cyclone_ttl_seconds)
            return normalized, "refreshed"
        except Exception as exc:
            logger.warning("Failed to refresh IMD cyclone warnings: %s", exc)
            if self._cyclone_cache:
                return self._cyclone_cache.data, "stale"
            return None, "stale"

    async def build_hazard_feature_collection(self) -> IMDMarineHazardFeatureCollection:
        """Aggregate active warnings into a unified MapLibre GeoJSON FeatureCollection."""
        features: list[HazardGeoJSONFeature] = []

        # 1. Port Warnings
        try:
            port_resp, _ = await self.get_port_warnings()
            for w in port_resp.warnings:
                if w.latitude is not None and w.longitude is not None and w.signal_number > 0:
                    sev = (
                        IMDWarnSeverity.DANGER if w.signal_number >= 8
                        else IMDWarnSeverity.WARNING if w.signal_number >= 4
                        else IMDWarnSeverity.ALERT if w.signal_number >= 3
                        else IMDWarnSeverity.WATCH
                    )
                    features.append(
                        HazardGeoJSONFeature(
                            type="Feature",
                            geometry={"type": "Point", "coordinates": [w.longitude, w.latitude]},
                            properties=HazardFeatureProperties(
                                hazard_type="port_warning",
                                title=f"{w.port_name} — {w.signal_type}",
                                severity=sev,
                                signal_number=w.signal_number,
                                details=w.signal_description or f"Signal {w.signal_number} hoisted.",
                                issued_at=w.issue_time,
                                valid_until=w.valid_until,
                                extra={"port_id": str(w.port_id), "state": w.state},
                            ),
                        )
                    )
        except Exception as exc:
            logger.debug("Port warnings skipped in hazard map: %s", exc)

        # 2. Cyclone Cones and Tracks
        try:
            cyclone_resp, _ = await self.get_cyclone_warnings()
            if cyclone_resp and cyclone_resp.cone_of_uncertainty:
                features.append(
                    HazardGeoJSONFeature(
                        type="Feature",
                        geometry=cyclone_resp.cone_of_uncertainty.geometry,
                        properties=HazardFeatureProperties(
                            hazard_type="cyclone_cone",
                            title=f"Cyclone {cyclone_resp.cyclone_name} — Cone of Uncertainty",
                            severity=IMDWarnSeverity.DANGER,
                            details=f"Current intensity: {cyclone_resp.current_intensity}",
                            issued_at=datetime.now(UTC),
                            extra={"basin": cyclone_resp.basin},
                        ),
                    )
                )
            if cyclone_resp and cyclone_resp.forecast_track:
                coords = [[pt.longitude, pt.latitude] for pt in cyclone_resp.forecast_track]
                if len(coords) >= 2:
                    features.append(
                        HazardGeoJSONFeature(
                            type="Feature",
                            geometry={"type": "LineString", "coordinates": coords},
                            properties=HazardFeatureProperties(
                                hazard_type="cyclone_track",
                                title=f"Cyclone {cyclone_resp.cyclone_name} — Forecast Track",
                                severity=IMDWarnSeverity.WARNING,
                                details=f"Track forecast across {len(coords)} waypoints",
                                issued_at=datetime.now(UTC),
                            ),
                        )
                    )
        except Exception as exc:
            logger.debug("Cyclone hazard skipped in hazard map: %s", exc)

        return IMDMarineHazardFeatureCollection(
            type="FeatureCollection",
            features=features,
            metadata={"generated_at": datetime.now(UTC).isoformat(), "source": "India Meteorological Department"},
        )

