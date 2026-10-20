# 🎙️ AI Ovoz Bot (@mp3speak_bot)

O'zbek tilidagi AI yordamchi Telegram bot: matnni ovozga aylantirish, ovozni matnga aylantirish (STT), senariy bo'yicha qahramonlarga alohida ovoz berish, Grandpa effekti va AI suhbat.

## ✨ Imkoniyatlar

- 🎛 **Professional UI** — bosh menyu, pastki doimiy tugmalar, ichki menyular
- 🗣 **Ovoz katalogi (14 ta ovoz)** — har birini namuna bilan eshitib tanlang
- 📊 **Statistika** — bugungi/jami so'rovlar, tarix hajmi
- 📚 **Tarix** — har bir eski matnni bir tushish bilan qayta ovozga aylantiring
- 🧠 **Rejimlar** — Matn→Ovoz, Ovoz→Matn, Keksa, Senariy yoki AI avtomatik
- 🇺🇿 **Fish Audio + o'zbekcha** — o'zbek matn avval **fonetik ko'rinishga** o'tkaziladi
  (lotin → kirill, raqamlar → so'z), shuning uchun Fish ham o'zbekchani to'g'ri talaffuz qiladi
- ⏱ **Fish Audio timeout'lar** — muddat oshirilgan, qayta urinish va zaxira model qo'shilgan
- 🗣 **TTS (matn → ovoz)** — Edge TTS (bepul) asosiy dvigatel; Kokoro, Fish Audio fallback
- 🎤 **STT (ovoz → matn)** — Gemini bilan o'zbekcha transkripsiya
- 🎭 **Senariy** — qahramonlarni ajratib, har biriga alohida ovoz
- 👴 **Grandpa effekti** — FFmpeg bilan keksa odam ovozi
- 💬 **AI suhbat** — Gemini 3.5 Flash Lite
- ⚙️ **Sozlamalar** — til (uz/ru/en), ovoz (erkak/ayol), tezlik (sekin/normal/tez)
- 📄 **Fayl o'qish** — .txt, .pdf, .docx (10 MB gacha)
- 🚀 **Inline rejimi** — har qanday chatda `@mp3speak_bot matn` → ovoz xabari
- 📈 **Kunlik limit** — `DAILY_LIMIT` (.env da sozlanadi, 0 = cheklovsiz)
- 👑 **Admin panel** (`/admin`) — statistika va broadcast (faqat `ADMIN_IDS`)

## 🛠 O'rnatish

```bash
pip install -r requirements.txt
```

Kerakli tashqi dastur: **FFmpeg** (loyihada `imageio-ffmpeg` bilan keladi, alohida o'rnatish shart emas).

## ⚙️ .env sozlash

`.env.example` faylini nusxalab `.env` qiling va qiymatlarni to'ldiring:

| O'zgaruvchi | Tavsif |
|---|---|
| `BOT_TOKEN` | Telegram bot tokeni (@BotFather dan) |
| `MIYYA_API_KEY` | Gemini API kaliti (chat/STT/intent) |
| `OPENROUTER_API_KEY` | OpenRouter kaliti (Fish Audio fallback) |
| `OPENROUTER_THINKING_KEY` | matnni tayyorlash uchun (ixtiyoriy) |
| `ADMIN_IDS` | Admin ID lari, vergul bilan (masalan `123,456`) |
| `DAILY_LIMIT` | Kunlik so'rovlar (0 = cheklovsiz) |
| `KOKORO_API_URL` | Kokoro TTS endpointi (fallback) |
| `KOKORO_ENABLED` | `true`/`false` — Kokoro ishlatilsinmi |
| `KOKORO_TIMEOUT` | Kokoro kutish vaqti (soniya, default 180) |
| `FISH_TTS_MODELS` | Fish modellari ro'yxati (vergul bilan). Birinchisi ishlamasa keyingisiga o'tiladi |
| `FISH_TIMEOUT` | Bitta Fish so'roviga vaqt (soniya, default 300) — "vaqt tugaydi" xatosining oldini oladi |
| `FISH_CONNECT_TIMEOUT` | Serverga ulanish vaqti (soniya, default 30) |
| `FISH_RETRIES` | 429/5xx/timeout uchun qayta urinishlar (default 2) |
| `FISH_BUDGET` | Umumiy vaqt byudjeti (soniya, default 600) |
| `FISH_CHUNK_CHARS` | Bitta so'rovdagi maksimal belgi (default 900) — kichik bo'lak = kamroq timeout + yaxshiroq talaffuz |
| `FISH_UZ_MODE` | `cyrillic` (default) / `latin` / `off` — o'zbek matnni tayyorlash usuli |
| `FISH_LATENCY` | `high` (default) / `normal` / `low` — Fish sifat/tezlik rejimi |

> ⚠️ `.env` hech qachon Git'ga commit qilinmaydi (`.gitignore` ichida).

## ▶️ Ishga tushirish

```bash
python bot.py
```

Baza (`bot.db`) birinchi ishga tushirishda avtomatik yaratiladi.

## 📦 Loyiha tuzilishi

| Fayl | Vazifasi |
|---|---|
| `bot.py` | Asosiy bot: handlerlar, TTS/STT, AI oqimi, menyular |
| `database.py` | SQLite (aiosqlite): sozlamalar, tarix, limitlar |
| `texts.py` | Barcha UI matnlari (o'zbekcha) |
| `uzbek_phonetics.py` | O'zbek matnni Fish Audio uchun fonetik ko'rinishga o'tkazadi (lotin → kirill, raqam → so'z) |
| `requirements.txt` | Python kutubxonalari |

## 🎛 Bot interfeysi

```
┌─────────────────────┬─────────────────────┐
│  🎙 Matn → Ovoz     │  🎤 Ovoz → Matn     │
│  👴 Keksa effekti    │  🎭 Senariy         │
│  🗣 Ovoz katalogi    │  📚 Tarix           │
│  ⚙️ Sozlamalar       │  📊 Statistika      │
│  ❓ Yordam           │  🧠 AI rejimi       │
│  🏠 Bosh menyu       │  ✖️ Yopish          │
└─────────────────────┴─────────────────────┘
```

Pastda esa **doimiy tugmalar** (reply keyboard):

```
🎙 Matn→Ovoz   🎤 Ovoz→Matn
👴 Keksa       🎭 Senariy
⚙️ Sozlamalar  ❓ Yordam
```

**Rejimlar.** Menyudan rejim tanlanganda AI niyatni aniqlash o'tkazib yuboriladi —
natijada har doim bir xil, kutilgan natija chiqadi:

| Rejim | Natija |
|---|---|
| 🧠 AI rejimi | Gemini niyatni aniqlaydi (barchasi avtomatik) |
| 🎙 Matn → Ovoz | Har doim TTS |
| 👴 Keksa effekti | Har doim keksa ovozi |
| 🎭 Senariy | Har doim qahramonlarga alohida ovoz |

**Ovoz katalogi.** 14 ta ovoz (Kokoro 12 ta + Fish Audio 2 ta). Tugma bosilsa
namuna ovoz yuboriladi va u sizning ovozingiz bo'lib qoladi (bazada saqlanadi).
Keyingi matnlar aynan shu ovoz bilan o'qiladi.

**Sozlamalar.** Joriy tanlov `✅` belgisi bilan ko'rsatiladi. Til/ovoz/tezlik
o'zgartirilgach, katalogdagi aniq ovoz tozalanadi (moslik uchun).

**Tarix.** Har bir eski matn — tugma. Bosilsa, matn qayta ovozga aylantiriladi.

## 🗣 Fish Audio va o'zbek talaffuzi

Fish Audio S2 modeli asosan ingliz/xitoy tilida o'qitilgan, shuning uchun
o'zbekcha lotin yozuvini to'g'ridan-to'g'ri yuborsa talaffuz buziladi:

| Lotin yozuv | Fish Audio'siz | Tuzatilgan (kirill) |
|---|---|---|
| `O'zbekiston` | `озбекистон` ❌ | `Узбекистон` ✅ |
| `qalqon` | `калкон` ❌ (`q`→`k`) | `калкон` ✅ |
| `xabar` | `ксабар` ❌ (`x`→`ks`) | `хабар` ✅ |
| `to'g'ri` | `тугри` ❌ | `тугри` ✅ |
| `ma'lumot` | `ма'лумот` ❌ | `маълумот` ✅ |
| `2025` | `2025` ❌ | `икки минг йигирма беш` ✅ |

`uzbek_phonetics.py` barcha o'zbek harflarini **standart rus kirillchasiga**
joylaydi (`o'`→`у`, `g'`→`г`, `q`→`к`, `x`→`х`), chunki Fish Audio'ning
kirill qo'llab-quvvatlashi lotin yozuvidan ancha kuchli. Bu sof (deterministik)
amal — tashqi API chaqirilmaydi, tez va bepul.

Boshqalar:
- `FISH_UZ_MODE=off` — o'zgartirishni butunlay o'chirish
- `FISH_UZ_MODE=latin` — faqat raqamlar so'zga aylanadi, matn o'zgarishsiz
- `FISH_LATENCY=normal` — sekin serverlarda tezroq javob (sifat biroz past)

## ⏱ Timeout muammosi

Fish Audio so'rovi "vaqt tugaydi" xatosi berganida bot endi:

1. **Bo'laklarga ajratadi** — `FISH_CHUNK_CHARS` (default 900) belgidan oshmasligi uchun
   matn qisqa so'rovlarga bo'linadi. Kichik so'rov tez tugaydi.
2. **Ko'proq vaqt beradi** — `FISH_TIMEOUT` (default 300s, avval 180s).
3. **Qayta urinadi** — 429/5xx/timeout da `FISH_RETRIES` (default 3) marta,
   `2^urinish` sekund kutib.
4. **Zaxira modelga o'tadi** — `FISH_TTS_MODELS` ro'yxatidagi keyingi modelga.
5. **Variantlarni sinaydi** — avval to'liq so'rov (options + voice + `high` latency),
   keyin soddalashtirilgan so'rovlar.

Bo'laklar keyin FFmpeg orqali bitta MP3 ga birlashtiriladi (`concat_audio`).

## 🔐 Xavfsizlik

- Barcha kalitlar faqat `.env` da
- SQL so'rovlari parametrlangan (SQL injection yo'q)
- Vaqtinchalik fayllar `tmp/` da uuid bilan, `finally` da o'chiriladi
- Throttling middleware (1.5s) + TTS Semaphore (5 parallel) — serverga yuk kam
