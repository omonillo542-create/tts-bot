# -*- coding: utf-8 -*-
"""
O'zbekcha matnni Fish Audio TTS uchun tayyorlash.

NIMA UCHUN KERAK?
Fish Audio S2 modeli asosan ingliz va xitoy tilida o'qitilgan. O'zbekcha
lotin yozuvini to'g'ridan-to'g'ri yuborsa talaffuz buziladi:

    "O'zbekiston"  ->  "ozbekiston"   (apostrof yo'qoladi, urg'u noto'g'ri)
    "qalqon"       ->  "kalkon"       (q  -> k)
    "xabar"        ->  "ksabar"       (x  -> ks)
    "to'g'ri"      ->  "tug'ri"       (o' -> u)
    "2025"         ->  "ikki nol ikki besh"  (raqamlar noto'g'ri o'qiladi)

YECHIM — matnni o'zbek kirillchasiga o'tkazish. Fish Audio'ning kirill
(qisman ruscha) qo'llab-quvvatlashi lotin yozuvidan ancha kuchli, va o'zbek
kirillchasi fonetik jihatdan rus yozuviga juda yaqin:

    o'  ->  у      (ў ning fonetik ekvivalenti)
    g'  ->  г      (ғ ning fonetik ekvivalenti)
    q   ->  к      (қ rus yozuvida "к" deb yoziladi)
    x   ->  х      (ҳ rus yozuvida "х" deb yoziladi)

Shuning uchun har bir o'zbek harfi **standart rus kirillchasiga** joylanadi:
model uchun ma'lum harflar, talaffuz esa maksimal aniqlik.
Matn to'liq kirill bo'lib qoladi — orasida "lotin" harf qolmaydi.

Yana ikki muammo ham shu yerda hal qilinadi:
  1. Raqamlar o'zbekcha so'zlarga aylantiriladi ("2025" -> "ikki ming
     yigirma besh").
  2. "o'" belgisi "ў" emas, "ъ" (ayin) bo'lganda farqlanadi:
     "ma'lumot" -> "маълумот", lekin "o'zbek" -> "узбек".

Barcha funksiyalar **sof (deterministik)** — tashqi API chaqirilmaydi,
shuning uchun tez, bepul va xatoga chiqmaydi.
"""

from __future__ import annotations

import re

__all__ = [
    "UZBEK_MODE_CYRILLIC",
    "UZBEK_MODE_LATIN",
    "UZBEK_MODE_OFF",
    "looks_like_uzbek",
    "latin_to_cyrillic",
    "numbers_to_uzbek_words",
    "prepare_for_fish",
    "int_to_uzbek_words",
]

UZBEK_MODE_CYRILLIC = "cyrillic"
UZBEK_MODE_LATIN = "latin"
UZBEK_MODE_OFF = "off"


# =============================================
# KIRILL O'ZBEK ALIFBOSI (rus yozuviga mos)
# =============================================

_CYR = {
    "a": "а", "b": "б", "v": "в", "g": "г", "d": "д", "e": "е",
    "z": "з", "i": "и", "j": "ж", "k": "к", "l": "л", "m": "м",
    "n": "н", "o": "о", "p": "п", "r": "р", "s": "с", "t": "т",
    "u": "у", "f": "ф", "x": "х", "h": "х",
    "q": "к",   # қ  -> к
    "c": "к",
    "w": "в",
    "y": "й",
}

# Ikki harfli kombinatsiyalar
_DIGRAPHS = {
    "ch": "ч",
    "sh": "ш",
    "ts": "ц",
    "yo": "йо",
    "yu": "ю",
    "ye": "йе",
}

# Apostrofli so'zlar — "o'" bu yerda glottal emas, oddiy "o" (masalan "o'n")
_WORD_EXCEPTIONS = {
    "o'n": "он",
    "o'nlab": "онлаб",
}

# O'zbek tilidagi apostrofli so'zlar (ayin -> ъ)
_UZ_WORDS = {
    "va", "ham", "uchun", "bilan", "bo'lsa", "shu", "bu", "men", "siz",
    "bitta", "kerak", "bo'ldi", "degan", "keyin", "hamda", "barcha", "eng",
    "kabi", "assalomu", "alaykum", "rahmat", "xayr", "zo'r", "chiroyli",
    "katta", "kichik", "bugun", "ertaga", "kechqurun", "tong", "qayerda",
    "qanday", "nima", "kim", "qachon", "nega", "chunonchi", "albatta",
    "xuddi", "ozbek", "toshkent", "samarqand", "buxoro", "andijon",
    "namangan", "kokand", "yirik", "kichkina", "yana", "barchasi", "hech",
    "shuning", "o'sha", "ular", "biz", "u",
    "xabar", "xabaringiz", "hamma", "oz", "haqida", "bo'yicha", "keyingi",
    "oldingi", "kattaroq", "bo'ldi", "bo'lgan", "uchun", "guruh", "jamoa",
}


