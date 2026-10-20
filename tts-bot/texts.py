"""texts.py — bot interfeysidagi barcha matnlar (o'zbekcha).

Barcha foydalanuvchi ko'radigan matnlar shu faylda.

Dizayn tamoyillari:
  • Qisqa, aniq, "bir ekran" — hech qanday dev yozuv yo'q
  • Har bir bo'limda bitta harakat (tugma) — foydalanuvchi nima qilishini biladi
  • Emoji + bo'lim ajratgichlari (━) — "professional" ko'rinish
"""

# Bo'lim ajratgichi
SEP = "━━━━━━━━━━━━━━━━━━━━━━"

# =============================================
# BOSH MENYU
# =============================================

MAIN_TITLE = (
    "🎙 <b>AI Ovoz Bot</b>\n"
    "<i>Matnni tabiiy, ifodali ovozga aylantiraman</i>\n"
    + SEP + "\n"
)

MAIN_SUBTITLE = (
    "Quyidagilardan birini tanlang yoki shunchaki yozing — "
    "men o'zim tushunaman."
)

MAIN_MENU_BUTTONS = [
    ("🎙 Matn → Ovoz", "menu:tts"),
    ("🎤 Ovoz → Matn", "menu:stt"),
    ("👴 Keksa effekti", "menu:grandpa"),
    ("🎭 Senariy", "menu:script"),
    ("🗣 Ovoz katalogi", "menu:voices"),
    ("📚 Tarix", "menu:history"),
    ("⚙️ Sozlamalar", "menu:settings"),
    ("📊 Statistika", "menu:stats"),
    ("❓ Yordam", "menu:help"),
    ("🧠 AI rejimi", "menu:ai"),
]

BTN_HOME = "🏠 Bosh menyu"
BTN_CLOSE = "✖️ Yopish"
BTN_BACK = "⬅️ Orqaga"

# --- Pastki (reply) menyu tugmalari ---
BOTTOM_TTS = "🎙 Matn→Ovoz"
BOTTOM_STT = "🎤 Ovoz→Matn"
BOTTOM_GRANDPA = "👴 Keksa"
BOTTOM_SCRIPT = "🎭 Senariy"
BOTTOM_SETTINGS = "⚙️ Sozlamalar"
BOTTOM_HELP = "❓ Yordam"

BOTTOM_PLACEHOLDER = "✍️ Matn yozing yoki 🎤 tugmasini bosing…"

# =============================================
# REJIMLAR (menyu orqali tanlangan)
# =============================================

MODE_TTS = (
    "🎙 <b>Matn → Ovoz rejimi</b>\n"
    + SEP + "\n"
    "Endi yozing — men har bir xabaringizni <b>ovozli xabar</b>ga aylantiraman.\n\n"
    "💡 Ixtiyoriy: <code>Grandpa ovozida aylantir</code> deb yozsangiz, keksa ovozi chiqadi."
)

MODE_STT = (
    "🎤 <b>Ovoz → Matn rejimi</b>\n"
    + SEP + "\n"
    "Endi mikrofon tugmasini bosing va gapiring — men yozib beraman.\n\n"
    "💡 Maksimal uzunlik: <b>5 daqiqa</b>"
)

MODE_GRANDPA = (
    "👴 <b>Keksa effekti rejimi</b>\n"
    + SEP + "\n"
    "Matnni yozing — uni keksa, donish ovozida o'qib beraman.\n\n"
    "💡 Masalan: <i>Bugun haqiqa yaxshi kun bo'ldi</i>"
)

MODE_SCRIPT = (
    "🎭 <b>Senariy rejimi</b>\n"
    + SEP + "\n"
    "Dialog yozing — har bir qahramonni <b>alohida ovozda</b> o'qib beraman.\n\n"
    "💡 Format: <code>Ism: replika</code>\n"
    "<code>Ali: Salom, qalqon qayerda?\n</code>"
    "<code>Vali: Bu yerda, tezroq kel!</code>"
)

