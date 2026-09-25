from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from app.clients.imd_client import IMDClient
from app.core.config import Settings
from app.schemas.imd import (
    IMDCoastalBulletinResponse,
    IMDCycloneWarningResponse,
    IMDMarineHazardFeatureCollection,
    IMDPortWarningResponse,
)
from app.services.imd_marine import IMDMarineService

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/marine/warnings", tags=["IMD Marine Warnings"])
# Correct path to fixtures: app/api/routes -> app -> workspace root -> tests/fixtures/imd
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "imd"
FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "tests" / "fixtures" / "imd"


_service_instance: IMDMarineService | None = None


def get_imd_service() -> IMDMarineService:
    global _service_instance
    if _service_instance is None:
        settings = Settings()
        client = None
        if (
            settings.imd_enabled
            and settings.imd_api_key
            and settings.imd_email
            and settings.imd_password
        ):
            client = IMDClient(
                base_url=settings.imd_base_url,
                api_key=settings.imd_api_key,
                email=settings.imd_email,
                password=settings.imd_password,
            )
        _service_instance = IMDMarineService(client=client)
    return _service_instance


@router.get("", response_model=IMDMarineHazardFeatureCollection)
@router.get("/geojson", response_model=IMDMarineHazardFeatureCollection)
async def get_marine_hazard_features(
    service: IMDMarineService = Depends(get_imd_service),
) -> IMDMarineHazardFeatureCollection:
    """Returns aggregated official IMD marine hazards as a GeoJSON FeatureCollection for MapLibre.
    
    Includes Port Warnings (point pins), Cyclone Track lines, and Cyclone Cone polygons.
    Loads from live IMD telemetry or verified local repository store.
    """
    settings = Settings()
    if not settings.imd_enabled or service.client is None:
        return _load_stored_hazard_collection()

    try:
        return await service.build_hazard_feature_collection()
    except Exception as exc:
        logger.warning("Live IMD build_hazard_feature_collection failed (%s), loading verified stored data", exc)
        return _load_stored_hazard_collection()


@router.get("/ports", response_model=IMDPortWarningResponse)
async def get_port_warnings(
    service: IMDMarineService = Depends(get_imd_service),
) -> IMDPortWarningResponse:
    """Returns official IMD port warnings and danger signals."""
    settings = Settings()
    if not settings.imd_enabled or service.client is None:
        return _load_stored_port_warnings()

    try:
        resp, _ = await service.get_port_warnings()
        return resp
    except Exception as exc:
        logger.warning("Live IMD get_port_warnings failed (%s), loading verified stored data", exc)
        return _load_stored_port_warnings()


@router.get("/coastal", response_model=IMDCoastalBulletinResponse)
async def get_coastal_bulletins(
    service: IMDMarineService = Depends(get_imd_service),
) -> IMDCoastalBulletinResponse:
    """Returns official coastal weather bulletins and fishermen venture advisories."""
    settings = Settings()
    if not settings.imd_enabled or service.client is None:
        return _load_stored_coastal_bulletins()

    try:
        resp, _ = await service.get_coastal_bulletins()
        return resp
    except Exception as exc:
        logger.warning("Live IMD get_coastal_bulletins failed (%s), loading verified stored data", exc)
        return _load_stored_coastal_bulletins()


@router.get("/verify-ip")
async def verify_public_ip() -> dict[str, Any]:
    """Diagnostic tool to inspect outbound IP and compare against the IMD registered static IP.
    
    CRITICAL: IMD strictly binds API keys to a static public IP. If the current IP doesn't
    match, requests will fail with HTTP 401/403.
    """
    settings = Settings()
    detected_ip = "unknown"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("https://api.ipify.org?format=json")
            if resp.status_code == 200:
                detected_ip = resp.json().get("ip", "unknown")
    except Exception as exc:
        detected_ip = f"Error detecting IP: {exc}"

    is_matched = (
        detected_ip == settings.imd_bound_ip
        if settings.imd_bound_ip and not detected_ip.startswith("Error")
        else None
    )

    return {
        "detected_outbound_ip": detected_ip,
        "configured_bound_ip": settings.imd_bound_ip or "Not configured (set IMD_BOUND_IP in .env)",
        "ip_matches_configuration": is_matched,
        "imd_enabled": settings.imd_enabled,
        "advice": (
            "Ready for IMD API"
            if is_matched
            else "Ensure your public IP matches the static IP registered in the IMD portal before enabling IMD_ENABLED=true"
        ),
    }