# =============================================
# O'ZBEK TILINI ANIQLASH
# =============================================

_UZ_CYRILLIC_RE = re.compile(r"[ўқғҳЎҚҒҲ]")
_UZ_APOSTROPHE_RE = re.compile(r"[oOgG]['ʼʻ]")
_LATIN_WORD_RE = re.compile(r"[A-Za-z]+(?:['ʼʻ][A-Za-z]+)*")
_UZ_WORDS_RE = re.compile(r"[a-z'ʼʻ]+")


def looks_like_uzbek(text: str) -> bool:
    """Matn o'zbek tilida ekanini taxmin qiladi.

    Fish Audio uchun matnni o'zgartirish faqat o'zbek matnida xavfsiz —
    ingliz/rus matni tegilmasligi kerak.
    """
    if not text:
        return False

    low = text.lower()

    # Kirill o'zbek alifbosidagi belgilar — aniq belgi
    if _UZ_CYRILLIC_RE.search(low):
        return True

    words = _UZ_WORDS_RE.findall(low)
    if not words:
        return False

    # O'zbekcha apostrofli so'zlar (o', g') — juda kuchli belgi
    if len(_UZ_APOSTROPHE_RE.findall(low)) >= 1:
        return True

    # Tipik o'zbek so'zlari
    hits = sum(1 for w in words if w in _UZ_WORDS)
    if hits >= 2:
        return True
    # Bitta aniq o'zbek so'zi + matn qisqa bo'lsa
    if hits >= 1 and (hits / len(words)) >= 0.2:
        return True

    return False


# =============================================
# LOTIN -> KIRILL
# =============================================

def _translit_word(word: str) -> str:
    """Bitta lotin so'zni kirillga o'tkazadi."""
    if not word:
        return word

    low = word.lower()
    if low in _WORD_EXCEPTIONS:
        exc = _WORD_EXCEPTIONS[low]
        if word[0].isupper():
            return exc[0].upper() + exc[1:]
        return exc

    out: list[str] = []
    i = 0
    n = len(word)

    while i < n:
        ch = word[i]
        low_ch = ch.lower()

        # Uch harfli kombinatsiya
        if word[i:i + 3].lower() == "ts":
            out.append("ц")
            i += 3
            continue

        # Ikki harfli kombinatsiya
        two = word[i:i + 2].lower()
        if two in _DIGRAPHS:
            piece = _DIGRAPHS[two]
            if ch.isupper():
                piece = piece[0].upper() + piece[1:]
            out.append(piece)
            i += 2
            continue

        # Apostrof: o' -> у, g' -> г, boshqa unli -> у/ъ
        if low_ch in "'ʼʻ":
            if out:
                # Oxirgi **belgi**ni tekshiramiz — digraph ("йо") bir bo'lakda
                # bo'lgani uchun butun elementni emas, oxirgi harfini olamiz.
                last = out[-1][-1]
                last_low = last.lower()
                if last_low == "о":
                    # o' (glottal o) -> у
                    out[-1] = out[-1][:-1] + ("У" if last.isupper() else "у")
                elif last_low == "г":
                    # g' (ғ) -> г  (o'zgarish yo'q)
                    pass
                elif last_low in "аеиу":
                    # a'/e'/i'/u' -> аъ/еъ/иъ/уъ  (ayin)
                    out.append("ъ")
                # boshqa holatlar: apostrofni tashlab qolamiz
            i += 1
            continue

        # Oddiy harf
        if low_ch in _CYR:
            piece = _CYR[low_ch]
            if ch.isupper():
                piece = piece.upper()
            out.append(piece)
            i += 1
            continue

        # Noma'lum belgi — o'zgartirmay qoldiramiz
        out.append(ch)
        i += 1

    return "".join(out)


def latin_to_cyrillic(text: str) -> str:
    """Matndagi lotin so'zlarni o'zbek kirillchasiga o'tkazadi.

    Punktuatsiya, raqamlar va boshqa belgilar o'zgarishsiz qoladi.
    """
    if not text:
        return text

    def repl(match: re.Match) -> str:
        return _translit_word(match.group(0))

    return _LATIN_WORD_RE.sub(repl, text)