MODE_AI = (
    "🧠 <b>AI rejimi</b>\n"
    + SEP + "\n"
    "Endi bemalol yozing — <b>Gemini</b> niyatingizni aniqlab, o'zi kerakli qismni bajaradi:\n"
    "• matnni ovozga aylantiradi\n"
    "• suhbat qiladi\n"
    "• keksa ovoziga o'tkazadi\n"
    "• senariyni qahramonlarga bo'ladi\n\n"
    "💡 Masalan: <i>Salom, bugun haqiqa yaxshi kun</i>"
)

MODE_ON = "✅ Rejim: <b>{mode}</b>"
MODE_OFF = "🔄 Rejim: <b>AI avtomatik</b>"

# =============================================
# OVOZ KATALOGI
# =============================================

VOICE_CATALOG_HEADER = (
    "🗣 <b>Ovoz katalogi</b>\n"
    + SEP + "\n"
    "Ovozni tanlang — <b>namuna</b> yuboraman va u sizning ovozingiz bo'lib qoladi."
)

VOICE_SELECTED = (
    "✅ <b>{name}</b> tanlandi.\n"
    "<i>{desc}</i>\n\n"
    "Endi matn yozing — bu ovoz bilan o'qib beraman."
)

VOICE_PREVIEW_ERROR = "❌ Namana yaratib bo'lmadi. Boshqa ovozni urinib ko'ring."

VOICE_ALREADY = "ℹ️ Bu ovoz allaqachon tanlangan."

# =============================================
# SOZLAMALAR
# =============================================

SETTINGS_HEADER = (
    "⚙️ <b>Sozlamalar</b>\n"
    + SEP + "\n"
    "O'zgartirmoqchi bo'lgan bo'limni tanlang:"
)

SETTINGS_SUMMARY = (
    "🌍 <b>Til</b> · {lang}\n"
    "🗣 <b>Ovoz</b> · {voice}\n"
    "⚡ <b>Tezlik</b> · {speed}"
)

CHOOSE_LANG = "🌍 <b>Tilni tanlang</b>"
CHOOSE_VOICE = "🗣 <b>Ovozni tanlang</b>"
CHOOSE_SPEED = "⚡ <b>Tezlikni tanlang</b>"

BTN_LANG_UZ = "🇺🇿 O'zbek"
BTN_LANG_RU = "🇷🇺 Rus"
BTN_LANG_EN = "🇬🇧 Ingliz"

BTN_VOICE_MALE = "🧔 Erkak"
BTN_VOICE_FEMALE = "👩 Ayol"

BTN_SPEED_SLOW = "🐢 Sekin"
BTN_SPEED_NORMAL = "🚶 Normal"
BTN_SPEED_FAST = "⚡ Tez"

BTN_REFRESH = "🔄 Yangilash"

SETTINGS_LANG_SET = "✅ Til: <b>{lang}</b>"
SETTINGS_VOICE_SET = "✅ Ovoz: <b>{voice}</b>"
SETTINGS_SPEED_SET = "✅ Tezlik: <b>{speed}</b>"

# =============================================
# TARIX
# =============================================

HISTORY_HEADER = (
    "📚 <b>Tarix</b> · so'nggi {count} ta\n"
    + SEP + "\n"
    "Matnni bosing — uni qayta ovozga aylantiraman."
)

HISTORY_EMPTY = (
    "📚 <b>Tarix bo'sh</b>\n"
    + SEP + "\n"
    "Hali matn yubormadingiz. Yozing — men ovozga aylantiraman! 🎙"
)

HISTORY_CLEARED = "🧹 Tarix tozalandi."

# =============================================
# STATISTIKA
# =============================================

STATS_HEADER = (
    "📊 <b>Sizning statistikasi</b>\n"
    + SEP + "\n"
)

