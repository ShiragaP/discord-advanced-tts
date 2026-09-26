"""
Unit tests for ThaiTextNormalizer.
"""

import pytest
from shared.thai_normalizer import ThaiTextNormalizer


@pytest.fixture
def normalizer():
    return ThaiTextNormalizer()


def test_clean_urls(normalizer):
    text = "ไปดูคลิปนี้กัน https://www.youtube.com/watch?v=123 สนุกมาก"
    result = normalizer.normalize(text)
    assert "https" not in result
    assert "ส่งลิงก์" in result


def test_discord_mentions(normalizer):
    text = "สวัสดี <@123456789> เข้ามาในห้อง <#987654321> หน่อย"
    result = normalizer.normalize(text)
    assert "<@" not in result
    assert "<#" not in result
    assert "แท็กสมาชิก" in result
    assert "แท็กห้อง" in result


def test_gaming_slang(normalizer):
    text = "แมตช์นี้ gg มากครับ ez สุดๆ"
    result = normalizer.normalize(text)
    assert "จีจี" in result
    assert "อีซี่" in result


def test_repeated_characters(normalizer):
    text = "ดีมากกกกกกกกกก"
    result = normalizer.normalize(text)
    assert result == "ดีมากก"


def test_laughing_555(normalizer):
    text = "ตลกมาก 55555"
    result = normalizer.normalize(text)
    assert "ฮ่าๆๆ" in result


def test_sentence_chunking(normalizer):
    long_text = "ประโยคที่หนึ่งยาวพอสมควร " * 10
    chunks = normalizer.split_sentences(long_text, max_chars=50)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= 60  # Allow small word boundary padding