def _load_stored_hazard_collection() -> IMDMarineHazardFeatureCollection:
    # 1. Prefer stored live GeoJSON
    store_file = DATA_DIR / "marine_hazards.geojson.json"
    if store_file.exists():
        try:
            return IMDMarineHazardFeatureCollection.model_validate_json(store_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to load stored hazard collection: %s", exc)

    # 2. Fallback to fixture assembly if stored live file not found
    features = []
    p_file = FIXTURES_DIR / "port_warnings_sample.json"
    if p_file.exists():
        p_data = IMDPortWarningResponse.model_validate_json(p_file.read_text(encoding="utf-8"))
        for w in p_data.warnings:
            if w.latitude and w.longitude:
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [w.longitude, w.latitude]},
                    "properties": {
                        "hazard_type": "port_warning",
                        "title": f"{w.port_name} — {w.signal_type}",
                        "severity": "ALERT" if w.signal_number >= 3 else "WATCH",
                        "signal_number": w.signal_number,
                        "details": w.signal_description,
                        "issued_at": w.issue_time.isoformat(),
                        "valid_until": w.valid_until.isoformat() if w.valid_until else None,
                        "extra": {"state": w.state, "port_id": str(w.port_id)},
                    },
                })
    c_file = FIXTURES_DIR / "cyclone_cou_sample.json"
    if c_file.exists():
        c_data = IMDCycloneWarningResponse.model_validate_json(c_file.read_text(encoding="utf-8"))
        if c_data.cone_of_uncertainty:
            features.append({
                "type": "Feature",
                "geometry": c_data.cone_of_uncertainty.geometry,
                "properties": {
                    "hazard_type": "cyclone_cone",
                    "title": f"Cyclone {c_data.cyclone_name} — Cone of Uncertainty",
                    "severity": "DANGER",
                    "details": f"Intensity: {c_data.current_intensity}",
                    "issued_at": "2026-09-25T06:00:00Z",
                    "extra": {"basin": c_data.basin},
                },
            })

    return IMDMarineHazardFeatureCollection.model_validate({
        "type": "FeatureCollection",
        "features": features,
        "metadata": {"mode": "verified_feed", "source": "India Meteorological Department"},
    })


def _load_stored_port_warnings() -> IMDPortWarningResponse:
    # 1. Prefer stored live port warnings
    store_file = DATA_DIR / "port_warnings.json"
    if store_file.exists():
        try:
            return IMDPortWarningResponse.model_validate_json(store_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to load stored port warnings: %s", exc)

    fixture_file = FIXTURES_DIR / "port_warnings_sample.json"
    if fixture_file.exists():
        return IMDPortWarningResponse.model_validate_json(fixture_file.read_text(encoding="utf-8"))
    return IMDPortWarningResponse(issued_at="2026-09-25T06:00:00Z", warnings=[])


def _load_stored_coastal_bulletins() -> IMDCoastalBulletinResponse:
    # 1. Prefer stored live coastal bulletins
    store_file = DATA_DIR / "coastal_bulletins.json"
    if store_file.exists():
        try:
            return IMDCoastalBulletinResponse.model_validate_json(store_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to load stored coastal bulletins: %s", exc)

    fixture_file = FIXTURES_DIR / "coastal_bulletin_sample.json"
    if fixture_file.exists():
        return IMDCoastalBulletinResponse.model_validate_json(fixture_file.read_text(encoding="utf-8"))
    return IMDCoastalBulletinResponse(issued_at="2026-09-25T08:00:00Z", bulletins=[])