STATS_CARD = (
    "🔤 <b>Bugungi so'rovlar</b> · {today}\n"
    "📚 <b>Jami so'rovlar</b> · {total}\n"
    "💬 <b>Tarixdagi matnlar</b> · {history}\n"
    "🌍 <b>Til</b> · {lang}\n"
    "🗣 <b>Ovoz</b> · {voice}\n"
    "⚡ <b>Tezlik</b> · {speed}"
)

# =============================================
# YORDAM
# =============================================

HELP_HEADER = (
    "❓ <b>Yordam</b>\n"
    + SEP + "\n"
)

HELP_BODY = (
    "<b>🎙 Matn → Ovoz</b>\n"
    "Matn yozing, men uni tabiiy ovozga aylantiraman.\n"
    "Tillar: 🇺🇿 o'zbek · 🇷🇺 rus · 🇬🇧 ingliz\n\n"
    "<b>🎤 Ovoz → Matn</b>\n"
    "Mikrofon tugmasini bosing va gapiring — matnini yozib beraman.\n\n"
    "<b>👴 Keksa effekti</b>\n"
    "Matnni keksa, donish ovozida o'qib beraman.\n\n"
    "<b>🎭 Senariy</b>\n"
    "Dialog yozing — har bir qahramonga alohida ovoz beraman.\n\n"
    "<b>🧠 AI suhbat</b>\n"
    "Har qanday savolga javob beraman.\n\n"
    + SEP + "\n"
    "<b>Buyruqlar</b>\n"
    "/start · /settings · /history · /reset · /help\n\n"
    "⚠️ Maksimal ovoz xabari: <b>5 daqiqa</b>\n"
    "📄 Fayl yuborish mumkin: .txt · .pdf · .docx (10 MB gacha)"
)

# =============================================
# SALOMLASHUV
# =============================================

GREETING = (
    "👋 <b>Assalomu alaykum!</b>\n"
    + SEP + "\n"
    "Men <b>AI Ovoz Bot</b>man — matnni tabiiy, ifodali ovozga aylantiraman.\n\n"
    "🎙 Matn yozing → men ovoz qilib yuboraman\n"
    "🎤 Yoki mikrofonni bosing → men matn qilib yozaman\n\n"
    "Qanday ishlashimni <b>quyidagi tugmalar</b> orqali ko'ring 👇"
)

RESET_DONE = (
    "🔄 <b>Suhbat tarixi tozalandi</b>\n"
    + SEP + "\n"
    "Yana yozing — men tayyorman! 😊"
)

# =============================================
# XATOLIK VA OGOHLANTIRISHLAR
# =============================================

ERR_EMPTY_TEXT = "⚠️ Matn topilmadi. Iltimos, qayta yozing."
ERR_NO_VOICE = (
    "❌ <b>Ovoz yaratib bo'lmadi</b>\n"
    + SEP + "\n"
    "Server vaqtida javob bermadi yoki yuklama katta. Birozdan so'ng "
    "qayta urinib ko'ring yoki boshqa rejimni tanlang."
)
ERR_TTS_FAILED = "❌ Ovoz yaratishda xatolik yuz berdi. Qayta urinib ko'ring."
ERR_TOO_LONG = "⚠️ Matn juda uzun. Maksimal {max} belgi."
ERR_VOICE_TOO_LONG = (
    "⚠️ Ovoz juda uzun ({duration} s). Maksimal {max} soniya."
)
ERR_SCRIPT_PARSE = (
    "❌ <b>Senariy qahramonlarini topa olmadim</b>\n"
    + SEP + "\n"
    "Formatda yuboring:\n"
    "<code>Ism: replika</code>\n"
    "<code>Ali: Salom!\nVali: Salom!</code>"
)
ERR_SCRIPT_EMPTY = "❌ Senariyda hech qanday qahramon topilmadi."
ERR_DAILY_LIMIT = (
    "🚫 <b>Bugungi bepul limit tugadi</b> ({limit} ta so'rov)\n"
    + SEP + "\n"
    "Ertaga qayta urinib ko'ring. Limiti oshirish uchun admin bilan "
    "bog'laning."
)
ERR_UNKNOWN = "❌ Kutilmagan xatolik: {error}"
ERR_FILE_TOO_BIG = "⚠️ Fayl juda katta ({size} MB). Maksimal {max} MB."
ERR_FILE_TYPE = (
    "❌ Bu fayl turini o'qiy olmayman.\n"
    "Qo'llab-quvvatlanadi: <b>.txt · .pdf · .docx</b>"
)
ERR_FILE_READ = "❌ Faylni o'qib bo'lmadi. Iltimos, boshqa fayl yuboring."
ERR_NOT_ADMIN = "🚫 Bu bo'lim faqat adminlar uchun."

