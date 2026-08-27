from pathlib import Path

import httpx
import pytest

from app.clients.incois_pfz import IncoisPFZClient


FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_client_creates_new_session_and_succeeds_on_retry() -> None:
    home_calls = 0
    sector_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal home_calls, sector_calls

        if request.url.path.endswith("TextDataHome"):
            home_calls += 1
            return httpx.Response(
                200,
                text=load_fixture("incois_home.html"),
                headers={"set-cookie": f"JSESSIONID=session-{home_calls}; Path=/"},
            )

        sector_calls += 1
        assert "JSESSIONID=" in request.headers.get("cookie", "")
        fixture = "invalid_session.html" if sector_calls == 1 else "incois_sec001.html"
        return httpx.Response(200, text=load_fixture(fixture))

    transport = httpx.MockTransport(handler)

    def client_factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=transport,
            base_url="https://incois.test",
            follow_redirects=True,
        )

    client = IncoisPFZClient(
        base_url="https://incois.test",
        session_attempts=2,
        client_factory=client_factory,
    )

    result = await client.fetch_sector("SEC001")

    assert result.sector_code == "SEC001"
    assert home_calls == 2
    assert sector_calls == 2

