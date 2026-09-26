"""
Thai Text Normalizer for Discord TTS.
Handles URLs, Discord mentions/emotes, numbers, repeated characters,
Thai gaming slang, and sentence chunking.
"""

import re
from typing import List, Dict


# Common gaming slang and abbreviations mapped to Thai pronunciation
DEFAULT_GAMING_SLANG: Dict[str, str] = {
    r"\bgg\b": "จีจี",
    r"\bez\b": "อีซี่",
    r"\bnt\b": "ไนซ์ทราย",
    r"\bmid\b": "มิด",
    r"\btop\b": "ท็อป",
    r"\bbot\b": "บอท",
    r"\bafk\b": "เอเอฟเค",
    r"\bdef\b": "เดฟ",
    r"\batk\b": "แอทแทก",
    r"\bcd\b": "คูลดาวน์",
    r"\bhp\b": "เลือด",
    r"\bmp\b": "มานา",
    r"\bbuff\b": "บัฟ",
    r"\bnerf\b": "เนิร์ฟ",
    r"\bdc\b": "หลุด",
    r"\bff\b": "ยอมแพ้",
    r"\bwp\b": "เวลเพลย์",
    r"\bgank\b": "แก๊งค์",
    r"\bgood game\b": "กู๊ดเกม",
    r"\bgl\b": "กู๊ดลัก",
    r"\bhf\b": "แฮฟฟัน",
    r"\bomg\b": "โอเอ็มจี",
    r"\bwtf\b": "วอทเดอะฟัก",
    r"\bpls\b": "พลีส",
    r"\bthx\b": "แต๊งกิ้ว",
    r"\bty\b": "แต๊งกิ้ว",
}

# Number dictionary for Thai digits
THAI_NUMBERS = {
    "0": "ศูนย์",
    "1": "หนึ่ง",
    "2": "สอง",
    "3": "สาม",
    "4": "สี่",
    "5": "ห้า",
    "6": "หก",
    "7": "เจ็ด",
    "8": "แปด",
    "9": "เก้า",
}


class ThaiTextNormalizer:
    def __init__(self, custom_slang: Dict[str, str] = None):
        self.slang_dict = dict(DEFAULT_GAMING_SLANG)
        if custom_slang:
            self.slang_dict.update(custom_slang)

    def normalize(self, text: str) -> str:
        if not text:
            return ""

        # 1. Clean URLs
        text = re.sub(r"https?://\S+|www\.\S+", "ส่งลิงก์", text)

        # 2. Discord mentions (<@ID>, <@!ID>, <#ID>, <@&ID>)
        text = re.sub(r"<@!?[0-9]+>", "แท็กสมาชิก", text)
        text = re.sub(r"<#[0-9]+>", "แท็กห้อง", text)
        text = re.sub(r"<@&[0-9]+>", "แท็กยศ", text)

        # 3. Discord custom emojis: <:emoji_name:123456> or <a:emoji_name:123456>
        text = re.sub(r"<a?:([a-zA-Z0-9_]+):[0-9]+>", r" \1 ", text)

        # 4. Remove unicode emojis and symbols (avoiding flowtts token error)
        # Keep Thai unicode range (0x0E00 - 0x0E7F), basic ASCII, and common punctuation
        text = self._strip_unsupported_symbols(text)

        # 5. Handle "555+" or "555" (Thai laughing)
        text = re.sub(r"5{3,}\+*", " ฮ่าๆๆ ", text)
        text = re.sub(r"5{2}", " ฮ่าฮ่า ", text)

        # 6. Normalize repeated characters (e.g. มากกกกก -> มากก, น้าาาาา -> น้าา)
        text = re.sub(r"(.)\1{3,}", r"\1\1", text)

        # 7. Apply gaming slang replacements (case-insensitive)
        for pattern, replacement in self.slang_dict.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        # 8. Collapse horizontal whitespace but preserve newlines
        text = re.sub(r"[^\S\r\n]+", " ", text)
        text = re.sub(r"\n+", "\n", text).strip()

        return text

    def _strip_unsupported_symbols(self, text: str) -> str:
        """Keep Thai characters, standard English letters, numbers, basic punctuation, and emotion brackets."""
        # Allowed chars: Thai \u0E00-\u0E7F, ASCII alphanum, whitespace, newlines, basic symbols, brackets, parentheses
        allowed_pattern = re.compile(r"[^\u0E00-\u0E7F\w\s.,!?'\"%+\-\[\]()~]")
        return allowed_pattern.sub(" ", text)

    def split_sentences(self, text: str, max_chars: int = 150) -> List[str]:
        """
        Split long text into sentence chunks within max_chars limit.
        Preserves paragraph and emotion tag boundaries.
        Uses PyThaiNLP for word / sentence boundary where appropriate.
        """
        if not text:
            return []

        # If text contains newlines, process each paragraph separately to preserve emotion tag context
        if "\n" in text:
            paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
            all_chunks: List[str] = []
            for p in paragraphs:
                all_chunks.extend(self.split_sentences(p, max_chars=max_chars))
            return all_chunks

        if len(text) <= max_chars:
            return [text]

        try:
            from pythainlp.tokenize import sent_tokenize
            raw_sentences = sent_tokenize(text)
        except Exception:
            # Fallback split on whitespace / punctuation
            raw_sentences = re.split(r"([.!?\n\s]+)", text)

        chunks: List[str] = []
        current = ""

        for part in raw_sentences:
            if not part:
                continue
            if len(current) + len(part) <= max_chars:
                current += part
            else:
                if current.strip():
                    chunks.append(current.strip())
                # If a single sentence is larger than max_chars, split on space or words
                if len(part) > max_chars:
                    # Break long segment into words
                    try:
                        from pythainlp.tokenize import word_tokenize
                        words = word_tokenize(part)
                    except Exception:
                        words = part.split()

                    sub_chunk = ""
                    for w in words:
                        if len(sub_chunk) + len(w) <= max_chars:
                            sub_chunk += w
                        else:
                            if sub_chunk.strip():
                                chunks.append(sub_chunk.strip())
                            sub_chunk = w
                    current = sub_chunk
                else:
                    current = part

        if current.strip():
            chunks.append(current.strip())

        return chunks


normalizer = ThaiTextNormalizer()
