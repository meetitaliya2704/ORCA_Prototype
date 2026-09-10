import pytest
from app.agents.multilingual import (
    detect_language,
    format_assessment_response,
    format_clarification_answer,
    format_default_greeting,
    format_inland_prefix_for_pfz,
    format_land_notice,
    format_marine_conditions_response,
    format_pfz_bulletin,
    format_planned_answer,
    translate_marine_reading,
)
from app.schemas.assistant import AssistantIntent, AssistantLanguage, RequiredInformation


def test_language_detection():
    assert detect_language("Hello", AssistantLanguage.HINDI) == "hi"
    assert detect_language("Hello", AssistantLanguage.GUJARATI) == "gu"
    assert detect_language("Hello", AssistantLanguage.MARATHI) == "mr"
    assert detect_language("Hello", AssistantLanguage.TAMIL) == "ta"
    assert detect_language("Hello", AssistantLanguage.TELUGU) == "te"
    assert detect_language("Hello", AssistantLanguage.MALAYALAM) == "ml"
    assert detect_language("Hello", AssistantLanguage.BENGALI) == "bn"
    assert detect_language("Hello", AssistantLanguage.ENGLISH) == "en"
    assert detect_language("\u0aa6\u0ab0\u0abf\u0aaf\u0abe\u0aa8\u0ac0", AssistantLanguage.ENGLISH) == "gu"
    assert detect_language("\u0b90\u0bbd\u0bad\u0bbe\u0b90\u0bcd", AssistantLanguage.ENGLISH) == "ta"
    assert detect_language("\u0c15\u0c4d\u0c30\u0c35\u0c43\u0c34\u0c35", AssistantLanguage.ENGLISH) == "te"
    assert detect_language("\u0d15\u0d3d\u0d24\u0d38\u0d31", AssistantLanguage.ENGLISH) == "ml"
    assert detect_language("\u0990\u09aa\u09af\u09be\u0982", AssistantLanguage.ENGLISH) == "bn"
    assert detect_language("सागरी परिस्थिती कशी आहे", AssistantLanguage.ENGLISH) == "mr"
    assert detect_language("समुद्र की स्थिति कैसी है", AssistantLanguage.ENGLISH) == "hi"


def test_land_notice_multilingual():
    for lang in ["en", "hi", "gu", "mr", "ta", "te", "ml", "bn"]:
        notice = format_land_notice(lang, 23.0225, 72.5714, "Gulf of Khambhat", 80.0)
        assert "23.0225" in notice
        assert "72.5714" in notice
        assert "Gulf of Khambhat" in notice
        assert "80" in notice



def test_pfz_bulletin_multilingual():
    for lang in ["en", "hi", "gu", "mr", "ta", "te", "ml", "bn"]:
        bulletin = format_pfz_bulletin(
            lang=lang,
            landing_centre="Veraval",
            direction="SSW",
            bearing_deg=195.0,
            dist_coast_str="15 - 25 km",
            depth_str="30 - 45 m",
            lat_dms="20°45'12\varningN",
            lat_num=20.7533,
            lon_dms="70°15'30\varwing",
            lon_num=70.2583,
            sector_code="SEC001",
            region_name="Gujarat",
            distance_km=22.4,
            date_str="12 Sep 2026 18:00 UTC",
        )
        assert "Veraval" in bulletin
        assert "SEC001" in bulletin


def test_marine_conditions_multilingual():
    readings = ["Significant wave height: 1.4 m", "Wind speed: 7.2 m/s"]
    for lang in ["en", "hi", "gu", "mr", "ta", "te", "ml", "bn"]:
        resp = format_marine_conditions_response(lang, readings, "complete", 6)
        assert "1.4 m" in resp



def test_clarification_and_planned_multilingual():
    for lang in ["en", "hi", "gu", "mr", "ta", "te", "ml", "bn"]:
        clar = format_clarification_answer(lang, (RequiredInformation.LOCATION, RequiredInformation.REQUESTED_TIME))
        assert len(clar) > 10
        plan = format_planned_answer(lang, AssistantIntent.OFFICIAL_ALERTS)
        assert len(plan) > 10

