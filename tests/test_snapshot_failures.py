import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.routes.marine import router
from app.clients.copernicus_sst import (
    InvalidSSTResponseError,
    SSTAuthenticationError,
    SSTDependencyMissingError,
    SSTRateLimitedError,
    SSTSourceNotConfiguredError,
    SSTSourceUnavailableError,
)
from app.services.sst import NoValidSSTError
from app.snapshots.jobs import (
    RefreshBlockedError,
    RefreshJobManager,
    classify_refresh_failure,
)
from app.snapshots.models import RefreshFailureClassification
from app.snapshots.store import InMemorySnapshotStore
from tests.test_sst_snapshots import FakeRegionalProvider, make_manager


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (TimeoutError(), RefreshFailureClassification.RETRYABLE),
        (ConnectionResetError(), RefreshFailureClassification.RETRYABLE),
        (SSTSourceUnavailableError(), RefreshFailureClassification.RETRYABLE),
        (SSTRateLimitedError("limited", retry_after_seconds=60), RefreshFailureClassification.RETRYABLE),
        (SSTAuthenticationError(), RefreshFailureClassification.NON_RETRYABLE),
        (SSTDependencyMissingError(), RefreshFailureClassification.NON_RETRYABLE),
        (SSTSourceNotConfiguredError(), RefreshFailureClassification.NON_RETRYABLE),
        (InvalidSSTResponseError(), RefreshFailureClassification.NON_RETRYABLE),
        (ValueError(), RefreshFailureClassification.NON_RETRYABLE),
        (NoValidSSTError(), RefreshFailureClassification.REQUEST_RESULT),
    ],
)
def test_refresh_failure_classification(error, expected):
    assert classify_refresh_failure(error) == expected


@pytest.mark.asyncio
async def test_authentication_gate_prevents_sequential_and_concurrent_retry_storm():
    provider = FakeRegionalProvider(error=SSTAuthenticationError("secret"))
    manager, provider, _ = make_manager(provider)
    accepted = await manager.get_sst(latitude=18.025, longitude=70.525)
    await manager.jobs.wait(accepted.job_id, 1)

    for _ in range(10):
        with pytest.raises(SSTAuthenticationError):
            await manager.get_sst(latitude=18.025, longitude=70.525)
    results = await asyncio.gather(*[
        manager.get_sst(latitude=18.025, longitude=70.525)
        for _ in range(10)
    ], return_exceptions=True)
    assert all(isinstance(item, SSTAuthenticationError) for item in results)
    assert provider.calls == 1

    status = await manager.job_status(accepted.job_id)
    assert status.state == "failed"
    assert status.retryable is False
    assert status.next_retry_at is None
    assert status.snapshot_available is False
    serialized = status.model_dump_json()
    assert "secret" not in serialized
    assert "configuration_identity" not in serialized

    assert await manager.schedule_if_due(18.025, 70.525) is None
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_retryable_backoff_is_bounded_and_success_clears_gate():
    clock = [datetime(2026, 9, 1, 12, tzinfo=UTC)]
    store = InMemorySnapshotStore(now=lambda: clock[0])
    jobs = RefreshJobManager(
        store=store, now=lambda: clock[0],
        retryable_base_delay_seconds=30, retryable_max_delay_seconds=45,
    )
    calls = 0
    error = [True]
    async def factory(job_id):
        nonlocal calls
        calls += 1
        if error[0]:
            raise SSTSourceUnavailableError("private")
        from tests.test_snapshot_store import snapshot
        return snapshot(clock[0])

    first = await jobs.request(
        deduplication_key="data", failure_gate_key="gate",
        configuration_identity="config", source="sst", tile_id="tile", factory=factory,
    )
    failed = await jobs.wait(first.job_id, 1)
    assert failed.retryable is True
    assert failed.retry_after_seconds == 30
    with pytest.raises(RefreshBlockedError):
        await jobs.request(
            deduplication_key="data", failure_gate_key="gate",
            configuration_identity="config", source="sst", tile_id="tile", factory=factory,
        )
    clock[0] += timedelta(seconds=30)
    second = await jobs.request(
        deduplication_key="data", failure_gate_key="gate",
        configuration_identity="config", source="sst", tile_id="tile", factory=factory,
    )
    failed_again = await jobs.wait(second.job_id, 1)
    assert failed_again.retry_after_seconds == 45
    clock[0] += timedelta(seconds=45)
    error[0] = False
    success = await jobs.request(
        deduplication_key="data", failure_gate_key="gate",
        configuration_identity="config", source="sst", tile_id="tile", factory=factory,
    )
    assert (await jobs.wait(success.job_id, 1)).state == "succeeded"
    assert await jobs.failure_gate("gate") is None
    assert calls == 3

    error[0] = True
    after_success = await jobs.request(
        deduplication_key="data", failure_gate_key="gate",
        configuration_identity="config", source="sst", tile_id="tile", factory=factory,
    )
    assert (await jobs.wait(after_success.job_id, 1)).retry_after_seconds == 30


