import re

from app.clients.incois_pfz import IncoisPFZClient
from app.parsers.pfz_html import parse_pfz_advisory
from app.schemas.pfz import PFZAdvisory


class PFZPreviewService:
    def __init__(self, client: IncoisPFZClient) -> None:
        self.client = client

    async def preview_sector(self, sector_code: str) -> PFZAdvisory:
        normalized = sector_code.strip().upper()
        if re.fullmatch(r"SEC\d{3}", normalized) is None:
            raise ValueError("sector_code must use the format SEC001")

        pages = await self.client.fetch_sector(normalized)
        return parse_pfz_advisory(
            sector_html=pages.sector_html,
            home_html=pages.home_html,
            sector_code=pages.sector_code,
            source_url=pages.source_url,
        )

