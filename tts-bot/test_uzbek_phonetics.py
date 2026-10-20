# -*- coding: utf-8 -*-
"""
O'zbekcha fonetik o'tkazish testlari (API chaqirilmaydi — tez va bepul).

Ishga tushirish:
    python test_uzbek_phonetics.py

Chiqish: har bir test "OK" yoki "FAIL" ko'rsatadi.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Windows konsolida emoji chiqmasligi uchun (cp1251 xatosi)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from uzbek_phonetics import (  # noqa: E402
    UZBEK_MODE_CYRILLIC,
    UZBEK_MODE_LATIN,
    UZBEK_MODE_OFF,
    int_to_uzbek_words,
    latin_to_cyrillic,
    looks_like_uzbek,
    numbers_to_uzbek_words,
    prepare_for_fish,
)

PASSED = 0
FAILED = 0


def check(name: str, got: str, want: str) -> None:
    global PASSED, FAILED
    if got == want:
        PASSED += 1
        print(f"  OK   {name}")
    else:
        FAILED += 1
        print(f"  FAIL {name}")
        print(f"       kutilgan: {want}")
        print(f"       kelgan:   {got}")


def check_bool(name: str, got: bool, want: bool) -> None:
    check(name, str(bool(got)), str(bool(want)))


# =============================================
print("\n1) LOTIN -> KIRILL")
# =============================================

check(
    "o'zbekiston",
    latin_to_cyrillic("O'zbekiston"),
    "Узбекистон",
)
check(
    "qalqon (q -> k)",
    latin_to_cyrillic("qalqon"),
    "калкон",
)
check(
    "xabar (x -> x)",
    latin_to_cyrillic("xabar"),
    "хабар",
)
check(
    "to'g'ri",
    latin_to_cyrillic("to'g'ri"),
    "тугри",
)
check(
    "ma'lumot (ayin -> ъ)",
    latin_to_cyrillic("ma'lumot"),
    "маълумот",
)
check(
    "bo'lsin (o' -> u)",
    latin_to_cyrillic("bo'lsin"),
    "булсин",
)
check(
    "o'quvchi",
    latin_to_cyrillic("o'quvchi"),
    "укувчи",
)
check(
    "g'oyasi (g' -> g)",
    latin_to_cyrillic("g'oyasi"),
    "гойаси",
)
check(
    "yulduz (yu -> yu)",
    latin_to_cyrillic("Yulduz"),
    "Юлдуз",
)
check(
    "yo'q (yo + o')",
    latin_to_cyrillic("yo'q"),
    "йук",
)
check(
    "she'rim (e' -> eъ)",
    latin_to_cyrillic("she'rim"),
    "шеърим",
)
check(
    "yaxshi (ya -> ya)",
    latin_to_cyrillic("yaxshi"),
    "йахши",
)
check(
    "chiroyli (ch -> ch)",
    latin_to_cyrillic("chiroyli"),
    "чиройли",
)
check(
    "kabi (k -> k)",
    latin_to_cyrillic("kabi"),
    "каби",
)
check(
    "punktuatsiya saqlanadi",
    latin_to_cyrillic("Salom! Qanday yaxshisiz?"),
    "Салом! Кандай йахшисиз?",
)
check(
    "kirill matn o'zgarilmaydi",
    latin_to_cyrillic("Привет, Салом"),
    "Привет, Салом",
)
check(
    "raqamlar o'zgarilmaydi",
    latin_to_cyrillic("2025"),
    "2025",
)


# =============================================
print("\n2) RAQAMLAR -> O'ZBEK SO'ZLARI")
# =============================================

check("0", int_to_uzbek_words(0), "nol")
check("5", int_to_uzbek_words(5), "besh")
check("10", int_to_uzbek_words(10), "o'n")
check("11", int_to_uzbek_words(11), "o'n bir")
check("25", int_to_uzbek_words(25), "yigirma besh")
check("100", int_to_uzbek_words(100), "yuz")
check("1500", int_to_uzbek_words(1500), "bir ming besh yuz")
check("2025", int_to_uzbek_words(2025), "ikki ming yigirma besh")
check("1000000", int_to_uzbek_words(1_000_000), "bir million")

check(
    "matn ichida 2025",
    numbers_to_uzbek_words("Bugun 2025-yil"),
    "Bugun ikki ming yigirma besh-yil",
)
check(
    "qo'shtirnoq (1,234)",
    numbers_to_uzbek_words("1,234 ta"),
    "bir ming ikki yuz o'ttiz to'rt ta",
)
check(
    "kasr (3.5)",
    numbers_to_uzbek_words("3.5 kg"),
    "uch butun besh kg",
)


# =============================================
print("\n3) O'ZBEK TILINI ANIQLASH")
# =============================================

check_bool("o'zbek matni", looks_like_uzbek("O'zbekiston mustaqil"), True)
check_bool("kirill o'zbek", looks_like_uzbek("Ўзбекистон"), True)
check_bool("tipik so'zlar", looks_like_uzbek("Men sizga yordam beraman va shu ishi"), True)
check_bool("qisqa o'zbek", looks_like_uzbek("Bugun 2025-yil 3 ta xabar"), True)
check_bool("ingliz matni", looks_like_uzbek("Hello world, this is an english sentence"), False)
check_bool("rus matni", looks_like_uzbek("Привет мир как дела"), False)
check_bool("bo'sh matn", looks_like_uzbek(""), False)


# =============================================
print("\n4) TO'LIQ PIPELINE (prepare_for_fish)")
# =============================================

check(
    "o'zbek matn -> kirill",
    prepare_for_fish(
        "Assalomu alaykum! Bugun 2025-yil 15-noyabr.",
        lang="uz",
        mode=UZBEK_MODE_CYRILLIC,
    ),
    "Ассалому алайкум! Бугун икки минг йигирма беш-йил он беш-нойабр.",
)

check(
    "uzbek matn -> kirill (2)",
    prepare_for_fish(
        "Bu yil 1500 ta odam, 1,234 ta mashina va 3.5 kg non oldim.",
        lang="uz",
        mode=UZBEK_MODE_CYRILLIC,
    ),
    "Бу йил бир минг беш юз та одам, бир минг икки юз уттиз турт та "
    "машина ва уч бутун беш кг нон олдим.",
)

check(
    "mode=latin: matn o'zgaradi, harflar qoladi",
    prepare_for_fish(
        "Bugun 2025-yil 3 ta xabar",
        lang="uz",
        mode=UZBEK_MODE_LATIN,
    ),
    "Bugun ikki ming yigirma besh-yil uch ta xabar",
)

check(
    "mode=off: hech narsa o'zgarmaydi",
    prepare_for_fish(
        "Bugun 2025-yil 3 ta xabar",
        lang="uz",
        mode=UZBEK_MODE_OFF,
    ),
    "Bugun 2025-yil 3 ta xabar",
)

check(
    "ingliz matn tegilmaydi",
    prepare_for_fish(
        "Hello world, this is 2025",
        lang="uz",
        mode=UZBEK_MODE_CYRILLIC,
    ),
    "Hello world, this is 2025",
)

check(
    "boshqa til tegilmaydi (ru)",
    prepare_for_fish(
        "Привет, это 2025 год",
        lang="ru",
        mode=UZBEK_MODE_CYRILLIC,
    ),
    "Привет, это 2025 год",
)


# =============================================
print("\n" + "=" * 52)
print(f"  O'tdi: {PASSED}   Yiqildi: {FAILED}")
print("=" * 52)

if FAILED:
    print("\nBa'zi testlar yiqildi — yuqoridagi farqlarni tekshiring.\n")
    sys.exit(1)

print("\nBarcha testlar muvaffaqiyatli o'tdi ✅\n")