@pytest.mark.asyncio
async def test_configuration_change_and_explicit_retry_allow_one_controlled_attempt():
    now = datetime(2026, 9, 1, tzinfo=UTC)
    jobs = RefreshJobManager(store=InMemorySnapshotStore(now=lambda: now), now=lambda: now)
    calls = 0
    async def factory(job_id):
        nonlocal calls
        calls += 1
        raise SSTAuthenticationError()
    first = await jobs.request(
        deduplication_key="one", failure_gate_key="gate-one",
        configuration_identity="one", source="sst", tile_id="tile", factory=factory,
    )
    await jobs.wait(first.job_id, 1)
    changed = await jobs.request(
        deduplication_key="two", failure_gate_key="gate-two",
        configuration_identity="two", source="sst", tile_id="tile", factory=factory,
    )
    await jobs.wait(changed.job_id, 1)
    forced = await jobs.request(
        deduplication_key="one", failure_gate_key="gate-one",
        configuration_identity="one", source="sst", tile_id="tile", factory=factory,
        retry_failed=True,
    )
    await jobs.wait(forced.job_id, 1)
    assert calls == 3


def _application(manager):
    app = FastAPI()
    app.include_router(router, prefix="/v1")
    app.state.sst_service = manager.point_service
    app.state.sst_snapshot_manager = manager
    return app


@pytest.mark.asyncio
async def test_http_auth_failure_changes_202_to_503_without_another_job():
    provider = FakeRegionalProvider(error=SSTAuthenticationError("password=hidden"))
    manager, provider, _ = make_manager(provider)
    async with AsyncClient(
        transport=ASGITransport(app=_application(manager)), base_url="http://test"
    ) as client:
        first = await client.get("/v1/marine/sst", params={"latitude": 18.025, "longitude": 70.525})
        assert first.status_code == 202
        await manager.jobs.wait(first.json()["job_id"], 1)
        second = await client.get("/v1/marine/sst", params={"latitude": 18.025, "longitude": 70.525})
        assert second.status_code == 503
        assert second.json() == {"detail": {
            "code": "SST_AUTHENTICATION_FAILED",
            "message": "Copernicus SST authentication is unavailable",
        }}
        assert "job_id" not in second.text
        assert "hidden" not in second.text
        assert provider.calls == 1

        blocked_wait = await client.get(
            "/v1/marine/sst",
            params={
                "latitude": 18.025,
                "longitude": 70.525,
                "wait_for_refresh": "true",
            },
        )
        assert blocked_wait.status_code == 503
        assert provider.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_error", "expected_code"),
    [
        (SSTDependencyMissingError("private path"), "SST_SOURCE_NOT_CONFIGURED"),
        (SSTSourceNotConfiguredError("private configuration"), "SST_SOURCE_NOT_CONFIGURED"),
    ],
)
async def test_http_non_retryable_setup_failure_returns_503_without_retry(
    provider_error, expected_code,
):
    provider = FakeRegionalProvider(error=provider_error)
    manager, provider, _ = make_manager(provider)
    async with AsyncClient(
        transport=ASGITransport(app=_application(manager)), base_url="http://test"
    ) as client:
        first = await client.get(
            "/v1/marine/sst", params={"latitude": 18.025, "longitude": 70.525}
        )
        assert first.status_code == 202
        await manager.jobs.wait(first.json()["job_id"], 1)
        second = await client.get(
            "/v1/marine/sst", params={"latitude": 18.025, "longitude": 70.525}
        )
        assert second.status_code == 503
        assert second.json()["detail"]["code"] == expected_code
        assert "job_id" not in second.text
        assert "private" not in second.text
        assert provider.calls == 1


@pytest.mark.asyncio
async def test_http_retryable_cooldown_has_retry_after_header():
    provider = FakeRegionalProvider(error=SSTSourceUnavailableError("private URL"))
    manager, provider, _ = make_manager(provider)
    async with AsyncClient(
        transport=ASGITransport(app=_application(manager)), base_url="http://test"
    ) as client:
        first = await client.get("/v1/marine/sst", params={"latitude": 18.025, "longitude": 70.525})
        await manager.jobs.wait(first.json()["job_id"], 1)
        blocked = await client.get("/v1/marine/sst", params={"latitude": 18.025, "longitude": 70.525})
        assert blocked.status_code == 503
        assert blocked.headers["Retry-After"] == "30"
        assert blocked.json()["detail"]["retry_after_seconds"] == 30
        assert provider.calls == 1


@pytest.mark.asyncio
async def test_stale_snapshot_reports_blocked_not_refreshing_and_preserves_data():
    manager, provider, clock = make_manager(fresh=1, stale=120)
    original = await manager.get_sst(
        latitude=18.025, longitude=70.525, wait_for_refresh=True
    )
    clock[0] += timedelta(seconds=2)
    provider.error = SSTAuthenticationError("private")
    stale_refreshing = await manager.get_sst(latitude=18.025, longitude=70.525)
    await manager.jobs.wait(stale_refreshing.snapshot.refresh_job_id, 1)
    stale = await manager.get_sst(latitude=18.025, longitude=70.525)
    assert stale.snapshot.status == "stale"
    assert stale.snapshot.refresh_job_id is None
    assert stale.snapshot.refresh_blocked_until is not None
    assert stale.retrieved_at == original.retrieved_at
    assert provider.calls == 2
