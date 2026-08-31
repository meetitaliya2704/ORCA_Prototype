import os
import subprocess
import sys
from pathlib import Path


def test_application_starts_without_database_or_redis_package(tmp_path: Path) -> None:
    script = r"""
import asyncio
import importlib.abc
import sys

class BlockOptionalPackages(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if (
            fullname == "redis"
            or fullname.startswith("redis.")
            or fullname == "copernicusmarine"
            or fullname.startswith("copernicusmarine.")
            or fullname == "ecmwf"
            or fullname.startswith("ecmwf.")
            or fullname == "eccodes"
            or fullname.startswith("eccodes.")
        ):
            raise ModuleNotFoundError(f"{fullname} intentionally unavailable")
        return None

sys.meta_path.insert(0, BlockOptionalPackages())

from app.main import app

async def verify_startup():
    async with app.router.lifespan_context(app):
        cache = app.state.marine_service.cache
        assert type(cache).__name__ == "MemoryJsonCache"
        assert "redis" not in sys.modules
        assert "copernicusmarine" not in sys.modules
        assert "ecmwf" not in sys.modules
        assert "eccodes" not in sys.modules

asyncio.run(verify_startup())
"""
    environment = os.environ.copy()
    environment.pop("DATABASE_URL", None)
    environment.pop("REDIS_URL", None)
    environment["REDIS_ENABLED"] = "false"

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_enabled_sst_missing_optional_package_is_controlled(tmp_path: Path) -> None:
    script = r"""
import importlib.abc
import sys

class BlockCopernicus(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "copernicusmarine" or fullname.startswith("copernicusmarine."):
            raise ModuleNotFoundError("copernicusmarine intentionally unavailable")
        return None

sys.meta_path.insert(0, BlockCopernicus())

from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as client:
    response = client.get(
        "/v1/marine/sst",
        params={
            "latitude": 18.025,
            "longitude": 70.525,
            "at": "2026-08-27T00:00:00Z",
        },
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "SST_SOURCE_NOT_CONFIGURED"
"""
    environment = os.environ.copy()
    environment["COPERNICUS_SST_ENABLED"] = "true"
    environment["REDIS_ENABLED"] = "false"
    environment.pop("COPERNICUSMARINE_SERVICE_USERNAME", None)
    environment.pop("COPERNICUSMARINE_SERVICE_PASSWORD", None)

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_enabled_waves_missing_optional_package_is_controlled(
    tmp_path: Path,
) -> None:
    script = r"""
import importlib.abc
import sys

class BlockCopernicus(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "copernicusmarine" or fullname.startswith("copernicusmarine."):
            raise ModuleNotFoundError("copernicusmarine intentionally unavailable")
        return None

sys.meta_path.insert(0, BlockCopernicus())

from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as client:
    response = client.get(
        "/v1/marine/waves",
        params={
            "latitude": 18.025,
            "longitude": 70.525,
            "at": "2026-08-28T00:00:00Z",
        },
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "WAVE_SOURCE_NOT_CONFIGURED"
"""
    environment = os.environ.copy()
    environment["COPERNICUS_SST_ENABLED"] = "false"
    environment["COPERNICUS_WAVES_ENABLED"] = "true"
    environment["REDIS_ENABLED"] = "false"
    environment.pop("COPERNICUSMARINE_SERVICE_USERNAME", None)
    environment.pop("COPERNICUSMARINE_SERVICE_PASSWORD", None)

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_enabled_wind_missing_optional_package_is_controlled(tmp_path: Path) -> None:
    script = r"""
import importlib.abc
import sys

class BlockCopernicus(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "copernicusmarine" or fullname.startswith("copernicusmarine."):
            raise ModuleNotFoundError("copernicusmarine intentionally unavailable")
        return None

sys.meta_path.insert(0, BlockCopernicus())

from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as client:
    response = client.get(
        "/v1/marine/wind",
        params={
            "latitude": 18.025,
            "longitude": 70.525,
            "at": "2026-08-28T23:00:00Z",
        },
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "WIND_SOURCE_NOT_CONFIGURED"
"""
    environment = os.environ.copy()
    environment["COPERNICUS_SST_ENABLED"] = "false"
    environment["COPERNICUS_WAVES_ENABLED"] = "false"
    environment["COPERNICUS_WIND_ENABLED"] = "true"
    environment["REDIS_ENABLED"] = "false"
    environment.pop("COPERNICUSMARINE_SERVICE_USERNAME", None)
    environment.pop("COPERNICUSMARINE_SERVICE_PASSWORD", None)

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_enabled_ecmwf_missing_optional_packages_is_controlled(
    tmp_path: Path,
) -> None:
    script = r"""
import importlib.abc
import sys

class BlockECMWF(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if (
            fullname == "ecmwf"
            or fullname.startswith("ecmwf.")
            or fullname == "eccodes"
            or fullname.startswith("eccodes.")
        ):
            raise ModuleNotFoundError(f"{fullname} intentionally unavailable")
        return None

sys.meta_path.insert(0, BlockECMWF())

from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as client:
    assert "ecmwf" not in sys.modules
    assert "eccodes" not in sys.modules
    response = client.get(
        "/v1/marine/wind/forecast",
        params={
            "latitude": 18.025,
            "longitude": 70.525,
            "at": "2026-08-31T00:00:00Z",
        },
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "ECMWF_DEPENDENCY_MISSING"
"""
    environment = os.environ.copy()
    environment["COPERNICUS_SST_ENABLED"] = "false"
    environment["COPERNICUS_WAVES_ENABLED"] = "false"
    environment["COPERNICUS_WIND_ENABLED"] = "false"
    environment["ECMWF_WIND_ENABLED"] = "true"
    environment["REDIS_ENABLED"] = "false"

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
