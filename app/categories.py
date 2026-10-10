"""Category definitions and keyword-based guessing (rule based, no LLM)."""
from __future__ import annotations

EXPENSE_CATEGORIES = [
    "อาหาร",
    "เดินทาง",
    "ช้อปปิ้ง",
    "บิล",
    "ที่พัก",
    "สุขภาพ",
    "บันเทิง",
    "การศึกษา",
    "อื่นๆ",
]

INCOME_CATEGORIES = [
    "เงินเดือน",
    "โบนัส",
    "ขายของ",
    "ดอกเบี้ย",
    "อื่นๆ",
]

FALLBACK_CATEGORY = "อื่นๆ"

# Keys are checked top-to-bottom; the first substring hit wins.
EXPENSE_KEYWORDS: dict[str, list[str]] = {
    "อาหาร": [
        "กาแฟ", "ชา", "น้ำ", "ข้าว", "ก๋วยเตี๋ยว", "ขนม", "อาหาร", "หมูกระทะ",
        "บุฟเฟ่", "ส้มตำ", "พิซซ่า", "ไก่", "หมู", "เนื้อ", "ปลา", "ผัด", "ต้ม",
        "แกง", "สุกี้", "หม่าล่า", "นม", "ไข่", "ผลไม้", "ของกิน", "เซเว่น",
        "seven", "ร้าน", "ชาบู", "ยำ", "ข้าวมันไก่", "lunch", "dinner", "breakfast",
    ],
    "เดินทาง": [
        "bts", "mrt", "แท็กซี่", "taxi", "วิน", "น้ำมัน", "แก๊ส", "ค่าทาง",
        "เครื่องบิน", "รถไฟ", "grab", "bolt", "lineman", "ค่าโดยสาร", "ที่จอด",
        "จอด", "มอไซค์", "รถเมล์", "ค่ารถ",
    ],
    "ช้อปปิ้ง": [
        "shopee", "lazada", "เสื้อ", "ผ้า", "รองเท้า", "กระเป๋า", "ของใช้",
        "หูฟัง", "เคส", "ซื้อ", "ไอเทม", "เครื่องสำอาง",
    ],
    "บิล": [
        "ค่าไฟ", "ค่าน้ำ", "ค่าเน็ต", "อินเทอร์เน็ต", "ค่าโทร", "มือถือ",
        "netflix", "spotify", "สมาชิก", "sub", "ผ่อน", "การ์ด", "บิล",
    ],
    "ที่พัก": ["ค่าเช่า", "ที่พัก", "หอ", "คอนโด", "โรงแรม"],
    "สุขภาพ": [
        "ยา", "หมอ", "โรงพยาบาล", "คลินิก", "ฟัน", "วิตามิน", "ประกัน", "ตรวจ",
    ],
    "บันเทิง": [
        "หนัง", "เกม", "เที่ยว", "คอนเสิร์ต", "คาราโอเกะ", "ปาร์ตี้",
        "แอลกอฮอล์", "เบียร์", "เหล้า",
    ],
    "การศึกษา": ["หนังสือ", "คอร์ส", "เรียน", "ติว", "อบรม"],
}

INCOME_KEYWORDS: dict[str, list[str]] = {
    "เงินเดือน": ["เงินเดือน", "salary"],
    "โบนัส": ["โบนัส", "bonus"],
    "ขายของ": ["ขาย", "ยอดขาย"],
    "ดอกเบี้ย": ["ดอกเบี้ย", "ปันผล", "interest"],
}


def guess_category(note: str, tx_type: str) -> str:
    """Return the best matching category for a transaction note."""
    text = (note or "").lower()
    table = EXPENSE_KEYWORDS if tx_type == "expense" else INCOME_KEYWORDS
    for category, keywords in table.items():
        for keyword in keywords:
            if keyword.lower() in text:
                return category
    return FALLBACK_CATEGORY


def categories_for(tx_type: str) -> list[str]:
    return INCOME_CATEGORIES if tx_type == "income" else EXPENSE_CATEGORIES
