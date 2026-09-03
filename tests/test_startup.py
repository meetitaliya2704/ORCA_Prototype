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
        chlorophyll = next(
            source
            for source in app.state.marine_service.sources
            if source.name == "chlorophyll"
        )
        assert type(chlorophyll).__name__ == "DemoMarineSource"
        assert chlorophyll.variable == "CHLOROPHYLL_A"
        sea_level = next(
            source
            for source in app.state.marine_service.sources
            if source.name == "sea_level"
        )
        assert type(sea_level).__name__ == "DemoMarineSource"
        assert sea_level.variable == "TOTAL_MODELLED_SEA_LEVEL"
        assert app.state.tide_service is None

asyncio.run(verify_startup())
"""
    environment = os.environ.copy()
    environment.pop("DATABASE_URL", None)
    environment.pop("REDIS_URL", None)
    environment["REDIS_ENABLED"] = "false"
    environment["CHLOROPHYLL_ENABLED"] = "false"
    environment["COPERNICUS_TIDES_ENABLED"] = "false"

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_snapshot_startup_is_lazy_and_combined_sst_remains_direct(tmp_path: Path) -> None:
    script = r"""
import asyncio
import importlib.abc
import sys

class BlockCopernicus(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "copernicusmarine" or fullname.startswith("copernicusmarine."):
            raise ModuleNotFoundError("copernicusmarine intentionally unavailable")
        return None

sys.meta_path.insert(0, BlockCopernicus())
from app.main import app

async def verify():
    async with app.router.lifespan_context(app):
        assert app.state.sst_snapshot_manager is not None
        assert app.state.sst_snapshot_manager.provider is app.state.sst_service.provider
        sst = next(source for source in app.state.marine_service.sources if source.name == "sst")
        assert type(sst).__name__ == "CopernicusSSTMarineSource"
        assert type(sst).__name__ != "SSTSnapshotManager"
        assert "copernicusmarine" not in sys.modules

asyncio.run(verify())
"""
    environment = os.environ.copy()
    environment.update({
        "REDIS_ENABLED": "false",
        "COPERNICUS_SST_ENABLED": "true",
        "MARINE_SNAPSHOTS_ENABLED": "true",
        "MARINE_SNAPSHOT_STARTUP_WARM_ENABLED": "false",
        "MARINE_SNAPSHOT_PREWARM_POINTS_JSON": "[]",
        "COPERNICUS_WAVES_ENABLED": "false",
        "COPERNICUS_WIND_ENABLED": "false",
        "CHLOROPHYLL_ENABLED": "false",
        "COPERNICUS_CURRENTS_ENABLED": "false",
        "COPERNICUS_TIDES_ENABLED": "false",
        "ECMWF_WIND_ENABLED": "false",
    })
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=tmp_path, env=environment,
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr


def test_chlorophyll_snapshot_startup_is_lazy_and_combined_remains_direct(
    tmp_path: Path,
) -> None:
    script = r"""
import asyncio
import importlib.abc
import sys

class BlockCopernicus(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "copernicusmarine" or fullname.startswith("copernicusmarine."):
            raise ModuleNotFoundError("copernicusmarine intentionally unavailable")
        return None

sys.meta_path.insert(0, BlockCopernicus())
from app.main import app

async def verify():
    async with app.router.lifespan_context(app):
        manager = app.state.chlorophyll_snapshot_manager
        assert manager is not None
        assert manager.provider is app.state.chlorophyll_service.provider
        source = next(
            item for item in app.state.marine_service.sources
            if item.name == "chlorophyll"
        )
        assert type(source).__name__ == "CopernicusChlorophyllMarineSource"
        assert "copernicusmarine" not in sys.modules

asyncio.run(verify())
"""
    environment = os.environ.copy()
    environment.update({
        "REDIS_ENABLED": "false",
        "COPERNICUS_SST_ENABLED": "false",
        "CHLOROPHYLL_ENABLED": "true",
        "MARINE_SNAPSHOTS_ENABLED": "true",
        "CHLOROPHYLL_SNAPSHOTS_ENABLED": "true",
        "CHLOROPHYLL_SNAPSHOT_STARTUP_WARM_ENABLED": "false",
        "MARINE_SNAPSHOT_PREWARM_POINTS_JSON": "[]",
        "COPERNICUS_WAVES_ENABLED": "false",
        "COPERNICUS_WIND_ENABLED": "false",
        "COPERNICUS_CURRENTS_ENABLED": "false",
        "COPERNICUS_TIDES_ENABLED": "false",
        "ECMWF_WIND_ENABLED": "false",
    })
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=tmp_path, env=environment,
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr


def test_sst_and_chlorophyll_snapshots_share_store_and_job_limit(tmp_path: Path) -> None:
    script = r"""
import asyncio
from app.main import app

async def verify():
    async with app.router.lifespan_context(app):
        sst = app.state.sst_snapshot_manager
        chlorophyll = app.state.chlorophyll_snapshot_manager
        assert sst.store is chlorophyll.store
        assert sst.jobs is chlorophyll.jobs
        assert app.state.snapshot_job_manager is sst.jobs

asyncio.run(verify())
"""
    environment = os.environ.copy()
    environment.update({
        "REDIS_ENABLED": "false",
        "COPERNICUS_SST_ENABLED": "true",
        "CHLOROPHYLL_ENABLED": "true",
        "MARINE_SNAPSHOTS_ENABLED": "true",
        "CHLOROPHYLL_SNAPSHOTS_ENABLED": "true",
        "MARINE_SNAPSHOT_STARTUP_WARM_ENABLED": "false",
        "CHLOROPHYLL_SNAPSHOT_STARTUP_WARM_ENABLED": "false",
        "MARINE_SNAPSHOT_PREWARM_POINTS_JSON": "[]",
        "COPERNICUS_WAVES_ENABLED": "false",
        "COPERNICUS_WIND_ENABLED": "false",
        "COPERNICUS_CURRENTS_ENABLED": "false",
        "COPERNICUS_TIDES_ENABLED": "false",
        "ECMWF_WIND_ENABLED": "false",
    })
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=tmp_path, env=environment,
        capture_output=True, text=True, check=False,
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

from datetime import UTC, datetime, timedelta
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
            "at": (datetime.now(UTC) + timedelta(hours=24)).isoformat(),
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


def test_enabled_chlorophyll_missing_optional_package_is_controlled(
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
    assert "copernicusmarine" not in sys.modules
    assert "/v1/marine/chlorophyll" in client.get("/openapi.json").json()["paths"]
    response = client.get(
        "/v1/marine/chlorophyll",
        params={
            "latitude": 18.025,
            "longitude": 70.525,
            "at": "2026-08-30T12:00:00Z",
        },
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "CHLOROPHYLL_DEPENDENCY_MISSING"
"""
    environment = os.environ.copy()
    environment["COPERNICUS_SST_ENABLED"] = "false"
    environment["COPERNICUS_WAVES_ENABLED"] = "false"
    environment["COPERNICUS_WIND_ENABLED"] = "false"
    environment["ECMWF_WIND_ENABLED"] = "false"
    environment["CHLOROPHYLL_ENABLED"] = "true"
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


def test_enabled_currents_missing_optional_package_is_controlled(tmp_path: Path) -> None:
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
    assert "copernicusmarine" not in sys.modules
    assert "/v1/marine/currents" in client.get("/openapi.json").json()["paths"]
    response = client.get("/v1/marine/currents", params={"latitude":18.025,"longitude":70.525,"at":"2026-08-31T22:00:00Z"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "CURRENT_DEPENDENCY_MISSING"
"""
    environment = os.environ.copy()
    environment.update({
        "COPERNICUS_SST_ENABLED":"false", "COPERNICUS_WAVES_ENABLED":"false",
        "COPERNICUS_WIND_ENABLED":"false", "ECMWF_WIND_ENABLED":"false",
        "CHLOROPHYLL_ENABLED":"false", "COPERNICUS_CURRENTS_ENABLED":"true",
        "COPERNICUS_TIDES_ENABLED":"false",
        "REDIS_ENABLED":"false",
    })
    result = subprocess.run([sys.executable,"-c",script],cwd=tmp_path,env=environment,capture_output=True,text=True,check=False)
    assert result.returncode == 0, result.stderr


def test_enabled_tides_missing_optional_package_is_controlled(tmp_path: Path) -> None:
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
    assert "copernicusmarine" not in sys.modules
    paths=client.get("/openapi.json").json()["paths"]
    assert "/v1/marine/sea-level" in paths
    assert "/v1/marine/sea-level/events" in paths
    response=client.get("/v1/marine/sea-level",params={"latitude":18.025,"longitude":70.525,"at":"2026-09-01T12:00:00Z"})
    assert response.status_code==503
    assert response.json()["detail"]["code"]=="TIDE_DEPENDENCY_MISSING"
"""
    environment=os.environ.copy()
    environment.update({
        "COPERNICUS_SST_ENABLED":"false","COPERNICUS_WAVES_ENABLED":"false",
        "COPERNICUS_WIND_ENABLED":"false","ECMWF_WIND_ENABLED":"false",
        "CHLOROPHYLL_ENABLED":"false","COPERNICUS_CURRENTS_ENABLED":"false",
        "COPERNICUS_TIDES_ENABLED":"true","REDIS_ENABLED":"false",
    })
    result=subprocess.run([sys.executable,"-c",script],cwd=tmp_path,env=environment,capture_output=True,text=True,check=False)
    assert result.returncode==0,result.stderr

def test_global_app_diagnostics_are_disabled_by_default() -> None:
    from app.core.config import Settings

    defaults = Settings(_env_file=None)
    assert defaults.performance_diagnostics_enabled is False
    assert defaults.performance_server_timing_enabled is False