# =============================================
# RAQAMLAR -> O'ZBEK SO'ZLARI
# =============================================

_UZ_ONES = [
    "nol", "bir", "ikki", "uch", "to'rt", "besh",
    "olti", "yetti", "sakkiz", "to'qqiz",
]
_UZ_TENS = [
    "", "o'n", "yigirma", "o'ttiz", "qirq", "ellik",
    "olmish", "yetmish", "sakson", "to'qqiz",
]
_UZ_HUNDREDS = [
    "", "yuz", "ikki yuz", "uch yuz", "to'rt yuz", "besh yuz",
    "olti yuz", "yetti yuz", "sakkiz yuz", "to'qqiz yuz",
]

_NUM_RE = re.compile(r"\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?")
_THOUSANDS_RE = re.compile(r"^\d{1,3}(?:[.,]\d{3})+$")
_DECIMAL_RE = re.compile(r"^\d+[.,]\d+$")


def int_to_uzbek_words(n: int) -> str:
    """Butun sonni o'zbekcha so'zlarga aylantiradi."""
    if n < 0:
        return "minus " + int_to_uzbek_words(-n)
    if n < 10:
        return _UZ_ONES[n]
    if n < 20:
        rest = n - 10
        return _UZ_TENS[1] + (" " + _UZ_ONES[rest] if rest else "")
    if n < 100:
        tens, ones = divmod(n, 10)
        return _UZ_TENS[tens] + (" " + _UZ_ONES[ones] if ones else "")
    if n < 1000:
        hund, rest = divmod(n, 100)
        return _UZ_HUNDREDS[hund] + (" " + int_to_uzbek_words(rest) if rest else "")
    if n < 1_000_000:
        thou, rest = divmod(n, 1000)
        return int_to_uzbek_words(thou) + " ming" + (
            " " + int_to_uzbek_words(rest) if rest else ""
        )
    if n < 1_000_000_000:
        mil, rest = divmod(n, 1_000_000)
        return int_to_uzbek_words(mil) + " million" + (
            " " + int_to_uzbek_words(rest) if rest else ""
        )
    if n < 1_000_000_000_000:
        mil, rest = divmod(n, 1_000_000_000)
        return int_to_uzbek_words(mil) + " milliard" + (
            " " + int_to_uzbek_words(rest) if rest else ""
        )
    return str(n)


def numbers_to_uzbek_words(text: str) -> str:
    """Matndagi raqamlarni o'zbekcha so'zlarga aylantiradi.

    "2025"        -> "ikki ming yigirma besh"
    "3.5"         -> "uch butun besh"
    "1,234"       -> "bir ming ikki yuz o'ttiz to'rt"
    "12:30"       -> "o'n ikki" + ":" + "o'ttiz"  (":" o'zgarishsiz qoladi)
    """
    if not text:
        return text

    def repl(match: re.Match) -> str:
        raw = match.group(0)
        if _THOUSANDS_RE.match(raw):
            digits = raw.replace(",", "").replace(".", "")
            if not digits.isdigit():
                return raw
            return int_to_uzbek_words(int(digits))
        if _DECIMAL_RE.match(raw):
            whole, frac = re.split(r"[.,]", raw)
            if not whole.isdigit() or not frac.isdigit():
                return raw
            return int_to_uzbek_words(int(whole)) + " butun " + int_to_uzbek_words(int(frac))
        if raw.isdigit():
            return int_to_uzbek_words(int(raw))
        return raw

    return _NUM_RE.sub(repl, text)


# =============================================
# ASOSIY FUNKSIYA
# =============================================

def prepare_for_fish(
    text: str,
    lang: str = "uz",
    mode: str = UZBEK_MODE_CYRILLIC,
) -> str:
    """Matnni Fish Audio uchun tayyorlaydi.

    mode:
        "cyrillic" — raqamlar so'zlarga + lotin -> kirill (eng sifatli)
        "latin"    — faqat raqamlar so'zlarga (matn o'zgarishsiz qoladi)
        "off"      — hech narsa o'zgartirilmaydi
    """
    if not text:
        return text

    mode = (mode or UZBEK_MODE_OFF).strip().lower()
    if mode == UZBEK_MODE_OFF:
        return text

    lang = (lang or "").strip().lower()
    if lang not in ("uz", "uzb", "uz-latn", "uz_latin", "uzlatn"):
        return text

    if not looks_like_uzbek(text):
        return text

    out = numbers_to_uzbek_words(text)

    if mode == UZBEK_MODE_CYRILLIC:
        out = latin_to_cyrillic(out)

    return out
