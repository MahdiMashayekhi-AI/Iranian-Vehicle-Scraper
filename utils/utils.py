from typing import Optional


def fa_to_en_digits(text: str) -> Optional[int]:
    fa_to_en = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
    cleaned = text.translate(fa_to_en)
    digits = "".join(ch for ch in cleaned if ch.isdigit())
    return int(digits) if digits else None