# =============================================
# PROGRESS VA STATUS
# =============================================

STATUS_TTS = "⏳ <b>Ovoz yaratilmoqda…</b>"
STATUS_SCRIPT_PARSE = "📜 <b>Senariy tahlil qilinmoqda…</b>"
STATUS_VOICE_HEARING = "🎤 <b>Ovoz tinglanmoqda…</b>"
STATUS_TRANSCRIBING = "⏳ <b>Matnga aylantirilmoqda…</b>"
STATUS_FILE_READING = "📄 <b>Fayl o'qilmoqda…</b>"
STATUS_CHUNK = "⏳ <b>Ovoz yaratilmoqda</b> · {current}/{total}"
STATUS_GRANDPA = "👴 <b>Keksa effekti qo'llanmoqda…</b>"
STATUS_THINKING = "🧠 <b>Tahlil qilinmoqda…</b>"
STATUS_PREVIEW = "🔊 <b>Namuna tayyorlanmoqda…</b>"

# =============================================
# MUVAFFAQIYAT XABARLARI
# =============================================

TTS_DONE = "🔊 {engine} · {lang} · {chars} belgi"
GRANDPA_DONE = "👴 Keksa effekti · {chars} belgi"
SCRIPT_FOUND = "🎭 <b>{count} ta qahramon topildi</b>\n{summary}"
SCRIPT_DONE = (
    "✅ <b>Tayyor!</b> {count} ta ovozli xabar yuborildi 🎉"
)
TRANSCRIPT = "🗣️ «{text}»\n\n🧠 Davom etilmoqda…"

# =============================================
# INLINE REJIM
# =============================================

INLINE_NO_QUERY = "✏️ Matn yozing — ovozga aylantirib beraman."

# =============================================
# ADMIN PANEL
# =============================================

ADMIN_HEADER = "👑 <b>Admin Panel</b>\n" + SEP + "\n"
ADMIN_STATS = (
    "👥 Foydalanuvchilar: <b>{users}</b>\n"
    "📊 Bugungi so'rovlar: <b>{today}</b>\n"
    "📈 Jami so'rovlar: <b>{total}</b>"
)
ADMIN_BROADCAST_PROMPT = (
    "📢 <b>Broadcast rejimi</b>\n"
    + SEP + "\n"
    "Yubormoqchi bo'lgan xabaringizni yozing.\n"
    "Bekor qilish uchun /cancel bosing."
)
ADMIN_BROADCAST_START = "📤 Broadcast boshlandi: {count} ta foydalanuvchi…"
ADMIN_BROADCAST_DONE = "✅ Broadcast tugadi. Yuborildi: {sent}/{total}"
ADMIN_CANCELLED = "❌ Broadcast bekor qilindi."

# =============================================
# BOSHQA
# =============================================

NOT_UNDERSTOOD = (
    "😊 Men hozircha <b>matn</b>, <b>ovoz</b> va <b>fayl</b>lar bilan ishlayman.\n"
    "Matn yozing yoki mikrofon tugmasini bosib ovoz yuboring!"
)

AI_FALLBACK = (
    "😔 Kechirasiz, AI bilan aloqa vaqtincha uzildi.\n"
    "Birozdan keyin qayta yozing yoki <b>Matn → Ovoz</b> rejimini tanlang."
)
