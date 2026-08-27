import os
import subprocess
import sys
from pathlib import Path


def test_application_starts_without_database_or_redis_package(tmp_path: Path) -> None:
    script = r"""
import asyncio
import importlib.abc
import sys

class BlockRedis(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "redis" or fullname.startswith("redis."):
            raise ModuleNotFoundError("redis intentionally unavailable")
        return None

sys.meta_path.insert(0, BlockRedis())

from app.main import app

async def verify_startup():
    async with app.router.lifespan_context(app):
        cache = app.state.marine_service.cache
        assert type(cache).__name__ == "MemoryJsonCache"
        assert "redis" not in sys.modules

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
