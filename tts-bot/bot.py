"""
Telegram AI Ovoz Bot — AI-first oqim (Kokoro TTS bilan)

OQIM:
  /start  -> AI salomlashuv -> AI suhbat rejimi (ai_chat)
  Foydalanuvchi istalgan matn YOKI ovozli xabar yuboradi:
    1. Gemini niyatni (intent) aniqlaydi: tts | grandpa | script | chat
    2. tts      -> matnni ovozga aylantiradi
    3. voice    -> Gemini STT orqali matnga o'girib, uni xuddi shu oqimga beradi
    4. grandpa  -> TTS + FFmpeg 'Grandpa' effekti
    5. script   -> Gemini qahramonlarni ajratadi -> har biriga alohida ovoz
    6. aks holda -> o'zbekcha suhbat (tarix bilan)

OVOZ DVIGATELLARI (tartib):
  1. Kokoro TTS — ASOSIY dvigatel (OpenAI-compatible API, barcha tillar)
     Endpoint: KOKORO_API_URL (default: http://localhost:8880/v1/audio/speech)
  2. Fish Audio (OpenRouter) — fallback (Kokoro ishlamayotganda)
  3. gTTS — oxirgi fallback (faqat gTTS qo'llab-quvvatlagan tillar: en, ru, tr, ...)
     Eslatma: gTTS 'uz' (o'zbek) tilini QO'LLAB-QUVVATLAMAYDI

BARCHA KALITLAR FAQAT .env FAYLDAN OLINADI.
"""

import os
import re
import json
import io
import sys
import uuid
import asyncio
import logging
import base64
import tempfile
import time
from pathlib import Path

import edge_tts

from dotenv import load_dotenv
import imageio_ffmpeg
import aiohttp

try:
    from gtts import gTTS

    try:
        from gtts.lang import tts_langs as _tts_langs
        GTTS_LANGS = set(_tts_langs().keys())
    except Exception:  # pragma: no cover
        GTTS_LANGS = {"en", "ru", "tr", "de", "fr", "es", "it", "pt", "ja", "ko", "zh", "ar", "hi", "id", "uk"}
    GTTS_AVAILABLE = True
except ImportError:  # gTTS o'rnatilmagan bo'lsa — bot Fish Audio bilan ishlaveradi
    gTTS = None
    GTTS_LANGS = set()
    GTTS_AVAILABLE = False

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, BufferedInputFile, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineQuery, InlineQueryResultVoice, InlineQueryResultArticle,
    InputTextMessageContent,
)
from aiogram.enums import ParseMode, ChatAction
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

import texts as T
import database as db
from uzbek_phonetics import prepare_for_fish

# --- Edge TTS 403 fix (faqat eski versiyalar uchun) ---
# edge-tts 7.3.0+ da v2 token qo'llab-quvvatlanadi — native URL to'g'ri ishlaydi.
# Faqat 7.2.x da Microsoft endpoint yopilgani uchun yangi hostga o'tkazamiz.
try:
    import edge_tts as _edge_ver
    _ver_parts = tuple(
        int(x) for x in getattr(_edge_ver, "__version__", "0").split(".")[:2]
    )
    if _ver_parts < (7, 3):
        from edge_tts.constants import TRUSTED_CLIENT_TOKEN
        import edge_tts.communicate as _edge_cm
        _edge_cm.WSS_URL = (
            "wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1"
            f"?Ocp-Apim-Subscription-Key={TRUSTED_CLIENT_TOKEN}"
        )
except Exception:
    pass

load_dotenv()

# Windows konsolida emoji chiqmasligi uchun (cp1251 xatosi)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# =============================================
# KALITLAR (faqat .env dan!)
# =============================================
BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_THINKING_KEY = os.getenv("OPENROUTER_THINKING_KEY")
GEMINI_API_KEY = os.getenv("MIYYA_API_KEY")  # Gemini (Google AI Studio)

# --- Fish Audio TTS (OpenRouter) — fallback sifatida saqlanadi ---
TTS_API_URL = "https://openrouter.ai/api/v1/audio/speech"
TTS_MODEL = "fish-audio/s2.1-pro-free:free"

# Fish Audio sozlamalari (.env dan o'qiladi)
# Modellar ro'yxati: birinchisi ishlamasa keyingisiga avtomatik o'tiladi
FISH_TTS_MODELS = [
    m.strip()
    for m in os.getenv(
        "FISH_TTS_MODELS",
        # free model kunlik limiti tugishi mumkin — to'lovli model birinchi
        f"fish-audio/s2.1-pro,{TTS_MODEL}",
    ).split(",")
    if m.strip()
] or [TTS_MODEL]
FISH_TIMEOUT = int(os.getenv("FISH_TIMEOUT", "300"))           # bitta so'rovga umumiy vaqt (s)
FISH_CONNECT_TIMEOUT = int(os.getenv("FISH_CONNECT_TIMEOUT", "30"))  # ulanish vaqti (s)
FISH_RETRIES = int(os.getenv("FISH_RETRIES", "2"))            # 429/5xx/timeout uchun urinishlar
FISH_BUDGET = int(os.getenv("FISH_BUDGET", "600"))            # umumiy vaqt byudjeti (s)
FISH_CHUNK_CHARS = int(os.getenv("FISH_CHUNK_CHARS", "900"))  # bitta so'rovdagi maksimal belgi
FISH_UZ_MODE = os.getenv("FISH_UZ_MODE", "cyrillic").strip().lower()  # cyrillic|latin|off
FISH_LATENCY = os.getenv("FISH_LATENCY", "high").strip().lower()      # low|normal|high

# --- Kokoro TTS (asosiy TTS dvigateli) ---
KOKORO_API_URL = os.getenv("KOKORO_API_URL", "https://strive33-kokoro-tts-fastapi.hf.space/tts")
KOKORO_DEFAULT_VOICE = os.getenv("KOKORO_DEFAULT_VOICE", "af_heart")
KOKORO_SPEED = float(os.getenv("KOKORO_SPEED", "1.0"))
KOKORO_ENABLED = os.getenv("KOKORO_ENABLED", "true").lower() in ("true", "1", "yes")
KOKORO_TIMEOUT = int(os.getenv("KOKORO_TIMEOUT", "180"))   # sekin serverlar uchun ko'proq vaqt

# --- Thinking model: matnni ovozli nutqqa tayyorlash ---
THINKING_API_URL = "https://openrouter.ai/api/v1/chat/completions"
# Eski model "nvidia/nemotron-3-super-120b-a12b:free" — OpenRouter'dagi
# KUNLIK free limit tugagani uchun 429 beradi. Quyidagilar ishlaydi:
THINKING_MODEL = os.getenv("THINKING_MODEL", "meta-llama/llama-3.3-70b-instruct")

# --- AI TTS dvigatellari (realistik ovoz) ---
# Gemini 2.5 Flash TTS — AI Studio bepul tierida, o'zbek tilini qo'llab-quvvatlaydi
GEMINI_TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
GEMINI_TTS_ENABLED = os.getenv("GEMINI_TTS_ENABLED", "true").lower() in ("true", "1", "yes")
GEMINI_TTS_VOICES = {
    "🔮 Zephyr": "Zephyr",
    "🔊 Puck": "Puck",
    "🌊 Charon": "Charon",
    "💫 Kore": "Kore",
    "🎭 Fenrir": "Fenrir",
    "🌸 Aoede": "Aoede",
    "🎵 Leda": "Leda",
    "🗣 Orus": "Orus",
}

# OpenAI TTS — juda realistik, lekin to'lovli
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
# Realistik AI ovozi (Gemini/OpenAI) Edge'dan oldin ishlatilsinmi?
AI_TTS_FIRST = os.getenv("AI_TTS_FIRST", "true").lower() in ("true", "1", "yes")
OPENAI_TTS_VOICES = {
    "🧔 Alloy": "alloy",
    "🌊 Nova": "nova",
    "✨ Shimmer": "shimmer",
    "🗿 Onyx": "onyx",
    "🎭 Fable": "fable",
    "🎀 Coral": "coral",
    "📖 Verse": "verse",
    "🌲 Ash": "ash",
    "🎙 Echo": "echo",
    "🍃 Sage": "sage",
    "🎵 Ballad": "ballad",
}

# Noto'g'ri kalit (401) keyin davomida vaqt yo'qotmaslik uchun
_broken_keys: dict[str, float] = {}


def _key_broken(name: str, ttl: float = 900) -> bool:
    """Kalit ishlamayotganini vaqtincha eslab qolamiz (15 daqiqa)."""
    return time.monotonic() < _broken_keys.get(name, 0)


def _mark_broken(name: str) -> None:
    _broken_keys[name] = time.monotonic() + 900
    logger.warning(f"Kalit '{name}' ishlamadi — 15 daqiqa uchun o'chirildi")


# --- Gemini / OpenAI / LLM zanjiri (OpenRouter asosiy) ---
# OpenRouter (ishlaydi) -> Gemini (kalit to'g'ri bo'lsa) -> kalit so'z fallback
LLM_MODELS = [
    m.strip()
    for m in os.getenv(
        "LLM_MODELS",
        "meta-llama/llama-3.3-70b-instruct,"
        "google/gemini-2.5-flash-lite,"
        "openai/gpt-4o-mini",
    ).split(",")
    if m.strip()
] or [THINKING_MODEL]
LLM_API_KEY = OPENROUTER_API_KEY or OPENROUTER_THINKING_KEY

# --- Gemini (Google AI Studio) ---
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_MODEL = "gemini-3.5-flash-lite"

# --- Cheklovlar ---
MAX_VOICE_SECONDS = 300     # 5 daqiqa
TG_MSG_LIMIT = 4000         # Telegram xabar chegarasi (4096) dan xavfsiz
MAX_SCRIPT_CHARS = 1200     # bitta qahramon audio bo'lakchasi
MAX_SCRIPT_CHARACTERS = 10  # senariyda ishlanadigan qahramonlar soni
MAX_TEXT_CHARS = 15000      # TTS uchun maksimal matn uzunligi
MAX_CHUNK_CHARS = 3000      # bitta ovoz bo'lakchasi uchun maksimal belgi
DAILY_LIMIT = int(os.getenv("DAILY_LIMIT", "50"))  # kunlik so'rovlar (0 = cheklovsiz)
FILE_SIZE_LIMIT_MB = 10     # fayl hajmi limiti (MB)
ADMIN_IDS = [
    int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()
]

# --- Edge TTS (asosiy TTS dvigateli — bepul, o'zbekcha qo'llab-quvvatlaydi) ---
EDGE_TTS_VOICES = {
    "uz": {
        "male": "uz-UZ-SardorNeural",
        "female": "uz-UZ-MadinaNeural",
    },
    "ru": {
        "male": "ru-RU-DmitryNeural",
        "female": "ru-RU-SvetlanaNeural",
    },
    "en": {
        "male": "en-US-GuyNeural",
        "female": "en-US-JennyNeural",
    },
}

EDGE_TTS_RATES = {
    "slow": "-20%",
    "normal": "+0%",
    "fast": "+25%",
}

# Fish Audio prosody tezligi (1.0 = normal)
FISH_SPEEDS = {
    "slow": 0.9,
    "normal": 1.0,
    "fast": 1.15,
}

LANG_LABELS = {"uz": "🇺🇿 O'zbek", "ru": "🇷🇺 Rus", "en": "🇬🇧 Ingliz"}
GENDER_LABELS_UI = {"male": "— Erkak", "female": "— Ayol"}
SPEED_LABELS = {"slow": "— Sekin", "normal": "— Normal", "fast": "— Tez"}

# --- Logger ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Foydalanuvchi ma'lumotlari (in-memory) ---
user_data: dict[int, dict] = {}

# =============================================
# FSM — juda oddiy: asosiy AI suhbat rejimi
# =============================================


class Flow(StatesGroup):
    ai_chat = State()     # AI suhbat rejimi (asosiy holat)
    broadcast = State()   # Admin: broadcast matni kutilmoqda


# =============================================
# OVOZLAR KATALOGI (qahramonlar va ovoz so'rovlari uchun)
# =============================================

# --- Kokoro TTS ovozlari (asosiy) ---
KOKORO_MALE_VOICES = {
    "— Erkak (Rasmiy)": "am_michael",
    "— Erkak (Tabiiy)": "am_liam",
    "— Erkak (Chuqur)": "am_adam",
    "— Erkak (Do'stona)": "am_eric",
}

KOKORO_FEMALE_VOICES = {
    "— Ayol (Tabiiy)": "af_heart",
    "— Ayol (Expressiv)": "af_bella",
    "— Ayol (Sokin)": "af_nicole",
    "— Ayol (Suhbatdosh)": "af_sarah",
}

KOKORO_CHILD_VOICES = {
    "— Bola (Yosh)": "am_puck",
    "— Bola (Ilmom)": "af_nova",
}

KOKORO_GRANDPA_VOICES = {
    "— Keksa (Chuqur)": "am_echo",
    "— Keksa (Barqaror)": "am_fenrir",
    "— Keksa (Hikoyachi)": "bm_george",
}

KOKORO_GENDER_POOLS = {
    "male": KOKORO_MALE_VOICES,
    "female": KOKORO_FEMALE_VOICES,
    "child": KOKORO_CHILD_VOICES,
}

KOKORO_DEFAULT = KOKORO_DEFAULT_VOICE  # af_heart

# --- Fish Audio ovozlari (fallback) ---
UZBEK_VOICES = {
    "— Erkak (Rasmiy)": "44ad146afad04e4e99a7b98b8f97106f",
    "— Erkak (Tabiiy)": "fef226d2978a42d5b542e7577134f7b2",
}

FEMALE_VOICES = {
    "— Sarah (Yosh, jonli)": "933563129e564b19a115bedd57b7406a",
    "— Laura (Ishonchli)": "e3cd384158934cc9a01029cd7d278634",
    "— Selene (Sokin, meditativ)": "b347db033a6549378b48d00acb0d06cd",
    "— Hannah (Suhbatdosh)": "412a7bebb63345b6becf50f9da63ed5b",
}

MALE_VOICES = {
    "— Ethan (Tushuntiruvchi)": "2ce3de29febb43d7a4a85a63085e1da1",
    "— Adrian (Barqaror)": "7d44c98f619c4e98823a84ed60122f9f",
}

CHILD_VOICES = {
    "— Bolacha (Neutal)": "4e407b98cb034f74b3863ec33c567c83",
    "— Kichkina bola": "051eccd6d8894155a0c544b8e5c0fd72",
    "— O'g'il bola": "501f126749464eef92d30fa913da1e8e",
    "— Yosh bola (Playful)": "c0d6e010f2bb4198b98b78fb796e1b36",
}

TREND_VOICES = {
    "— Grandpa Spencer (Trend)": "245aac5cae7640d88a0e81da89c1e0f3",
    "— Grandpa (Hikoyachi)": "b0f79e4bac084142a2ca8266bd959ae5",
    "— Grandpa (Faktlar, PSA)": "697a707402bf47e9940b95a5f85fbe94",
}

GENDER_POOLS = {
    "male": MALE_VOICES,
    "female": FEMALE_VOICES,
    "child": CHILD_VOICES,
}

DEFAULT_VOICE = UZBEK_VOICES["— Erkak (Rasmiy)"]  # Fish Audio fallback ovozi

GENDER_LABELS = {"male": "erkak", "female": "ayol", "child": "bola"}


def voice_for_gender(gender: str, index: int = 0) -> tuple[str, str]:
    """Qahramon jinsiga qarab ovoz tanlaydi.
    Kokoro ishlasa — Kokoro ovozi, aks holda Fish Audio ovozi."""
    if KOKORO_ENABLED:
        pool = list(KOKORO_GENDER_POOLS.get(gender, KOKORO_MALE_VOICES).items())
        name, voice_id = pool[index % len(pool)]
        return voice_id, name
    pool = list(GENDER_POOLS.get(gender, UZBEK_VOICES).items())
    name, voice_id = pool[index % len(pool)]
    return voice_id, name


def fish_voice_for_gender(gender: str, index: int = 0) -> str:
    """Jinsga mos **Fish Audio** ovoz ID (Kokoro ID'si Fish'da ishlamaydi)."""
    pool = list(GENDER_POOLS.get(gender, UZBEK_VOICES).items())
    name, voice_id = pool[index % len(pool)]
    return voice_id


def voice_for_hint(hint: str) -> str:
    """Foydalanuvchi ovoz so'rovi ('male', 'female', ...) -> voice_id."""
    h = (hint or "default").strip().lower()

    if KOKORO_ENABLED:
        if h in ("male", "erkak"):
            return list(KOKORO_MALE_VOICES.values())[0]
        if h in ("female", "ayol", "qiz"):
            return list(KOKORO_FEMALE_VOICES.values())[0]
        if h in ("child", "bola", "bolacha"):
            return list(KOKORO_CHILD_VOICES.values())[0]
        if h in ("grandpa", "keksa", "bobo"):
            return list(KOKORO_GRANDPA_VOICES.values())[0]
        return KOKORO_DEFAULT

    if h in ("male", "erkak"):
        return list(MALE_VOICES.values())[0]
    if h in ("female", "ayol", "qiz"):
        return list(FEMALE_VOICES.values())[0]
    if h in ("child", "bola", "bolacha"):
        return list(CHILD_VOICES.values())[0]
    if h in ("grandpa", "keksa", "bobo"):
        return list(TREND_VOICES.values())[0]
    return DEFAULT_VOICE


# =============================================
# YORDAMCHI FUNKSIYALAR
# =============================================


def clip(text: str, limit: int = TG_MSG_LIMIT) -> str:
    """Telegram xabarlar uchun xavfsiz uzunlik."""
    text = text or ""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "—"


def clean_ai_text(text: str) -> str:
    """AI matnidan keraksiz markdown belgilarini tozalaydi
    (Telegram oddiy matnda **qalin**, `kod` ni literal ko'rsatadi)."""
    if not text:
        return ""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = text.replace("`", "")
    return text.strip()


def chunk_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Uzun matnni ovoz uchun qulay bo'laklarga bo'ladi.

    Bo'lish tartibi:
      1. Abzats (\n\n) chegarasida
      2. Gap (., !, ?, ...) chegarasida
      3. So'z o'rtasida (so'zni O'RTASIDAN kesma emas!)

    Har bo'lak max_chars belgidan oshmaydi.
    """
    text = (text or "").strip()
    if not text or len(text) <= max_chars:
        return [text] if text else []

    chunks = []

    # 1) Avval abzats bo'yicha bo'lamiz
    paragraphs = re.split(r"\n\s*\n", text)
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # Agar bitta abzats o'zi juda uzun bo'lsa — gap bo'yicha bo'lamiz
        if len(para) > max_chars:
            # Avval joriy bo'lakni saqlaymiz
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_chunk_by_sentences(para, max_chars))
            continue

        # Abzats qo'shsak hajm oshmasa — qo'shamiz
        if current and len(current) + len(para) + 2 > max_chars:
            chunks.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para

    if current:
        chunks.append(current)

    return chunks


def _chunk_by_sentences(text: str, max_chars: int) -> list[str]:
    """Matnni gaplar bo'yicha bo'laklarga bo'ladi (yordamchi funksiya)."""
    # Gap oxirlarini topamiz: . ! ? ... (lekin raqamlardan keyingi nuqtani emas)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks = []
    current = ""

    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue

        # Bitta gap o'zi juda uzun bo'lsa — so'zlar bilan bo'lamiz
        if len(sent) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            words = sent.split()
            for w in words:
                if current and len(current) + len(w) + 1 > max_chars:
                    chunks.append(current)
                    current = w
                else:
                    current = f"{current} {w}" if current else w
            continue

        # Gap qo'shsak hajm oshmasa — qo'shamiz
        if current and len(current) + len(sent) + 1 > max_chars:
            chunks.append(current)
            current = sent
        else:
            current = f"{current} {sent}" if current else sent

    if current:
        chunks.append(current)

    return chunks


async def safe_edit(
    msg: Message | None,
    text: str,
    reply_markup=None,
    parse_mode=None,
) -> None:
    """Xabar tahrirlashda xato qaytarmasligi uchun (message is not modified va h.k.)."""
    if msg is None:
        return
    try:
        kwargs = {}
        if reply_markup is not None:
            kwargs["reply_markup"] = reply_markup
        if parse_mode is not None:
            kwargs["parse_mode"] = parse_mode
        await msg.edit_text(text, **kwargs)
    except Exception as e:
        logger.debug(f"edit_text xatosi: {e}")


async def kill(msg: Message | None) -> None:
    if msg is None:
        return
    try:
        await msg.delete()
    except Exception as e:
        logger.debug(f"delete xatosi: {e}")


async def typing(message: Message) -> None:
    try:
        await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    except Exception:
        pass


async def record_voice(message: Message) -> None:
    """Foydalanuvchiga 'ovoz yozilmoqda' ko'rsatadi."""
    try:
        await message.bot.send_chat_action(message.chat.id, ChatAction.RECORD_VOICE)
    except Exception:
        pass


# =============================================
# TTS: Edge TTS (asosiy) + Kokoro + Fish Audio + gTTS
# =============================================


async def edge_tts_speak(
    text: str,
    voice: str | None = None,
    rate: str = "+0%",
    retries: int = 2,
) -> bytes | None:
    """Edge TTS — Microsoft Edge ovoz sintezi (bepul, o'zbekcha qo'llab-quvvatlaydi).

    Qaytaradi: MP3 audio bytes.
    Ulanish uzilsa `retries` marta qayta urinadi.
    """
    if not voice:
        voice = EDGE_TTS_VOICES.get("uz", {}).get("male", "uz-UZ-SardorNeural")

    for attempt in range(retries + 1):
        try:
            communicate = edge_tts.Communicate(text, voice, rate=rate)
            audio = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio += chunk["data"]
            if audio and len(audio) > 100:
                return audio
            logger.warning(f"Edge TTS juda kichik audio qaytardi ({len(audio)} bayt)")
            return None
        except Exception as e:
            logger.warning(
                f"Edge TTS xatosi (urinish {attempt + 1}/{retries + 1}, "
                f"voice={voice}): {type(e).__name__}: {e}"
            )
            if attempt < retries:
                await asyncio.sleep(1.0 * (attempt + 1))
    return None


async def mp3_to_ogg(mp3_bytes: bytes) -> bytes | None:
    """MP3 faylni OGG (Opus) ga o'giradi — Telegram voice xabari uchun.

    FFmpeg asyncio.create_subprocess_exec orqali chaqiriladi (bloklamaydi).
    """
    uid = uuid.uuid4().hex[:12]
    in_path = TMP_DIR / f"conv_in_{uid}.mp3"
    out_path = TMP_DIR / f"conv_out_{uid}.ogg"

    try:
        in_path.write_bytes(mp3_bytes)
        cmd = [
            FFMPEG_PATH, "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(in_path),
            "-c:a", "libopus",
            "-b:a", "48k",
            "-ar", "16000",
            "-ac", "1",
            str(out_path),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            logger.error(f"MP3->OGG FFmpeg xatosi: {stderr.decode(errors='replace')[:300]}")
            return None
        if not out_path.exists() or out_path.stat().st_size == 0:
            return None
        return out_path.read_bytes()
    except Exception as e:
        logger.error(f"MP3->OGG konversiya xatosi: {e}")
        return None
    finally:
        for p in (in_path, out_path):
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass


def get_edge_voice(lang: str, gender: str) -> str:
    """Til va jinsga qarab Edge TTS ovozini tanlaydi."""
    voices = EDGE_TTS_VOICES.get(lang, EDGE_TTS_VOICES["uz"])
    return voices.get(gender, voices.get("male", "uz-UZ-SardorNeural"))


async def gtts_speak(text: str, lang: str = "en") -> bytes | None:
    """gTTS — sinxron kutubxona, shuning uchun asyncio.to_thread ichida."""
    lang = (lang or "en").strip()
    if not GTTS_AVAILABLE or lang not in GTTS_LANGS:
        # gTTS bu tilni qo'llab-quvvatlamaydi (masalan, 'uz') yoki o'rnatilmagan
        return None

    def _synth() -> bytes:
        buf = io.BytesIO()
        gTTS(text=text, lang=lang, slow=False).write_to_fp(buf)
        return buf.getvalue()

    try:
        data = await asyncio.to_thread(_synth)
        return data if data and len(data) > 100 else None
    except Exception as e:
        logger.error(f"gTTS xatosi ({lang}): {e}")
        return None


async def kokoro_tts(text: str, voice_id: str | None = None) -> bytes | None:
    """Kokoro TTS (HF Space orqali).

    API formati (strive33/Kokoro-TTS-FastAPI Space):
      POST {KOKORO_API_URL}
      {"text": "...", "voice": "af_heart", "speed": 1.0, "output_format": "wav"}
      -> WAV audio bytes
    """
    if not KOKORO_ENABLED:
        return None

    voice = voice_id or KOKORO_DEFAULT_VOICE
    payload = {
        "text": text,
        "voice": voice,
        "speed": KOKORO_SPEED,
        "output_format": "wav",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                KOKORO_API_URL, json=payload,
                timeout=aiohttp.ClientTimeout(total=KOKORO_TIMEOUT),
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"Kokoro TTS xatosi {resp.status}: {error_text[:300]}")
                    # Agar voice noto'g'ri bo'lsa — default voice bilan qayta urinish
                    if voice != KOKORO_DEFAULT_VOICE:
                        payload["voice"] = KOKORO_DEFAULT_VOICE
                        async with session.post(
                            KOKORO_API_URL, json=payload,
                            timeout=aiohttp.ClientTimeout(total=KOKORO_TIMEOUT),
                        ) as retry:
                            if retry.status == 200:
                                data = await retry.read()
                                if len(data) > 100:
                                    return data
                    return None

                data = await resp.read()
                if len(data) > 100:
                    return data
                logger.warning(f"Kokoro TTS juda kichik audio qaytardi ({len(data)} bayt)")
                return None
    except aiohttp.ClientConnectorError:
        logger.warning(f"Kokoro TTS serverga ulanib bo'lmadi: {KOKORO_API_URL}")
        return None
    except asyncio.TimeoutError:
        logger.warning(f"Kokoro TTS timeout ({KOKORO_TIMEOUT}s)")
        return None
    except Exception as e:
        logger.error(f"Kokoro TTS xatosi: {e}")
        return None


async def fish_audio_tts(
    text: str,
    voice_id: str | None = None,
    lang: str = "uz",
    speed: float = 1.0,
) -> bytes | None:
    """Fish Audio TTS (OpenRouter orqali) — Kokoro/Edge ishlamayotganda fallback.

    Yaxshilashlar:
      1. O'zbekcha matn avval **fonetik ko'rinishga** o'tkaziladi (kirillcha):
         Fish Audio lotin yozuvidagi o'/g'/q/x harflarini noto'g'ri o'qiydi.
      2. Raqamlar o'zbekcha so'zlarga aylantiriladi.
      3. Uzun matn bo'laklarga bo'linadi — bitta so'rov qisqa bo'lgani uchun
         server "vaqt tugaydi" xatosini kamaytiradi.
      4. Timeout oshiriladi (FISH_TIMEOUT), qayta urinishlar qo'shiladi
         (FISH_RETRIES) va birinchi model ishlamasa ikkinchisi sinab ko'riladi.
    """
    if not OPENROUTER_API_KEY:
        logger.warning("OPENROUTER_API_KEY topilmadi — Fish Audio TTS ishlamaydi")
        return None

    text = (text or "").strip()
    if not text:
        return None

    # O'zbekcha matnni Fish Audio uchun tayyorlash
    prepared = prepare_for_fish(text, lang=lang, mode=FISH_UZ_MODE)
    if prepared != text:
        logger.debug("Fish Audio: matn o'zbekcha fonetik ko'rinishga o'tkazildi")

    # Uzun matnni bo'laklarga bo'lish (timeout kamayadi, talaffuz yaxshilanadi)
    parts = chunk_text(prepared, max_chars=FISH_CHUNK_CHARS)
    if not parts:
        return None

    audios: list[bytes] = []
    for part in parts:
        data = await _fish_synthesize(part, voice_id, speed)
        if not data:
            if audios:
                # Biror bo'lak ishlamasa — qolganlarini qaytaramiz
                # (butunlay vozlikdan voz kechgandan ko'ra foydaliroq)
                logger.warning(
                    "Fish Audio: bir bo'lak ishlamadi, qolganlari qaytariladi"
                )
                break
            return None
        audios.append(data)

    if not audios:
        return None
    if len(audios) == 1:
        return audios[0]

    merged = await concat_audio(audios)
    return merged or audios[0]


def _fish_payload(
    model: str,
    text: str,
    voice_id: str | None,
    speed: float,
    variant: dict,
) -> dict:
    """Fish Audio so'rov tanasini yig'adi."""
    payload: dict = {
        "model": model,
        "input": text,
        "response_format": "mp3",
    }
    if variant.get("voice") and voice_id and voice_id != "default":
        payload["voice"] = voice_id
    if variant.get("options"):
        payload["provider"] = {
            "options": {
                "fish-audio": {
                    "normalize": True,
                    "latency": variant.get("latency", "normal"),
                    "prosody": {
                        "speed": speed,
                        "normalize_loudness": True,
                    },
                }
            }
        }
    return payload


async def _fish_try(
    session: aiohttp.ClientSession,
    headers: dict,
    payload: dict,
) -> tuple[str, bytes | None, str]:
    """Bitta Fish Audio so'rovini bajaradi.

    Qaytadi: (holat, audio | None, xato matni)
      holat: "ok"    — muvaffaqiyat
             "fatal" — so'rov xato (boshqa variantni sinash kerak)
             "retry" — vaqt tugadi / server yuklama (qayta urinish kerak)
    """
    model = payload.get("model", "?")
    try:
        async with session.post(TTS_API_URL, headers=headers, json=payload) as resp:
            if resp.status == 200:
                data = await resp.read()
                if data and len(data) > 100:
                    return "ok", data, ""
                return "fatal", None, f"{model}: javob juda kichik ({len(data)} bayt)"

            body = ""
            try:
                body = (await resp.text())[:200]
            except Exception:
                pass
            err = f"{model}: HTTP {resp.status} {body}"
            if resp.status == 429 or resp.status >= 500:
                return "retry", None, err
            return "fatal", None, err
    except asyncio.TimeoutError:
        return "retry", None, f"{model}: TIMEOUT ({FISH_TIMEOUT}s)"
    except Exception as e:
        return "retry", None, f"{model}: {type(e).__name__}: {e}"


async def _fish_synthesize(
    text: str,
    voice_id: str | None,
    speed: float,
) -> bytes | None:
    """Fish Audio so'rovini variantlar va modellar zaxirasi bilan bajaradi."""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    timeout = aiohttp.ClientTimeout(
        total=FISH_TIMEOUT,
        sock_connect=FISH_CONNECT_TIMEOUT,
        sock_read=FISH_TIMEOUT,
    )

    # Urinish variantlari: avval to'liq so'rov, keyin soddalashtirilgan.
    # "high" latency sifatliroq, lekin sekin — timeout bo'lsa "normal" ga tushamiz.
    variants = [
        {"options": True, "voice": True, "latency": FISH_LATENCY},
        {"options": True, "voice": True, "latency": "normal"},
        {"options": True, "voice": False, "latency": "normal"},
        {"options": False, "voice": True, "latency": "normal"},
        {"options": False, "voice": False, "latency": "normal"},
    ]

    errors: list[str] = []
    deadline = time.monotonic() + max(60, FISH_BUDGET)
    retries = max(1, FISH_RETRIES)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        for model in FISH_TTS_MODELS:
            skip_variants = False
            for variant in variants:
                if skip_variants or time.monotonic() > deadline:
                    break

                payload = _fish_payload(model, text, voice_id, speed, variant)

                for attempt in range(1, retries + 1):
                    if time.monotonic() > deadline:
                        break

                    status, data, err = await _fish_try(session, headers, payload)
                    if status == "ok":
                        return data

                    errors.append(err)
                    if status == "fatal":
                        # Bu variant yaroqsiz — keyingisini sinab ko'ramiz
                        break

                    # "retry": timeout yoki server yuklamasi
                    if attempt < retries:
                        await asyncio.sleep(min(2 ** attempt, 10))
                        continue

                    # Urinishlar tugadi — variantlarni tashlab, keyingi modelga
                    skip_variants = True
                    break

            if time.monotonic() > deadline:
                break

    logger.error(
        "Fish Audio TTS muvaffaqiyatsiz: " + " | ".join(errors[-6:])
    )
    return None


# =============================================
# AI TTS — realistik ovozlar (Gemini / OpenAI)
# =============================================


def pcm_to_wav(pcm: bytes, sample_rate: int = 24000, channels: int = 1) -> bytes:
    """Xom PCM ma'lumotini WAV konteyneriga o'rab beradi (siz headersiz)."""
    import struct
    bits = 16
    byte_rate = sample_rate * channels * bits // 8
    block_align = channels * bits // 8
    header = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, channels, sample_rate, byte_rate, block_align, bits)
    header += b"data" + struct.pack("<I", len(pcm))
    return header + pcm


async def gemini_tts(text: str, voice: str = "Kore", lang: str = "uz") -> bytes | None:
    """Gemini 2.5 Flash TTS — juda realistik ovoz, bepul tier.

    Kalit `MIYYA_API_KEY` da. Agar kalit noto'g'ri bo'lsa — 15 daqiqa
    qayta urunilmaydi (serverga zarar bermaslik uchun).
    """
    if not GEMINI_API_KEY or not GEMINI_TTS_ENABLED:
        return None
    if _key_broken("gemini"):
        return None

    url = f"{GEMINI_BASE_URL}/{GEMINI_TTS_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": voice},
                }
            },
        },
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload,
                timeout=aiohttp.ClientTimeout(total=180),
            ) as resp:
                if resp.status != 200:
                    body = (await resp.text())[:250]
                    logger.error(f"Gemini TTS xatosi {resp.status}: {body}")
                    if resp.status in (400, 401, 403):
                        _mark_broken("gemini")
                    return None

                data = await resp.json()
                for cand in data.get("candidates", []):
                    for part in cand.get("content", {}).get("parts", []):
                        inline = part.get("inlineData") or {}
                        raw = inline.get("data")
                        if not raw:
                            continue
                        audio = base64.b64decode(raw)
                        mime = (inline.get("mimeType") or "").lower()
                        if "wav" in mime:
                            return audio
                        if "pcm" in mime or "l16" in mime:
                            rate = 24000
                            if "rate=" in mime:
                                try:
                                    rate = int(mime.split("rate=")[1].split(";")[0])
                                except ValueError:
                                    rate = 24000
                            return pcm_to_wav(audio, sample_rate=rate)
                        return audio
                logger.warning("Gemini TTS: audio qaytmadi")
                return None
    except Exception as e:
        logger.error(f"Gemini TTS xatosi: {type(e).__name__}: {str(e)[:200]}")
        return None


async def openai_tts(text: str, voice: str = "alloy", lang: str = "uz") -> bytes | None:
    """OpenAI TTS (gpt-4o-mini-tts / tts-1-hd) — juda realistik ovoz."""
    if not OPENAI_API_KEY:
        return None
    if _key_broken("openai"):
        return None

    payload = {
        "model": OPENAI_TTS_MODEL,
        "voice": voice,
        "input": text,
        "response_format": "mp3",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.openai.com/v1/audio/speech",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=aiohttp.ClientTimeout(total=180),
            ) as resp:
                if resp.status != 200:
                    body = (await resp.text())[:250]
                    logger.error(f"OpenAI TTS xatosi {resp.status}: {body}")
                    if resp.status in (401, 403):
                        _mark_broken("openai")
                    return None
                data = await resp.read()
                return data if len(data) > 100 else None
    except Exception as e:
        logger.error(f"OpenAI TTS xatosi: {type(e).__name__}: {str(e)[:200]}")
        return None


# =============================================
# ASOSIY SYNTEZ (dvigatel zanjiri)
# =============================================


async def synthesize_speech(
    text: str,
    lang: str = "uz",
    voice_id: str | None = None,
    gender: str = "male",
    speed: str = "normal",
    engine: str | None = None,
) -> tuple[bytes | None, str]:
    """
    Matnni ovozga aylantiradi.
    - Edge TTS birinchi (asosiy dvigatel — bepul, tez, o'zbekcha)
    - Kokoro TTS ikkinchi (Edge ishlamayotganda)
    - Fish Audio uchinchi
    - gTTS oxirgi (faqat qo'llab-quvvatlanadigan tillar)

    `engine` — katalogdan aniq dvigatel tanlangan bo'lsa ("kokoro"/"fish"),
    o'sha dvigatel birinchi ishlatiladi.

    Qaytadi: (audio_bytes | None, qaysi dvigatel ishlatildi)
    """
    text = (text or "").strip()
    if not text:
        return None, ""

    fish_speed = FISH_SPEEDS.get(speed, 1.0)

    # 0) AI TTS — realistik ovoz (Gemini / OpenAI).
    #    Aniq ovoz tanlangan bo'lsa — o'sha dvigatel birinchi.
    if engine == "gemini":
        audio = await gemini_tts(text, voice_id or "Kore", lang)
        if audio:
            return audio, "Gemini TTS"
    elif engine == "openai":
        audio = await openai_tts(text, voice_id or "alloy", lang)
        if audio:
            return audio, "OpenAI TTS"
    elif AI_TTS_FIRST:
        # Kalit mavjud bo'lsa — avval realistik AI ovozi
        if GEMINI_API_KEY and GEMINI_TTS_ENABLED and not _key_broken("gemini"):
            audio = await gemini_tts(text, "Kore", lang)
            if audio:
                return audio, "Gemini TTS"
        if OPENAI_API_KEY and not _key_broken("openai"):
            audio = await openai_tts(text, "alloy", lang)
            if audio:
                return audio, "OpenAI TTS"

    # 1) Edge TTS — bepul, limitsiz, kalitsiz (o'zbek ovozlari bor)
    edge_voice = get_edge_voice(lang, gender)
    edge_rate = EDGE_TTS_RATES.get(speed, "+0%")
    audio = await edge_tts_speak(text, edge_voice, rate=edge_rate)
    if audio:
        return audio, "Edge TTS"

    # 2) Kokoro TTS (bepul, HF Space)
    if KOKORO_ENABLED:
        audio = await kokoro_tts(text, voice_id)
        if audio:
            return audio, "Kokoro TTS"

    # 3) Fish Audio (kirill moslash — o'zbek talaffuzi to'g'ri)
    if OPENROUTER_API_KEY:
        audio = await fish_audio_tts(text, voice_id, lang=lang, speed=fish_speed)
        if audio:
            return audio, "Fish Audio"

    # 4) gTTS (oxirgi fallback)
    if lang in GTTS_LANGS:
        audio = await gtts_speak(text, lang)
        if audio:
            return audio, "gTTS"

    logger.error(f"Ovoz yaratib bo'lmadi (lang={lang})")
    return None, ""


# =============================================
# GRANDPA EFFEKTI (FFmpeg)
# =============================================

FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
TMP_DIR = Path(__file__).parent / "tmp"
TMP_DIR.mkdir(exist_ok=True)


async def concat_audio(parts: list[bytes]) -> bytes | None:
    """MP3 bo'laklarini bitta faylda birlashtiradi (FFmpeg concat demuxer).

    Fish Audio matnni bo'laklarga bo'lib yuborilganda kerak bo'ladi —
    har bir bo'lak alohida yig'ilib, keyin bitta faylda birlashtiriladi.
    """
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]

    uid = uuid.uuid4().hex[:12]
    list_path = TMP_DIR / f"concat_{uid}.txt"
    out_path = TMP_DIR / f"concat_{uid}.mp3"
    part_paths: list[Path] = []

    try:
        lines: list[str] = []
        for idx, part in enumerate(parts):
            p = TMP_DIR / f"cpart_{uid}_{idx}.mp3"
            p.write_bytes(part)
            part_paths.append(p)
            # FFmpeg concat demuxer uchun yo'lni "/" bilan yozamiz
            lines.append(f"file '{p.as_posix()}'")
        list_path.write_text("\n".join(lines), encoding="utf-8")

        cmd = [
            FFMPEG_PATH, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(list_path),
            "-c", "copy", str(out_path),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            logger.error(
                f"Audio birlashtirish xatosi: {stderr.decode(errors='replace')[:300]}"
            )
            return None
        if not out_path.exists() or out_path.stat().st_size == 0:
            logger.error("Audio birlashtirish natijasi bo'sh")
            return None
        return out_path.read_bytes()
    except Exception as e:
        logger.error(f"Audio birlashtirish xatosi: {e}")
        return None
    finally:
        for p in [*part_paths, list_path, out_path]:
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass


GRANDPA_SETTINGS = {
    "pitch": 0.82,        # pastroq ovoz (0.75-0.90)
    "tempo": 0.97,        # biroz sekinroq (0.90-1.0)
    "low_boost_db": 3,    # ko'krak rezonansi
    "high_cut_db": -3,    # yuqori chastotani kesish (keksa ovoz)
    "clip_threshold": 0.8,  # asoftclip chegarasi
    "denoise_strength": 10,  # afftdn NR darajasi
    "loudnorm_I": -16,    # loudnorm maqsadli loudness
}


async def apply_grandpa_effect(audio_bytes: bytes) -> bytes | None:
    """
    Audio fayliga 'Grandpa' (keksa odam) effektini qo'llaydi.
    FFmpeg: rubberband (pitch/formant) + EQ + asoftclip + afftdn + loudnorm.
    """
    s = GRANDPA_SETTINGS
    filter_str = (
        f"rubberband=pitch={s['pitch']}:tempo={s['tempo']},"
        f"equalizer=f=180:t=q:w=1.5:g={s['low_boost_db']},"
        f"equalizer=f=3500:t=q:w=2:g={s['high_cut_db']},"
        f"asoftclip=type=tanh:threshold={s['clip_threshold']},"
        f"afftdn=nr={s['denoise_strength']}:nf=-30,"
        f"loudnorm=I={s['loudnorm_I']}:TP=-1.5:LRA=11"
    )

    uid = uuid.uuid4().hex[:12]
    in_path = TMP_DIR / f"gp_in_{uid}.mp3"
    out_path = TMP_DIR / f"gp_out_{uid}.mp3"

    try:
        in_path.write_bytes(audio_bytes)

        cmd = [
            FFMPEG_PATH, "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(in_path),
            "-af", filter_str,
            "-b:a", "128k",
            str(out_path),
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            logger.error(f"Grandpa FFmpeg xatosi: {stderr.decode(errors='replace')[:300]}")
            return None

        if not out_path.exists() or out_path.stat().st_size == 0:
            logger.error("Grandpa effekti bo'sh fayl qaytardi")
            return None

        return out_path.read_bytes()

    except Exception as e:
        logger.error(f"Grandpa effekti xatosi: {e}")
        return None
    finally:
        for p in (in_path, out_path):
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass


# =============================================
# THINKING MODEL — matnni ovozli nutqqa tayyorlash
# =============================================


async def improve_prompt(text: str, mode: str = "tts") -> str:
    """Thinking model matnni ovozli nutqqa tayyorlaydi (raqamlar -> so'zlar, imlo va h.k.)."""
    if not OPENROUTER_THINKING_KEY:
        return text

    if mode == "stt":
        system_msg = (
            "Siz ovozdan matnga aylantirilgan matnni tozalaysiz.\n"
            "Vazifangiz:\n"
            "1. Punktuatsiyani qo'shing (nuqta, vergul, savol belgisi).\n"
            "2. O'zbekcha matn bo'lsa, imlosini tuzating: o', g', so'ngra, "
            "nima uchun, xuddi, albatta.\n"
            "3. Transkripsiya xato so'zlarini kontekstdan kelib chiqib tuzating.\n"
            "4. Ma'noni hech qanday o'zgartirmang, qo'shimcha so'z qo'shmang.\n"
            "5. Matn boshqa tilda bo'lsa, o'sha tilda tozalang.\n\n"
            "Faqat tozalangan matnni qaytaring, boshqa hech narsa yozmang."
        )
    else:
        system_msg = (
            "Siz matnni ovozli nutqqa tayyorlash yordamchisisiz.\n"
            "Vazifangiz:\n"
            "1. Punktuatsiyani to'g'rilang — nutqda pauzalar shu belgilarga "
            "bog'lanadi (nuqta, vergul, savol/tanqis belgisi).\n"
            "2. O'zbekcha matn bo'lsa, imlosini tekshiring: o', g', so'ngra, "
            "nima uchun, xuddi, albatta.\n"
            "3. Raqamlarni ovozda o'qiladigan so'zlarga aylantiring, chunki "
            "model raqamlarni noto'g'ri o'qiydi:\n"
            "   - 2025 -> 'ikki ming yigirma besh'\n"
            "   - 5 -> 'besh', 100 -> 'yuz', 3 -> 'uch'\n"
            "   - 12:30 -> 'o'n ikki yarim'\n"
            "4. Qisqartmalarni oching: 'Dr.' -> 'doktor', 'km' -> 'kilometr'.\n"
            "5. Agar o'qilishi qiyin bo'lsa, tabiiy ravishda ozgina qayta "
            "ifodalang, lekin ma'no saqlansin.\n"
            "6. Boshqa tildagi matn uchun — o'sha tilda tabiiy qilib tayyorlang "
            "va o'sha tilning imlosiga amal qiling.\n\n"
            "Ma'noni o'zgartirmang. Faqat tayyor matnni qaytaring."
        )

    headers = {
        "Authorization": f"Bearer {OPENROUTER_THINKING_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": THINKING_MODEL,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": text[:6000]},
        ],
        "max_tokens": 1000,
        "reasoning": {"enabled": False},
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                THINKING_API_URL, headers=headers, json=payload,
                timeout=aiohttp.ClientTimeout(total=90),
            ) as resp:
                if resp.status != 200:
                    return text
                data = await resp.json()
                content = data["choices"][0]["message"].get("content")
                if not content:
                    return text
                for junk in ("```", "`", "**", "__", "#"):
                    content = content.replace(junk, "")
                content = content.strip()
                return content if content else text
    except Exception as e:
        logger.error(f"improve_prompt xatosi: {e}")
        return text


# =============================================
# GEMINI AI — umumiy so'rov + chat / JSON / STT
# =============================================


async def _gemini_call(contents: list, system_prompt: str | None = None,
                       temperature: float = 0.6) -> str | None:
    """Gemini generateContent ga so'rov yuboradi, matn javobini qaytaradi."""
    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY (MIYYA_API_KEY) topilmadi")
        return None

    url = f"{GEMINI_BASE_URL}/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"

    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": 8192,
        },
    }
    if system_prompt:
        payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload,
                timeout=aiohttp.ClientTimeout(total=90),
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"Gemini API xatosi {resp.status}: {error_text[:300]}")
                    return None
                data = await resp.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    logger.warning("Gemini: candidates bo'sh")
                    return None
                parts = candidates[0].get("content", {}).get("parts", [])
                chunks = [p["text"] for p in parts if "text" in p]
                text = "".join(chunks).strip()
                return text or None
    except Exception as e:
        logger.error(f"Gemini so'rov xatosi: {e}")
        return None


def _contents_with_history(user_message: str, history: list | None) -> list:
    """Foydalanuvchi suhbat tarixini Gemini contents ko'rinishiga o'giradi."""
    contents = []
    for h in (history or [])[-10:]:
        role = h.get("role", "user")
        if role not in ("user", "model"):
            role = "user"
        txt = (h.get("text") or "").strip()
        if txt:
            contents.append({"role": role, "parts": [{"text": txt}]})
    contents.append({"role": "user", "parts": [{"text": user_message}]})
    return contents


async def gemini_chat(user_message: str, system_prompt: str | None = None,
                      history: list | None = None) -> str | None:
    """Gemini orqali suhbat javobi."""
    return await _gemini_call(
        _contents_with_history(user_message, history),
        system_prompt,
        temperature=0.8,
    )


def _parse_json_block(text: str) -> dict | None:
    """Gemini javobidan JSON obyektini ajratib oladi (markdown kod bloklarini ham)."""
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)

    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end <= start:
        return None
    candidate = t[start:end + 1]

    for attempt in (candidate, re.sub(r",\s*([}\]])", r"\1", candidate)):
        try:
            obj = json.loads(attempt)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    return None


async def gemini_json(user_message: str, system_prompt: str,
                      history: list | None = None,
                      temperature: float = 0.2) -> dict | None:
    """Gemini dan strukturali JSON oladi."""
    text = await _gemini_call(
        _contents_with_history(user_message, history),
        system_prompt,
        temperature=temperature,
    )
    return _parse_json_block(text)


# =============================================
# LLM ZANJIRI — OpenRouter (asosiy) + Gemini (zaxira)
# =============================================


async def _openrouter_call(
    messages: list,
    system_prompt: str | None = None,
    temperature: float = 0.6,
    models: list[str] | None = None,
) -> str | None:
    """OpenRouter chat/completions orqali matn oladi.

    Modellar ro'yxati bo'yicha sinaydi — birinchisi ishlamasa keyingisi.
    """
    if not LLM_API_KEY:
        logger.warning("OpenRouter kaliti topilmadi")
        return None

    msgs: list[dict] = []
    if system_prompt:
        msgs.append({"role": "system", "content": system_prompt})
    msgs.extend(messages)

    for model in (models or LLM_MODELS):
        payload = {
            "model": model,
            "messages": msgs,
            "temperature": temperature,
            "max_tokens": 1500,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    THINKING_API_URL,
                    headers={
                        "Authorization": f"Bearer {LLM_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=90),
                ) as resp:
                    if resp.status != 200:
                        body = (await resp.text())[:200]
                        logger.warning(f"OpenRouter {model} -> HTTP {resp.status}: {body}")
                        continue
                    data = await resp.json()
                    choices = data.get("choices") or []
                    if not choices:
                        logger.warning(f"OpenRouter {model} -> choices bo'sh")
                        continue
                    content = (choices[0].get("message") or {}).get("content") or ""
                    content = content.strip()
                    if content:
                        return content
        except Exception as e:
            logger.warning(f"OpenRouter {model} xatosi: {type(e).__name__}: {str(e)[:150]}")
            continue
    return None


def _messages_with_history(user_message: str, history: list | None) -> list:
    """Tarihni OpenRouter chat formatiga o'giradi."""
    msgs: list[dict] = []
    for h in (history or [])[-10:]:
        role = h.get("role", "user")
        if role not in ("user", "assistant"):
            role = "user"
        txt = (h.get("text") or "").strip()
        if txt:
            msgs.append({"role": role, "content": txt})
    msgs.append({"role": "user", "content": user_message})
    return msgs


async def llm_chat(user_message: str, system_prompt: str | None = None,
                   history: list | None = None) -> str | None:
    """Suhbat javobi: OpenRouter -> Gemini -> None."""
    text = await _openrouter_call(
        _messages_with_history(user_message, history),
        system_prompt,
        temperature=0.8,
    )
    if text:
        return text
    # OpenRouter ishlamasa — Gemini bilan urinib ko'ramiz
    return await _gemini_call(
        _contents_with_history(user_message, history),
        system_prompt,
        temperature=0.8,
    )


async def llm_json(user_message: str, system_prompt: str,
                   history: list | None = None,
                   temperature: float = 0.2) -> dict | None:
    """Strukturali JSON: OpenRouter -> Gemini -> None."""
    text = await _openrouter_call(
        _messages_with_history(user_message, history),
        system_prompt,
        temperature=temperature,
    )
    obj = _parse_json_block(text) if text else None
    if obj:
        return obj
    # OpenRouter ishlamasa — Gemini bilan urinib ko'ramiz
    return await gemini_json(user_message, system_prompt, history, temperature)


async def gemini_stt(audio_bytes: bytes, mime_type: str = "audio/ogg") -> str | None:
    """Ovoz faylini Gemini orqali matnga aylantiradi (STT)."""
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
    contents = [{
        "parts": [
            {"inline_data": {"mime_type": mime_type, "data": audio_b64}},
            {"text": (
                "Bu ovozli xabar (Telegram voice message). "
                "Undagi so'zlarni aniq transkripsiya qiling.\n"
                "Qoidalar:\n"
                "- Agar o'zbekcha bo'lsa, o'zbek tilida yozing (o', g', so'ngra)\n"
                "- Agar boshqa tilda bo'lsa, o'sha tilda yozing\n"
                "- Faqat transkripsiya matnini qaytaring\n"
                "- Boshqa hech narsa yozmang (izoh, tushuntirish kerak emas)"
            )},
        ]
    }]
    return await _gemini_call(contents, temperature=0.1)


# --- STT zaxira: lokal faster-whisper (Gemini kaliti noto'g'ri bo'lsa) ---
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "small")
_whisper_model = None


def _patch_av_for_whisper() -> None:
    """PyAV 19 da metadata_errors parametri olib tashlangan — moslik uchun."""
    try:
        import faster_whisper.audio as fwa
        import av as _av

        class _AvProxy:
            def __init__(self, real):
                self._real = real

            def __getattr__(self, name):
                return getattr(self._real, name)

            def open(self, file, mode="r", **kwargs):
                kwargs.pop("metadata_errors", None)
                return self._real.open(file, mode, **kwargs)

        fwa.av = _AvProxy(_av)
        logger.info("PyAV patch qo'llandi (faster-whisper mosligi)")
    except Exception as e:
        logger.warning(f"PyAV patch bo'lmadi: {e}")


async def whisper_stt(audio_bytes: bytes) -> str | None:
    """Lokal faster-whisper bilan ovozni matnga aylantiradi (STT zaxirasi)."""
    global _whisper_model
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return None

    if _whisper_model is None:
        _patch_av_for_whisper()

        def _load():
            from faster_whisper import WhisperModel
            return WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")

        try:
            _whisper_model = await asyncio.to_thread(_load)
            logger.info(f"Whisper model yuklandi: {WHISPER_MODEL_SIZE}")
        except Exception as e:
            logger.error(f"Whisper yuklanmadi: {e}")
            return None

    tmp = TMP_DIR / f"whisper_{uuid.uuid4().hex[:10]}.ogg"
    try:
        tmp.write_bytes(audio_bytes)

        def _run():
            segments, info = _whisper_model.transcribe(str(tmp), language="uz", beam_size=1)
            return " ".join(s.text.strip() for s in segments).strip()

        text = await asyncio.to_thread(_run)
        return text or None
    except Exception as e:
        logger.error(f"Whisper STT xatosi: {e}")
        return None
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


async def stt_transcribe(audio_bytes: bytes, mime_type: str = "audio/ogg") -> str | None:
    """Ovozni matnga aylantiradi: Gemini -> Whisper -> None."""
    if GEMINI_API_KEY and not _key_broken("gemini"):
        text = await gemini_stt(audio_bytes, mime_type)
        if text:
            return text
    return await whisper_stt(audio_bytes)


# =============================================
# NIYAT (INTENT) ANIQLASH — Gemini + kalit so'z fallback
# =============================================

VALID_INTENTS = {"chat", "tts", "grandpa", "script"}

INTENT_SYSTEM = """Sen Telegram AI ovoz botining miyasisan. Foydalanuvchi xabarini tahlil qilib, NATIJANI FAQAT JSON ko'rinishida qaytarasiz (boshqa matn, tarmoqcha belgi yoki izoh YO'Q).

Intent turlari:
1. "tts" — foydalanuvchi matnni ovozga aylantirmoqchi (masalan: 'ovozga chiqar', 'o'qib ber', 'tts qil', 'speak').
2. "grandpa" — keksa odam / bobo ovozi effekti so'ralmoqda.
3. "script" — uzun senariy, dialog, pyescha, dars skripti yoki audiodrama (odatda 2+ qahramon, 'Ism: matn' ko'rinishidagi replikalar).
4. "chat" — oddiy suhbat, savol, tarjima, hisob-kitob, yordam va boshqalar.

JSON shakli:
{
  "intent": "chat|tts|grandpa|script",
  "text": "ovoz uchun toza matn (faqat tts/grandpa uchun: tarmoqcha, #, emoji, rejissyor yo'riqnomalarini olib tashlang, raqamlarni so'zlarga aylantiring)",
  "lang": "matn tili ikki harfda: uz, ru, en, kk, ky, tr, de, ...",
  "voice": "default|male|female|child|grandpa — foydalanuvchi aniq ovoz talab qilmasa 'default'",
  "reply": "faqat chat intenti uchun: iliq, foydali javob (o'zbekcha, 1000 belgidan qisqa, emoji bo'lishi mumkin)"
}

Muhim qoidalar:
- Javob FAQAT JSON bo'lishi kerak.
- 'script' intentida 'text' maydoniga senariyni takrorlash shart emas (bo'sh qoldiring).
- Matn boshqa tilda bo'lsa, 'lang' shu tilni ko'rsating.
- Foydalanuvchi o'zbekcha yozsa, 'reply'ni o'zbekcha yozing."""

GRANDPA_KEYWORDS = ("grandpa", "keksa", "bobojon", "bobo ovoz", "keksa odam", "bobokhal", "—")
TTS_KEYWORDS = (
    "ovozga aylantir", "ovozga chiqar", "ovozga ot", "o'qib ber", "oqib ber",
    "ovozli qil", "gapirtir", "ovoz ber", "tts", "speak", "audio qil", "ovozga utqaz",
)
CHAT_KEYWORDS_HELP = (
    "nima qila", "imkoniyat", "yordam", "help", "qanday ishla", "bot nima", "—",
)


def keyword_intent(raw: str) -> dict:
    """Gemini ishlamaydigan bo'lsa — oddiy kalit so'zlar bilan niyat aniqlash."""
    text = (raw or "").strip()
    low = text.lower()

    # 1) Senariy: uzoq matn + 'Ism: matn' ko'rinishidagi replikalar
    dialogue_lines = [
        ln for ln in text.splitlines()
        if re.match(r"^\s*[^:\n]{1,40}:\s*\S", ln)
    ]
    if len(text) >= 200 and len(dialogue_lines) >= 3:
        return {"intent": "script", "text": "", "lang": "uz", "voice": "default", "reply": ""}

    # 2) Grandpa effekti
    if any(k in low for k in GRANDPA_KEYWORDS):
        return {"intent": "grandpa", "text": text, "lang": "uz", "voice": "default", "reply": ""}

    # 3) Matn -> ovoz
    if any(k in low for k in TTS_KEYWORDS):
        return {"intent": "tts", "text": text, "lang": "uz", "voice": "default", "reply": ""}

    # 4) Oddiy suhbat
    return {"intent": "chat", "text": text, "lang": "uz", "voice": "default", "reply": ""}


def normalize_lang(lang) -> str:
    if not isinstance(lang, str) or len(lang.strip()) < 2:
        return "uz"
    return lang.strip()[:2].lower()


def normalize_intent(obj: dict | None, raw: str) -> dict:
    """Gemini JSONini tekshiradi/mukammallantiradi; yaroqsiz bo'lsa fallback."""
    if not isinstance(obj, dict):
        return keyword_intent(raw)

    kind = str(obj.get("intent", "")).strip().lower()
    if kind not in VALID_INTENTS:
        logger.warning(f"Noma'lum intent: {kind!r} — fallback ishlatiladi")
        return keyword_intent(raw)

    result = {
        "intent": kind,
        "text": str(obj.get("text") or "").strip(),
        "lang": normalize_lang(obj.get("lang")),
        "voice": str(obj.get("voice") or "default").strip().lower(),
        "reply": str(obj.get("reply") or "").strip(),
    }

    # tts/grandpa uchun matn bo'sh bo'lsa — xududiy matndan foydalanamiz
    if kind in ("tts", "grandpa") and not result["text"]:
        result["text"] = raw.strip()

    return result


async def detect_intent(text: str, history: list | None = None) -> dict:
    """Gemini orqali niyat aniqlaydi; Gemini yiqilsa — kalit so'z fallback."""
    raw = await llm_json(text, INTENT_SYSTEM, history=history, temperature=0.2)
    intent = normalize_intent(raw, text)
    logger.info(f"Intent: {intent['intent']} (lang={intent['lang']}, voice={intent['voice']})")
    return intent


# =============================================
# SENARIY TAHLILI — qahramonlarni ajratish
# =============================================

SCRIPT_SYSTEM = (
    "Sen professional senariy tahlilchisisiz. Sizga senariy (dialog, pyescha, "
    "dars skripti, audiodrama) beriladi. Uni OVOZ YOZISH uchun quyidagi JSON "
    "ko'rinishida qaytaring (faqat JSON, boshqa matn yo'q):\n\n"
    "{\n"
    '  "lang": "senariy tili, ikki harf (masalan uz)",\n'
    '  "characters": [\n'
    "    {\n"
    '      "name": "Qahramon nomi",\n'
    '      "gender": "male",\n'
    '      "lines": ["Birinchi replikasi", "Ikkinchi replikasi"]\n'
    "    }\n"
    "  ]\n"
    "}\n\n"
    "Qoidalar:\n"
    "1. Faqat qahramonlarining SO'ZLARINI 'lines' ichiga joylang; rejissyor "
    "yo'riqnomalari, sahna nomlari, tavsiflar kerak emas.\n"
    "2. Har bir qahramon alohida obyekt bo'lsin; uning replikalari ketma-ket "
    "tartibda joylansin.\n"
    "3. 'gender': erkak/o'g'il/ota -> male, ayol/qiz/onasi -> female, bola/"
    "bolalar/chaqaloq -> child.\n"
    "4. 12 tadan ko'p qahramon bo'lmasin.\n"
    "5. Matn tilini o'zgartirmang (tarjima qilmang).\n"
    "6. Agar qahramon nomi bo'lmasa: 'Qahramon 1', 'Qahramon 2' deb nomlang."
)


def normalize_script(obj: dict | None) -> list[dict]:
    """Gemini JSONini qahramonlar ro'yxatiga aylantiradi."""
    if not isinstance(obj, dict):
        return []
    chars = obj.get("characters")
    if not isinstance(chars, list):
        return []

    result = []
    for c in chars[:MAX_SCRIPT_CHARACTERS]:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name") or "Qahramon").strip()[:40] or "Qahramon"
        gender = str(c.get("gender") or "male").strip().lower()
        if gender not in GENDER_POOLS:
            if gender in ("erkak", "m", "man", "o'g'il", "ota"):
                gender = "male"
            elif gender in ("ayol", "f", "qiz", "onasi", "ayol kishi"):
                gender = "female"
            elif gender in ("bola", "bolalar", "chaqaloq", "bolacha"):
                gender = "child"
            else:
                gender = "male"
        lines = c.get("lines") or []
        if isinstance(lines, str):
            lines = [lines]
        lines = [str(l).strip() for l in lines if str(l).strip()]
        if lines:
            result.append({"name": name, "gender": gender, "lines": lines})

    return result


async def parse_script(text: str) -> tuple[list[dict], str]:
    """Senariyni Gemini bilan tahlil qilib, qahramonlar ro'yxatini qaytaradi."""
    raw = await llm_json(text, SCRIPT_SYSTEM, temperature=0.2)
    characters = normalize_script(raw)
    lang = normalize_lang(raw.get("lang")) if isinstance(raw, dict) else "uz"
    return characters, lang


def chunk_lines(lines: list[str], max_chars: int = MAX_SCRIPT_CHARS) -> list[str]:
    """Qahramon replikalarini ovoz uchun qulay bo'lakchalarga bo'ladi."""
    chunks: list[str] = []
    current = ""
    for line in lines:
        if current and len(current) + len(line) + 1 > max_chars:
            chunks.append(current)
            current = line
        else:
            current = f"{current} {line}".strip() if current else line
    if current:
        chunks.append(current)
    return chunks


# =============================================
# SUHBAT TARIXI
# =============================================


def get_history(uid: int) -> list[dict]:
    return user_data.setdefault(uid, {}).setdefault("history", [])


def append_history(uid: int, user_text: str, bot_text: str) -> None:
    history = get_history(uid)
    history.append({"role": "user", "text": user_text[:2000]})
    history.append({"role": "model", "text": bot_text[:2000]})
    del history[:-12]  # oxirgi 12 xabarni saqlaymiz (4 juft)


# =============================================
# PROMPTLAR (salomlashuv, suhbat, fallback)
# =============================================

GREETING_SYSTEM = (
    "Sen 'AI Ovoz Bot' — Telegram'dagi iliq, do'stona o'zbek tilidagi yordamchisan.\n"
    "Foydalanuvchi botni yangi boshladi. Quyidagilarni qisqacha va chiroyli "
    "emoji bilan tushuntirib, so'ng o'zingizdan xabar kutishini so'rang:\n"
    "- Matnni ovozga aylantirish (tabiiy ovoz)\n"
    "- Ovozli xabarni matnga aylantirish\n"
    "- Grandpa (keksa odam) effekti\n"
    "- Senariy bo'yicha har bir qahramon uchun alohida ovoz\n"
    "- Oddiy suhbat va savollarga javob\n\n"
    "Qoidalar: 350 belgidan kam, o'zbekcha, emoji bilan. Faqat matn qaytaring."
)

DEFAULT_GREETING = (
    "Assalomu alaykum! — Men <b>AI Ovoz Bot</b>man — sizning o'zbek tilidagi "
    "ovoz yordamchingiz.\n\n"
    "Men nima qila olaman:\n"
    "— Matnni ovozga aylantiraman\n"
    "— Ovozli xabaringizni matnga aylantiraman\n"
    "— Grandpa (keksa odam) effektini qo'llayman\n"
    "— Senariy bo'yicha har bir qahramonni alohida ovozda ovozlayman\n"
    "— Har qanday savolga o'zbekcha javob beraman\n\n"
    "Shunchaki yozing yoki mikrofon tugmasini bosib ovoz yuboring — "
    "men o'zim tushunib olaman. ——"
)

CHAT_SYSTEM = (
    "Sen 'AI Ovoz Bot' — Telegram'dagi foydali o'zbek tilidagi yordamchisan.\n"
    "Imkoniyatlaring: matnni ovozga aylantirish, ovozli xabarni matnga o'girish, "
    "Grandpa effekti, senariy bo'yicha qahramonlarga alohida ovoz, oddiy suhbat.\n"
    "Qoidalar:\n"
    "- Doimo o'zbek tilida javob bering (foydalanuvchi boshqa tilda yozmasa).\n"
    "- Qisqa, iliq, do'stona va amaliy bo'ling (1000 belgidan kam).\n"
    "- Agar foydalanuvchi ovoz yaratishni so'rasa, matnni jo'natishini ayting — "
    "bot o'zi ovozga aylantiradi.\n"
    "- Kutilmagan savolga ham foydali javob bering."
)


def fallback_chat_reply(text: str) -> str:
    """Gemini umuman ishlamasa — oddiy kalit so'zli javoblar."""
    low = text.lower()
    if any(k in low for k in ("salom", "assalomu", "—", "hello", "hi")):
        return ("Assalomu alaykum! — Men AI Ovoz Botman. Matn yozing — "
                "ovozga aylantiraman, yoki ovoz yuboring — matnga o'giraman.")
    if any(k in low for k in CHAT_KEYWORDS_HELP):
        return ("Men quyidagilarni qila olaman:\n"
                "— Matn — ovoz\n"
                "— Ovoz — matn\n"
                "— Grandpa effekti\n"
                "— Senariy — qahramonlar uchun alohida ovoz\n\n"
                "Shunchaki matn yoki ovoz yuboring — men o'zim tushunaman. ——")
    if any(k in low for k in ("ovoz", "tts", "voice")):
        return "Matnni yuboring — men uni ovozga aylantirib beraman. —"
    return ("Kechirasiz, AI bilan aloqa vaqtincha uzildi ——. "
            "Birozdan keyin qayta yozing yoki /start bosing.")


# =============================================
# AI OQIMI — niyat bo'yicha amallar
# =============================================


def selected_voice(settings: dict) -> tuple[str, str | None]:
    """Katalogdan tanlangan ovozni qaytaradi: (voice_id, engine).

    Tanlangan yo'q bo'lsa — ("", None) qaytaradi.
    """
    vid = (settings.get("voice_id") or "").strip()
    if not vid:
        return "", None
    for v in VOICE_CATALOG:
        if v["id"] == vid:
            return v["id"], v["engine"]
    return "", None


async def do_tts(message: Message, processing: Message, text: str, intent: dict) -> None:
    """Matn -> ovoz."""
    speak = (intent.get("text") or text).strip()
    lang = intent.get("lang") or "uz"
    hint = intent.get("voice") or "default"

    # Foydalanuvchi sozlamalarini olamiz
    uid = message.from_user.id
    settings = await db.get_settings(uid)
    gender = settings["voice_gender"]
    speed = settings["speed"]

    # Katalogdan tanlangan aniq ovoz (agar bo'lsa) — ustunlikka ega
    voice_id, voice_engine = selected_voice(settings)
    if not voice_id:
        voice_id = voice_for_hint(hint)

    # Agar foydalanuvchi ma'lum til/ovoz so'ragan bo'lsa — o'shani ishlatamiz
    if lang not in EDGE_TTS_VOICES:
        lang = settings["language"]

    if not speak:
        await safe_edit(processing, T.ERR_EMPTY_TEXT)
        return
    if len(speak) > MAX_TEXT_CHARS:
        speak = speak[:MAX_TEXT_CHARS]

    await safe_edit(processing, T.STATUS_TTS, parse_mode=ParseMode.HTML)
    await record_voice(message)

    # Matnni bo'laklarga bo'lamiz
    chunks = chunk_text(speak)
    if not chunks:
        await safe_edit(processing, T.ERR_EMPTY_TEXT)
        return

    sent = 0
    for idx, chunk in enumerate(chunks, start=1):
        if len(chunks) > 1:
            await safe_edit(
                processing,
                T.STATUS_CHUNK.format(current=idx, total=len(chunks)),
                parse_mode=ParseMode.HTML,
            )
            await record_voice(message)

        async with TTS_SEMAPHORE:
            audio, engine = await synthesize_speech(
                chunk, lang=lang, voice_id=voice_id,
                gender=gender, speed=speed, engine=voice_engine,
            )

        if not audio:
            logger.error(f"Bo'lak {idx}/{len(chunks)} uchun ovoz yaratib bo'lmadi")
            continue

        # MP3 -> OGG (Opus) konversiya (Telegram voice uchun)
        ogg = await mp3_to_ogg(audio)
        if ogg:
            voice_file = BufferedInputFile(ogg, filename="voice.ogg")
        else:
            # Konversiya ishlamasa — MP3 sifatida yuboramiz
            voice_file = BufferedInputFile(audio, filename="voice.mp3")

        caption = T.TTS_DONE.format(engine=engine, lang=lang.upper(), chars=len(chunk))
        if len(chunks) > 1:
            caption += f" ({idx}/{len(chunks)})"

        await message.answer_voice(voice=voice_file, caption=caption)
        sent += 1

    await kill(processing)

    if sent == 0:
        await message.answer(T.ERR_NO_VOICE, parse_mode=ParseMode.HTML)


async def do_grandpa(message: Message, processing: Message, text: str, intent: dict) -> None:
    """Matn -> ovoz -> Grandpa (keksa odam) effekti."""
    speak = (intent.get("text") or text).strip()
    lang = intent.get("lang") or "uz"
    hint = intent.get("voice") or "default"

    # Foydalanuvchi sozlamalarini olamiz
    uid = message.from_user.id
    settings = await db.get_settings(uid)
    gender = settings["voice_gender"]
    speed = settings["speed"]

    if lang not in EDGE_TTS_VOICES:
        lang = settings["language"]

    if not speak:
        await safe_edit(processing, T.ERR_EMPTY_TEXT)
        return
    if len(speak) > 3000:
        speak = speak[:3000]

    await safe_edit(processing, T.STATUS_TTS, parse_mode=ParseMode.HTML)
    await record_voice(message)

    async with TTS_SEMAPHORE:
        audio, _engine = await synthesize_speech(
            speak, lang=lang, voice_id=voice_for_hint(hint),
            gender=gender, speed=speed,
            engine="kokoro" if KOKORO_ENABLED else None,
        )
    if not audio:
        await safe_edit(processing, T.ERR_NO_VOICE, parse_mode=ParseMode.HTML)
        return

    await safe_edit(processing, T.STATUS_GRANDPA, parse_mode=ParseMode.HTML)
    processed = await apply_grandpa_effect(audio)
    if processed is None:
        logger.warning("Grandpa effekti ishlamadi, oddiy ovoz yuboriladi")
        processed = audio

    # MP3 -> OGG konversiya
    ogg = await mp3_to_ogg(processed)
    if ogg:
        voice_file = BufferedInputFile(ogg, filename="grandpa.ogg")
    else:
        voice_file = BufferedInputFile(processed, filename="grandpa_voice.mp3")

    await message.answer_voice(
        voice=voice_file,
        caption=T.GRANDPA_DONE.format(chars=len(speak)),
    )
    await kill(processing)


async def do_script(message: Message, processing: Message, text: str) -> None:
    """Senariy -> qahramonlarni ajratish -> har biriga alohida ovoz."""
    await safe_edit(processing, T.STATUS_SCRIPT_PARSE, parse_mode=ParseMode.HTML)
    await typing(message)

    characters, lang = await parse_script(text)

    if not characters:
        await safe_edit(
            processing,
            T.ERR_SCRIPT_PARSE,
            parse_mode=ParseMode.HTML,
        )
        return

    summary_lines = "\n".join(
        f"— {c['name']} — {GENDER_LABELS.get(c['gender'], 'erkak')} "
        f"({len(c['lines'])} ta replika)"
        for c in characters
    )
    await message.answer(
        T.SCRIPT_FOUND.format(
            count=len(characters), summary=summary_lines
        ),
        parse_mode=ParseMode.HTML,
    )

    used = {"male": 0, "female": 0, "child": 0}
    sent = 0

    settings = await db.get_settings(message.from_user.id)
    fish_speed = FISH_SPEEDS.get(settings.get("speed", "normal"), 1.0)

    for ch in characters:
        voice_id, voice_name = voice_for_gender(ch["gender"], used[ch["gender"]])
        # Fish Audio uchun alohida (Fish'ga tegishli) ovoz kerak
        fish_voice = fish_voice_for_gender(ch["gender"], used[ch["gender"]])
        used[ch["gender"]] += 1

        parts = chunk_lines(ch["lines"])
        for idx, part in enumerate(parts, start=1):
            await safe_edit(
                processing,
                f"— {ch['name']} ovozi yaratilmoqda ({idx}/{len(parts)})...",
            )
            await typing(message)

            # Qahramon ovozlari uchun Kokoro (har xil ovozlar kerak),
            # u ishlamasa — Fish Audio -> gTTS ga fallback
            audio = await kokoro_tts(part, voice_id)
            if not audio:
                audio = await fish_audio_tts(
                    part, fish_voice, lang=lang, speed=fish_speed
                )
            if not audio:
                audio = await gtts_speak(part, lang)

            if not audio:
                logger.error(f"{ch['name']} uchun ovoz yaratib bo'lmadi")
                continue

            caption = f"— {ch['name']} — {voice_name}"
            if len(parts) > 1:
                caption += f" ({idx}/{len(parts)})"
            await message.answer_voice(
                voice=BufferedInputFile(audio, filename="voice.mp3"),
                caption=caption,
            )
            sent += 1

    if sent == 0:
        await safe_edit(
            processing, "— Ovozlarni yaratib bo'lmadi. Qayta urinib ko'ring."
        )
        return

    await kill(processing)
    await message.answer(
        T.SCRIPT_DONE.format(count=sent), parse_mode=ParseMode.HTML
    )


async def do_chat(message: Message, processing: Message, text: str,
                  intent: dict, history: list) -> None:
    """Oddiy suhbat (Gemini + tarix + fallback)."""
    reply = (intent.get("reply") or "").strip()

    if not reply:
        await typing(message)
        reply = (await llm_chat(text, CHAT_SYSTEM, history=history) or "").strip()

    if not reply:
        reply = fallback_chat_reply(text)

    append_history(message.from_user.id, text, reply)
    await safe_edit(processing, clip(clean_ai_text(reply), TG_MSG_LIMIT))


async def run_pipeline(
    message: Message,
    user_text: str,
    processing: Message,
    force: str = "auto",
) -> None:
    """Asosiy AI oqimi: niyat aniqlash -> amal bajarish.

    `force` — "auto" bo'lmasa, AI niyat aniqlash o'rniga shu rejim
    majburan qo'llaniladi (menyu orqali tanlangan rejim).
    """
    text = (user_text or "").strip()
    if not text:
        await safe_edit(processing, T.ERR_EMPTY_TEXT)
        return

    uid = message.from_user.id

    # Kunlik limitni tekshiramiz
    if not await db.check_daily_limit(uid, DAILY_LIMIT):
        await safe_edit(
            processing,
            T.ERR_DAILY_LIMIT.format(limit=DAILY_LIMIT),
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        await typing(message)
        history = get_history(uid)
        if force and force != "auto":
            # Rejim menyudan tanlangan — AI aniqlash kerak emas
            intent = {
                "intent": force,
                "text": text,
                "lang": "uz",
                "voice": "default",
                "reply": "",
            }
            logger.info(f"Intent: {force} (tanlangan rejim)")
        else:
            intent = await detect_intent(text, history)
        kind = intent["intent"]

        # Matnni tarixga saqlaymiz
        await db.add_history(uid, text)

        # So'rovlar hisobini oshiramiz
        await db.increment_usage(uid)

        if kind == "tts":
            await do_tts(message, processing, text, intent)
        elif kind == "grandpa":
            await do_grandpa(message, processing, text, intent)
        elif kind == "script":
            await do_script(message, processing, text)
        else:
            await do_chat(message, processing, text, intent, history)

    except Exception as e:
        logger.error(f"Oqim xatosi: {e}", exc_info=True)
        await safe_edit(processing, T.ERR_UNKNOWN.format(error=str(e)[:200]))


# =============================================
# MIDDLEWARE (throttling) va SEMAPHORE
# =============================================

# TTS parallelligini cheklash (bir vaqtda ko'p so'rov botni qotirmasin)
TTS_SEMAPHORE = asyncio.Semaphore(5)

# Throttling: bir foydalanuvchi 1.5 soniyada ko'p so'rov yubormasin
_last_request: dict[int, float] = {}
THROTTLE_SECONDS = 1.5


async def throttling_middleware(handler, event, data: dict):
    """Foydalanuvchi so'rovlar tezligini cheklaydi (anti-spam)."""
    user = event.from_user
    if user is None:
        return await handler(event, data)

    now = asyncio.get_event_loop().time()
    last = _last_request.get(user.id, 0)
    if now - last < THROTTLE_SECONDS:
        # Juda tez — e'tiborsiz qoldiramiz
        logger.debug(f"Throttled: user {user.id}")
        return
    _last_request[user.id] = now

    # Keshni tozalash (eski yozuvlar)
    if len(_last_request) > 10000:
        cutoff = now - 300
        for uid in [k for k, v in _last_request.items() if v < cutoff]:
            del _last_request[uid]

    return await handler(event, data)


# =============================================
# HANDLERLAR
# =============================================

dp = Dispatcher(storage=MemoryStorage())
dp.message.middleware(throttling_middleware)
dp.callback_query.middleware(throttling_middleware)
dp.inline_query.middleware(throttling_middleware)


@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """/start — professional bosh menyu."""
    uid = message.from_user.id
    user_data[uid] = {"history": []}
    await state.set_state(Flow.ai_chat)

    # Foydalanuvchini bazaga qo'shamiz
    await db.get_settings(uid)

    # Bosh menyu
    await message.answer(
        clip(T.GREETING, 3900),
        parse_mode=ParseMode.HTML,
        reply_markup=build_main_menu(),
    )
    # Doimiy pastki tugmalar
    await message.answer(
        "— <i>Quyidagi tugmalar doim ko'rinib turadi</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=build_bottom_menu(),
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        T.HELP_HEADER + T.HELP_BODY,
        reply_markup=build_back_keyboard(),
        parse_mode=ParseMode.HTML,
    )


@dp.message(Command("history"))
async def cmd_history(message: Message):
    """/history — foydalanuvchining oxirgi matnlari."""
    uid = message.from_user.id
    history = await db.get_history(uid, limit=10)
    if not history:
        await message.answer(
            T.HISTORY_EMPTY,
            reply_markup=build_back_keyboard(),
            parse_mode=ParseMode.HTML,
        )
        return

    text = T.HISTORY_HEADER.format(count=len(history))
    await message.answer(
        text,
        reply_markup=build_history_keyboard(history),
        parse_mode=ParseMode.HTML,
    )


@dp.message(Command("reset"))
async def cmd_reset(message: Message, state: FSMContext):
    uid = message.from_user.id
    user_data[uid] = {"history": []}
    await state.set_state(Flow.ai_chat)
    await message.answer(T.RESET_DONE, parse_mode=ParseMode.HTML)


# =============================================
# PROFESSIONAL UI — menyular, tugmalar, katalog
# =============================================

# --- Tanlangan rejim (har bir foydalanuvchi uchun) ---
# "auto" | "tts" | "grandpa" | "script"
_user_mode: dict[int, str] = {}

MODE_LABELS = {
    "auto": "AI avtomatik",
    "tts": "Matn — Ovoz",
    "grandpa": "Keksa effekti",
    "script": "Senariy",
}

MODE_TEXTS = {
    "tts": T.MODE_TTS,
    "grandpa": T.MODE_GRANDPA,
    "script": T.MODE_SCRIPT,
    "auto": T.MODE_AI,
    "ai": T.MODE_AI,   # menyudagi "— AI rejimi" tugmasi
}


def get_mode(uid: int) -> str:
    """Foydalanuvchining tanlagan rejimini qaytaradi."""
    return _user_mode.get(uid, "auto")


def set_mode(uid: int, mode: str) -> None:
    _user_mode[uid] = mode


# --- Ovoz katalogi ---
# engine: gemini | openai | kokoro | fish
VOICE_CATALOG: list[dict] = [
    {"name": "💫 Kore · AI", "engine": "gemini", "id": "Kore",
     "gender": "female", "desc": "Gemini TTS — eng tabiiy, ifodali"},
    {"name": "🔊 Puck · AI", "engine": "gemini", "id": "Puck",
     "gender": "male", "desc": "Gemini TTS — yosh, quvnoq"},
    {"name": "🎭 Fenrir · AI", "engine": "gemini", "id": "Fenrir",
     "gender": "male", "desc": "Gemini TTS — chuqur, kuchli"},
    {"name": "🌸 Aoede · AI", "engine": "gemini", "id": "Aoede",
     "gender": "female", "desc": "Gemini TTS — yumshoq, iliq"},
    {"name": "🧔 Alloy · AI", "engine": "openai", "id": "alloy",
     "gender": "male", "desc": "OpenAI TTS — aniq, zamonaviy"},
    {"name": "🌊 Nova · AI", "engine": "openai", "id": "nova",
     "gender": "female", "desc": "OpenAI TTS — energiya bilan to'ldirilgan"},
    {"name": "✨ Shimmer · AI", "engine": "openai", "id": "shimmer",
     "gender": "female", "desc": "OpenAI TTS — yumshoq, tabiiy"},
    {"name": "🗿 Onyx · AI", "engine": "openai", "id": "onyx",
     "gender": "male", "desc": "OpenAI TTS — qattiq, ishonchli"},
    {"name": "🧔 Erkak · Rasmiy", "engine": "kokoro", "id": "am_michael",
     "gender": "male", "desc": "Aniq, rasmiy, ishonchli"},
    {"name": "👨 Erkak · Tabiiy", "engine": "kokoro", "id": "am_liam",
     "gender": "male", "desc": "Yumshoq, tabiiy, samimiy"},
    {"name": "🧑 Erkak · Chuqur", "engine": "kokoro", "id": "am_adam",
     "gender": "male", "desc": "Chuqur, ziddiyatli"},
    {"name": "🧔 Erkak · Do'stona", "engine": "kokoro", "id": "am_eric",
     "gender": "male", "desc": "Do'stona, iliq"},
    {"name": "👩 Ayol · Tabiiy", "engine": "kokoro", "id": "af_heart",
     "gender": "female", "desc": "Tabiiy, iliq, tinch"},
    {"name": "👩‍🦰 Ayol · Ekspressiv", "engine": "kokoro", "id": "af_bella",
     "gender": "female", "desc": "Jonli, ekspressiv"},
    {"name": "🧘 Ayol · Sokin", "engine": "kokoro", "id": "af_nicole",
     "gender": "female", "desc": "Sokin, meditativ"},
    {"name": "👩 Ayol · Suhbatdosh", "engine": "kokoro", "id": "af_sarah",
     "gender": "female", "desc": "Yangi, suhbatdosh"},
    {"name": "🧒 Bola · Yosh", "engine": "kokoro", "id": "am_puck",
     "gender": "child", "desc": "Yosh, quvnoq, serb"},
    {"name": "👶 Bola · Ilhom", "engine": "kokoro", "id": "af_nova",
     "gender": "child", "desc": "Yumshoq, ilhomlantiruvchi"},
    {"name": "👴 Keksa · Chuqur", "engine": "kokoro", "id": "am_echo",
     "gender": "grandpa", "desc": "Chuqur, keksa, donish"},
    {"name": "👴 Keksa · Hikoyachi", "engine": "kokoro", "id": "bm_george",
     "gender": "grandpa", "desc": "Hikoyachi, ko'ngilli"},
    {"name": "🇺🇿 O'zbek · Erkak", "engine": "fish",
     "id": "44ad146afad04e4e99a7b98b8f97106f", "gender": "male",
     "desc": "Fish Audio — kirill moslash, to'g'ri o'zbek talaffuzi"},
    {"name": "🇺🇿 O'zbek · Ayol", "engine": "fish",
     "id": "933563129e564b19a115bedd57b7406a", "gender": "female",
     "desc": "Fish Audio — kirill moslash, to'g'ri o'zbek talaffuzi"},
]

VOICE_SAMPLE = "Salom! Men sizning ovoz yordamchingizman. Bugun nima qilamiz?"


# --- Klaviaturalar ---

def build_main_menu() -> InlineKeyboardMarkup:
    """Bosh menyu — asosiy inline tugmalar (2 ustunli)."""
    rows: list[list[InlineKeyboardButton]] = []
    buttons = T.MAIN_MENU_BUTTONS
    for i in range(0, len(buttons), 2):
        chunk = buttons[i:i + 2]
        rows.append([
            InlineKeyboardButton(text=label, callback_data=action)
            for label, action in chunk
        ])
    rows.append([
        InlineKeyboardButton(text=T.BTN_HOME, callback_data="menu:home"),
        InlineKeyboardButton(text=T.BTN_CLOSE, callback_data="menu:close"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_bottom_menu() -> ReplyKeyboardMarkup:
    """Pastki menyu — doimiy ko'rinadigan tugmalar."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=T.BOTTOM_TTS), KeyboardButton(text=T.BOTTOM_STT)],
            [KeyboardButton(text=T.BOTTOM_GRANDPA), KeyboardButton(text=T.BOTTOM_SCRIPT)],
            [KeyboardButton(text=T.BOTTOM_SETTINGS), KeyboardButton(text=T.BOTTOM_HELP)],
        ],
        resize_keyboard=True,
        input_field_placeholder=T.BOTTOM_PLACEHOLDER,
    )


def build_back_keyboard() -> InlineKeyboardMarkup:
    """Faqat bosh menyuga qaytish tugmasi."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=T.BTN_HOME, callback_data="menu:home")],
    ])


def build_voice_catalog() -> InlineKeyboardMarkup:
    """Ovoz katalogi — 2 ustunli to'r."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for idx, voice in enumerate(VOICE_CATALOG):
        row.append(
            InlineKeyboardButton(text=voice["name"], callback_data=f"vprev:{idx}")
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([
        InlineKeyboardButton(text=T.BTN_HOME, callback_data="menu:home"),
        InlineKeyboardButton(text=T.BTN_CLOSE, callback_data="menu:close"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_history_keyboard(history: list[str]) -> InlineKeyboardMarkup:
    """Tarix — har bir matn uchun tugma."""
    rows: list[list[InlineKeyboardButton]] = []
    for idx, text in enumerate(history):
        label = clip(text, 28) or "(bo'sh)"
        rows.append([
            InlineKeyboardButton(text=f"— {label}", callback_data=f"hist:{idx}")
        ])
    rows.append([
        InlineKeyboardButton(text="— Tozalash", callback_data="menu:clear_history"),
        InlineKeyboardButton(text=T.BTN_HOME, callback_data="menu:home"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# --- Matnlar ---

async def home_text(uid: int) -> str:
    """Bosh menyu matni (joriy rejim va til bilan)."""
    s = await db.get_settings(uid)
    mode = MODE_LABELS.get(get_mode(uid), MODE_LABELS["auto"])
    lang = LANG_LABELS.get(s["language"], s["language"])
    return (
        T.MAIN_TITLE
        + T.MAIN_SUBTITLE + "\n\n"
        + f"— Rejim: <b>{mode}</b>\n"
        + f"— Til: <b>{lang}</b>"
    )


async def stats_text(uid: int) -> str:
    """Foydalanuvchi statistikasi."""
    s = await db.get_settings(uid)
    today, total = await db.get_user_usage(uid)
    hist = await db.get_user_history_count(uid)
    return (
        T.STATS_HEADER
        + T.STATS_CARD.format(
            today=today,
            total=total,
            history=hist,
            lang=LANG_LABELS.get(s["language"], s["language"]),
            voice=GENDER_LABELS_UI.get(s["voice_gender"], s["voice_gender"]),
            speed=SPEED_LABELS.get(s["speed"], s["speed"]),
        )
    )


# --- Rejimni o'zgartirish ---

async def apply_mode(uid: int, mode: str) -> str:
    """Rejimni o'zgartiradi va foydalanuvchiga xabar beradi."""
    if mode == "ai":
        mode = "auto"
    set_mode(uid, mode)
    return MODE_TEXTS.get(mode, T.MODE_AI)


# --- Ovoz namunasi ---

async def preview_voice(entry: dict) -> bytes | None:
    """Ovoz namunasini yaratadi (tanlangan dvigatel bilan)."""
    engine = entry.get("engine")
    if engine == "gemini":
        audio = await gemini_tts(VOICE_SAMPLE, entry["id"], "uz")
    elif engine == "openai":
        audio = await openai_tts(VOICE_SAMPLE, entry["id"], "uz")
    elif engine == "fish":
        audio = await fish_audio_tts(VOICE_SAMPLE, entry["id"], lang="uz", speed=1.0)
    else:
        audio = await kokoro_tts(VOICE_SAMPLE, entry["id"])
    if not audio:
        # Zaxira: Edge TTS
        audio = await edge_tts_speak(
            VOICE_SAMPLE, get_edge_voice("uz", entry.get("gender", "male"))
        )
    return audio


@dp.callback_query(F.data.startswith("menu:"))
async def menu_callback(callback: CallbackQuery):
    """Bosh menyu tugmalari boshqaruvi."""
    action = callback.data.split(":", 1)[1]
    uid = callback.from_user.id
    await callback.answer()

    if action == "close":
        await safe_edit(
            callback.message,
            "— Yopildi. <i>/start</i> — qayta ochish.",
            parse_mode=ParseMode.HTML,
        )
        return

    if action == "home":
        await safe_edit(
            callback.message,
            await home_text(uid),
            reply_markup=build_main_menu(),
            parse_mode=ParseMode.HTML,
        )
        return

    if action in MODE_TEXTS:
        text = await apply_mode(uid, action)
        await safe_edit(
            callback.message, text,
            reply_markup=build_back_keyboard(),
            parse_mode=ParseMode.HTML,
        )
        return

    if action == "stt":
        await safe_edit(
            callback.message, T.MODE_STT,
            reply_markup=build_back_keyboard(),
            parse_mode=ParseMode.HTML,
        )
        return

    if action == "voices":
        await safe_edit(
            callback.message, T.VOICE_CATALOG_HEADER,
            reply_markup=build_voice_catalog(),
            parse_mode=ParseMode.HTML,
        )
        return

    if action == "history":
        history = await db.get_history(uid, limit=10)
        if not history:
            await safe_edit(
                callback.message, T.HISTORY_EMPTY,
                reply_markup=build_back_keyboard(),
                parse_mode=ParseMode.HTML,
            )
            return
        text = T.HISTORY_HEADER.format(count=len(history))
        await safe_edit(
            callback.message, text,
            reply_markup=build_history_keyboard(history),
            parse_mode=ParseMode.HTML,
        )
        return

    if action == "clear_history":
        await db.clear_history(uid)
        user_data[uid] = {"history": []}
        await safe_edit(
            callback.message, T.HISTORY_CLEARED,
            reply_markup=build_back_keyboard(),
            parse_mode=ParseMode.HTML,
        )
        return

    if action == "settings":
        text = await settings_summary(uid)
        await safe_edit(
            callback.message, text,
            reply_markup=build_settings_keyboard(),
            parse_mode=ParseMode.HTML,
        )
        return

    if action == "stats":
        await safe_edit(
            callback.message, await stats_text(uid),
            reply_markup=build_back_keyboard(),
            parse_mode=ParseMode.HTML,
        )
        return

    if action == "help":
        await safe_edit(
            callback.message, T.HELP_HEADER + T.HELP_BODY,
            reply_markup=build_back_keyboard(),
            parse_mode=ParseMode.HTML,
        )
        return


@dp.callback_query(F.data.startswith("vprev:"))
async def voice_preview_callback(callback: CallbackQuery):
    """Ovoz namunasi: eshitish + tanlash."""
    uid = callback.from_user.id
    try:
        idx = int(callback.data.split(":", 1)[1])
    except ValueError:
        await callback.answer("— Ovoz topilmadi")
        return

    if idx < 0 or idx >= len(VOICE_CATALOG):
        await callback.answer("— Ovoz topilmadi")
        return

    entry = VOICE_CATALOG[idx]
    await callback.answer("— Namuna tayyorlanmoqda—")

    async with TTS_SEMAPHORE:
        audio = await preview_voice(entry)

    if not audio:
        await callback.message.answer(T.VOICE_PREVIEW_ERROR)
        return

    ogg = await mp3_to_ogg(audio)
    voice_file = (
        BufferedInputFile(ogg, filename="preview.ogg") if ogg
        else BufferedInputFile(audio, filename="preview.mp3")
    )
    await callback.message.answer_voice(
        voice=voice_file,
        caption=f"— <b>{entry['name']}</b>\n<i>{entry['desc']}</i>",
        parse_mode=ParseMode.HTML,
    )

    # Tanlaymiz
    await db.update_settings(
        uid, voice_id=entry["id"], voice_gender=entry.get("gender", "male")
    )
    await safe_edit(
        callback.message,
        T.VOICE_SELECTED.format(name=entry["name"], desc=entry["desc"]),
        reply_markup=build_back_keyboard(),
        parse_mode=ParseMode.HTML,
    )


@dp.callback_query(F.data.startswith("hist:"))
async def history_callback(callback: CallbackQuery):
    """Tarixdagi matnni qayta ovozga aylantiradi."""
    uid = callback.from_user.id
    await callback.answer("— Tayyorlanmoqda—")

    try:
        idx = int(callback.data.split(":", 1)[1])
    except ValueError:
        return

    history = await db.get_history(uid, limit=10)
    if idx < 0 or idx >= len(history):
        await callback.message.answer(T.HISTORY_EMPTY, parse_mode=ParseMode.HTML)
        return

    text = history[idx]
    processing = await callback.message.answer(T.STATUS_TTS, parse_mode=ParseMode.HTML)
    await run_pipeline(callback.message, text, processing, force="tts")


# --- Pastki menyu tugmalari ---
BOTTOM_ACTIONS = {
    T.BOTTOM_TTS: "tts",
    T.BOTTOM_GRANDPA: "grandpa",
    T.BOTTOM_SCRIPT: "script",
    T.BOTTOM_STT: "stt",
}


@dp.message(F.text.in_(list(BOTTOM_ACTIONS.keys())))
async def bottom_menu_handler(message: Message):
    """Pastki menyudagi tugmalar."""
    uid = message.from_user.id
    action = BOTTOM_ACTIONS.get((message.text or "").strip())
    if action is None:
        return

    if action == "stt":
        await message.answer(T.MODE_STT, parse_mode=ParseMode.HTML)
        return

    text = await apply_mode(uid, action)
    await message.answer(text, parse_mode=ParseMode.HTML)


@dp.message(F.text.in_([T.BOTTOM_SETTINGS]))
async def bottom_settings_handler(message: Message):
    """Pastki menyudagi sozlamalar tugmasi."""
    text = await settings_summary(message.from_user.id)
    await message.answer(
        text, reply_markup=build_settings_keyboard(), parse_mode=ParseMode.HTML
    )


@dp.message(F.text.in_([T.BOTTOM_HELP]))
async def bottom_help_handler(message: Message):
    """Pastki menyudagi yordam tugmasi."""
    await message.answer(
        T.HELP_HEADER + T.HELP_BODY,
        reply_markup=build_back_keyboard(),
        parse_mode=ParseMode.HTML,
    )


# =============================================
# /settings — sozlamalar (inline tugmalar)
# =============================================


def build_settings_keyboard() -> InlineKeyboardMarkup:
    """Sozlamalar uchun inline tugmalar klaviaturasi."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=T.CHOOSE_LANG, callback_data="settings:lang")],
        [InlineKeyboardButton(text=T.CHOOSE_VOICE, callback_data="settings:voice")],
        [InlineKeyboardButton(text=T.CHOOSE_SPEED, callback_data="settings:speed")],
        [
            InlineKeyboardButton(text=T.BTN_HOME, callback_data="menu:home"),
            InlineKeyboardButton(text=T.BTN_CLOSE, callback_data="menu:close"),
        ],
    ])


def _mark(label: str, code: str, current: str) -> str:
    """Joriy tanlovni — bilan belgilaydi."""
    return f"— {label}" if code == current else label


def build_lang_keyboard(current: str = "uz") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=_mark(T.BTN_LANG_UZ, "uz", current), callback_data="lang:uz"),
            InlineKeyboardButton(text=_mark(T.BTN_LANG_RU, "ru", current), callback_data="lang:ru"),
            InlineKeyboardButton(text=_mark(T.BTN_LANG_EN, "en", current), callback_data="lang:en"),
        ],
        [InlineKeyboardButton(text=T.BTN_BACK, callback_data="settings:refresh")],
    ])


def build_voice_keyboard(current: str = "male") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=_mark(T.BTN_VOICE_MALE, "male", current), callback_data="voice:male"),
            InlineKeyboardButton(text=_mark(T.BTN_VOICE_FEMALE, "female", current), callback_data="voice:female"),
        ],
        [
            InlineKeyboardButton(text="— Barcha ovozlar", callback_data="menu:voices"),
            InlineKeyboardButton(text=T.BTN_BACK, callback_data="settings:refresh"),
        ],
    ])


def build_speed_keyboard(current: str = "normal") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=_mark(T.BTN_SPEED_SLOW, "slow", current), callback_data="speed:slow"),
            InlineKeyboardButton(text=_mark(T.BTN_SPEED_NORMAL, "normal", current), callback_data="speed:normal"),
            InlineKeyboardButton(text=_mark(T.BTN_SPEED_FAST, "fast", current), callback_data="speed:fast"),
        ],
        [InlineKeyboardButton(text=T.BTN_BACK, callback_data="settings:refresh")],
    ])


async def settings_summary(user_id: int) -> str:
    """Foydalanuvchining hozirgi sozlamalari haqida matn qaytaradi."""
    s = await db.get_settings(user_id)

    # Tanlangan aniq ovoz katalogda bormi?
    voice_name = GENDER_LABELS_UI.get(s["voice_gender"], s["voice_gender"])
    vid = s.get("voice_id") or ""
    for v in VOICE_CATALOG:
        if v["id"] == vid:
            voice_name = v["name"]
            break

    return T.SETTINGS_HEADER + "\n\n" + T.SETTINGS_SUMMARY.format(
        lang=LANG_LABELS.get(s["language"], s["language"]),
        voice=voice_name,
        speed=SPEED_LABELS.get(s["speed"], s["speed"]),
    )


@dp.message(Command("settings"))
async def cmd_settings(message: Message):
    """/settings — sozlamalarni ko'rsatish."""
    text = await settings_summary(message.from_user.id)
    await message.answer(text, reply_markup=build_settings_keyboard(), parse_mode=ParseMode.HTML)


@dp.callback_query(F.data.startswith("settings:"))
async def settings_callback(callback: CallbackQuery):
    """Sozlamalar tugmalari boshqaruvi."""
    uid = callback.from_user.id
    action = callback.data.split(":", 1)[1]
    s = await db.get_settings(uid)

    if action == "lang":
        text = await settings_summary(uid) + "\n\n" + T.CHOOSE_LANG
        await safe_edit(
            callback.message, text,
            reply_markup=build_lang_keyboard(s["language"]),
            parse_mode=ParseMode.HTML,
        )
    elif action == "voice":
        text = await settings_summary(uid) + "\n\n" + T.CHOOSE_VOICE
        await safe_edit(
            callback.message, text,
            reply_markup=build_voice_keyboard(s["voice_gender"]),
            parse_mode=ParseMode.HTML,
        )
    elif action == "speed":
        text = await settings_summary(uid) + "\n\n" + T.CHOOSE_SPEED
        await safe_edit(
            callback.message, text,
            reply_markup=build_speed_keyboard(s["speed"]),
            parse_mode=ParseMode.HTML,
        )
    elif action == "refresh":
        text = await settings_summary(uid)
        await safe_edit(
            callback.message, text,
            reply_markup=build_settings_keyboard(),
            parse_mode=ParseMode.HTML,
        )

    await callback.answer()


@dp.callback_query(F.data.startswith("lang:"))
async def lang_callback(callback: CallbackQuery):
    """Til tanlash."""
    uid = callback.from_user.id
    lang = callback.data.split(":", 1)[1]
    if lang in db.VALID_LANGUAGES:
        await db.update_settings(uid, language=lang)
        text = T.SETTINGS_LANG_SET.format(lang=LANG_LABELS.get(lang, lang)) + "\n\n"
        text += await settings_summary(uid)
        await safe_edit(
            callback.message, text,
            reply_markup=build_settings_keyboard(),
            parse_mode=ParseMode.HTML,
        )
    await callback.answer()


@dp.callback_query(F.data.startswith("voice:"))
async def voice_callback(callback: CallbackQuery):
    """Ovoz tanlash (erkak/ayol)."""
    uid = callback.from_user.id
    gender = callback.data.split(":", 1)[1]
    if gender in db.VALID_GENDERS:
        # Jins o'zgarganda katalogdagi aniq ovoz tozalanadi
        await db.update_settings(uid, voice_gender=gender, voice_id="")
        text = T.SETTINGS_VOICE_SET.format(voice=GENDER_LABELS_UI.get(gender, gender)) + "\n\n"
        text += await settings_summary(uid)
        await safe_edit(
            callback.message, text,
            reply_markup=build_settings_keyboard(),
            parse_mode=ParseMode.HTML,
        )
    await callback.answer()


@dp.callback_query(F.data.startswith("speed:"))
async def speed_callback(callback: CallbackQuery):
    """Tezlik tanlash."""
    uid = callback.from_user.id
    speed = callback.data.split(":", 1)[1]
    if speed in db.VALID_SPEEDS:
        await db.update_settings(uid, speed=speed)
        text = T.SETTINGS_SPEED_SET.format(speed=SPEED_LABELS.get(speed, speed)) + "\n\n"
        text += await settings_summary(uid)
        await safe_edit(
            callback.message, text,
            reply_markup=build_settings_keyboard(),
            parse_mode=ParseMode.HTML,
        )
    await callback.answer()


# =============================================
# ADMIN PANEL (faqat ADMIN_IDS uchun)
# Matn handlerlaridan OLDIN — aks holda
# broadcast rejimi ishlamaydi (aiogram tartibi).
# =============================================


def is_admin(user_id: int) -> bool:
    """Foydalanuvchi adminmi?"""
    return user_id in ADMIN_IDS


def build_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="— Statistika", callback_data="admin:stats"),
            InlineKeyboardButton(text="— Broadcast", callback_data="admin:broadcast"),
        ],
    ])


async def admin_stats_text() -> str:
    users = await db.get_total_users()
    today = await db.get_today_requests()
    total = await db.get_total_requests()
    return (
        T.ADMIN_HEADER + "\n"
        + T.ADMIN_STATS.format(users=users, today=today, total=total)
    )


@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    """/admin — admin panel (faqat adminlar uchun)."""
    if not is_admin(message.from_user.id):
        await message.answer(T.ERR_NOT_ADMIN)
        return
    await message.answer(
        await admin_stats_text(),
        reply_markup=build_admin_keyboard(),
        parse_mode=ParseMode.HTML,
    )


@dp.message(Command("diag"))
async def cmd_diag(message: Message):
    """/diag — TTS dvigatellarini tekshirish (faqat adminlar uchun)."""
    if not is_admin(message.from_user.id):
        await message.answer(T.ERR_NOT_ADMIN)
        return

    import edge_tts as _et
    lines = [f"— <b>Diagnostics</b>", f"edge-tts: {_et.__version__}", ""]

    # 1) Edge TTS
    try:
        audio = await edge_tts_speak("Sinov.", "uz-UZ-SardorNeural", retries=0)
        lines.append(
            f"Edge TTS: — {len(audio)} bayt" if audio else "Edge TTS: — audio yo'q"
        )
    except Exception as e:
        lines.append(f"Edge TTS: — {type(e).__name__}: {str(e)[:200]}")

    # 2) Kokoro
    try:
        audio = await kokoro_tts("Sinov.")
        lines.append(
            f"Kokoro: — {len(audio)} bayt" if audio else "Kokoro: — ishlamadi (Space uxlayapti?)"
        )
    except Exception as e:
        lines.append(f"Kokoro: — {type(e).__name__}: {str(e)[:200]}")

    # 3) Fish Audio
    try:
        audio = await fish_audio_tts("Sinov.", None)
        lines.append(
            f"Fish Audio: — {len(audio)} bayt" if audio else "Fish Audio: — ishlamadi"
        )
    except Exception as e:
        lines.append(f"Fish Audio: — {type(e).__name__}: {str(e)[:200]}")

    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)


@dp.callback_query(F.data.startswith("admin:"))
async def admin_callback(callback: CallbackQuery, state: FSMContext):
    """Admin tugmalari boshqaruvi."""
    if not is_admin(callback.from_user.id):
        await callback.answer(T.ERR_NOT_ADMIN, show_alert=True)
        return

    action = callback.data.split(":", 1)[1]

    if action == "stats":
        await callback.message.edit_text(
            await admin_stats_text(),
            reply_markup=build_admin_keyboard(),
            parse_mode=ParseMode.HTML,
        )

    elif action == "broadcast":
        # Broadcast rejimiga o'tamiz
        await state.set_state(Flow.broadcast)
        await callback.message.edit_text(
            T.ADMIN_BROADCAST_PROMPT,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="— Bekor qilish", callback_data="admin:cancel")],
            ]),
            parse_mode=ParseMode.HTML,
        )

    elif action == "cancel":
        await state.set_state(Flow.ai_chat)
        await callback.message.edit_text(
            T.ADMIN_CANCELLED,
            reply_markup=build_admin_keyboard(),
            parse_mode=ParseMode.HTML,
        )

    await callback.answer()


@dp.message(Flow.broadcast)
async def broadcast_handler(message: Message, state: FSMContext):
    """Broadcast rejimida kelgan matnni barcha foydalanuvchilarga yuboradi."""
    if not is_admin(message.from_user.id):
        await state.set_state(Flow.ai_chat)
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer(T.ERR_EMPTY_TEXT)
        return

    user_ids = await db.get_all_user_ids()
    await message.answer(
        T.ADMIN_BROADCAST_START.format(count=len(user_ids)),
        parse_mode=ParseMode.HTML,
    )

    sent = 0
    for uid in user_ids:
        try:
            await message.bot.send_message(uid, text)
            sent += 1
        except Exception as e:
            logger.debug(f"Broadcast xatosi (user {uid}): {e}")
        # Telegram limitiga tushmaslik uchun kichik pauza
        await asyncio.sleep(0.05)

    await state.set_state(Flow.ai_chat)
    await message.answer(
        T.ADMIN_BROADCAST_DONE.format(sent=sent, total=len(user_ids)),
        parse_mode=ParseMode.HTML,
    )


@dp.message(F.voice | F.audio)
async def voice_message_handler(message: Message, state: FSMContext):
    """Ovozli xabar -> Gemini STT -> matnga aylantirib, AI oqimiga beradi."""
    await state.set_state(Flow.ai_chat)

    tg_file = message.voice or message.audio
    duration = tg_file.duration or 0
    if duration > MAX_VOICE_SECONDS:
        await message.answer(
            T.ERR_VOICE_TOO_LONG.format(duration=duration, max=MAX_VOICE_SECONDS)
        )
        return

    processing = await message.answer(T.STATUS_VOICE_HEARING, parse_mode=ParseMode.HTML)
    tmp_path = TMP_DIR / f"stt_{uuid.uuid4().hex[:12]}.ogg"

    try:
        file = await message.bot.get_file(tg_file.file_id)
        await message.bot.download_file(file.file_path, destination=str(tmp_path))
        audio_bytes = tmp_path.read_bytes()
        mime_type = "audio/ogg" if message.voice else "audio/mpeg"

        await safe_edit(processing, T.STATUS_TRANSCRIBING, parse_mode=ParseMode.HTML)
        transcript = await stt_transcribe(audio_bytes, mime_type)

        if not transcript:
            await safe_edit(
                processing,
                "— Ovozdan matn topilmadim.\nIltimos, aniqroq va yaqinroq gapiring.",
            )
            return

        cleaned = (await improve_prompt(transcript, mode="stt")).strip() or transcript
        logger.info(f"STT natija: {cleaned[:100]}")

    finally:
        # Vaqtinchalik faylni o'chirish
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass

    await typing(message)
    await safe_edit(processing, T.TRANSCRIPT.format(text=clip(cleaned, 500)))
    await run_pipeline(message, cleaned, processing)


# =============================================
# FAYL O'QISH (.txt / .pdf / .docx)
# =============================================

SUPPORTED_EXTS = {".txt", ".pdf", ".docx"}


def extract_document_text(path: Path, ext: str) -> str | None:
    """Fayldan matnni o'qiydi (.txt, .pdf, .docx). Xatolikda None qaytaradi."""
    try:
        if ext == ".txt":
            raw = path.read_bytes()
            # Kodlashni avtomatik aniqlaymiz (o'zbek matn ko'pincha UTF-8)
            for enc in ("utf-8", "utf-8-sig", "cp1251", "latin-1"):
                try:
                    return raw.decode(enc)
                except (UnicodeDecodeError, LookupError):
                    continue
            return None

        if ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            parts: list[str] = []
            for page in reader.pages[:100]:  # 100 sahifagacha
                try:
                    t = page.extract_text() or ""
                except Exception:
                    continue
                if t.strip():
                    parts.append(t.strip())
            return "\n\n".join(parts)

        if ext == ".docx":
            from docx import Document
            doc = Document(str(path))
            parts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            # Jadval matnlarini ham olamiz
            for table in doc.tables:
                for row in table.rows:
                    cells = [c.text.strip() for c in row.cells if c.text.strip()]
                    if cells:
                        parts.append(" | ".join(cells))
            return "\n".join(parts)

    except Exception as e:
        logger.error(f"Fayl o'qish xatosi ({ext}): {e}")
        return None
    return None


@dp.message(F.document)
async def document_handler(message: Message, state: FSMContext):
    """Fayl o'qish: .txt, .pdf, .docx -> matnga aylantirib AI oqimiga beradi."""
    await state.set_state(Flow.ai_chat)

    doc = message.document
    if doc is None:
        return

    name = (doc.file_name or "").lower()
    ext = Path(name).suffix

    if ext not in SUPPORTED_EXTS:
        await message.answer(T.ERR_FILE_TYPE, parse_mode=ParseMode.HTML)
        return

    size_mb = (doc.file_size or 0) / (1024 * 1024)
    if size_mb > FILE_SIZE_LIMIT_MB:
        await message.answer(
            T.ERR_FILE_TOO_BIG.format(size=round(size_mb, 1), max=FILE_SIZE_LIMIT_MB)
        )
        return

    processing = await message.answer(T.STATUS_FILE_READING, parse_mode=ParseMode.HTML)
    tmp_path = TMP_DIR / f"doc_{uuid.uuid4().hex[:12]}{ext}"

    try:
        file = await message.bot.get_file(doc.file_id)
        await message.bot.download_file(file.file_path, destination=str(tmp_path))

        text = await asyncio.to_thread(extract_document_text, tmp_path, ext)
        if not text or not text.strip():
            await safe_edit(processing, T.ERR_FILE_READ)
            return

        text = text.strip()
        # Fayldan o'qilgan matnni cheklab, oqimga beramiz
        if len(text) > MAX_TEXT_CHARS:
            text = text[:MAX_TEXT_CHARS]

        await safe_edit(
            processing,
            f"— <b>{doc.file_name}</b>\n{len(text)} belgi o'qildi. Davom etilmoqda...",
        )
        await run_pipeline(message, text, processing)

    except Exception as e:
        logger.error(f"Fayl handler xatosi: {e}", exc_info=True)
        await safe_edit(processing, T.ERR_FILE_READ)

    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass


@dp.message(F.text)
async def text_message_handler(message: Message, state: FSMContext):
    """AI suhbat rejimi — matn keladi, niyat aniqlanadi va bajariladi."""
    await state.set_state(Flow.ai_chat)

    text = (message.text or "").strip()
    if not text:
        return

    uid = message.from_user.id
    mode = get_mode(uid)

    processing = await message.answer(T.STATUS_THINKING, parse_mode=ParseMode.HTML)
    await run_pipeline(message, text, processing, force=mode)


@dp.message()
async def other_content_handler(message: Message):
    """Boshqa kontent turlari (stiker, rasm, hujjat...)."""
    await message.answer(T.NOT_UNDERSTOOD, parse_mode=ParseMode.HTML)


# =============================================
# INLINE REJIM (@bot matn — istalgan chatda ovoz)
# =============================================


def detect_lang_fast(text: str) -> str:
    """Tez til aniqlash (inline rejim uchun, API'siz)."""
    if re.search(r"[—-—-—]", text):
        return "ru"
    if (
        re.search(r"[oO]'|[gG]'|[—]", text)
        or re.search(
            r"\b(men|siz|biz|bu|va|uchun|ham|lekin|assalomu|salom|qanday|nima)\b",
            text, re.IGNORECASE,
        )
    ):
        return "uz"
    if re.search(
        r"\b(the|is|are|and|you|hello|this|that|for|with|what|how)\b",
        text, re.IGNORECASE,
    ):
        return "en"
    return "uz"


async def publish_audio(audio: bytes) -> str | None:
    """Audio faylni bepul hostga yuklab, to'g'ridan-to'g'ri URL qaytaradi.

    Inline rejimda Telegram ovoz uchun tashqi URL talab qiladi.
    1) catbox.moe (doimiy) — 2) uguu.se (1 soat) fallback.
    """
    filename = f"voice_{uuid.uuid4().hex[:8]}.mp3"
    timeout = aiohttp.ClientTimeout(total=40)

    # 1) catbox.moe
    try:
        form = aiohttp.FormData()
        form.add_field("reqtype", "fileupload")
        form.add_field("fileToUpload", audio, filename=filename, content_type="audio/mpeg")
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post("https://catbox.moe/user/api.php", data=form) as resp:
                if resp.status == 200:
                    url = (await resp.text()).strip()
                    if url.startswith("http"):
                        return url
    except Exception as e:
        logger.warning(f"catbox.moe yuklash xatosi: {e}")

    # 2) uguu.se (1 soat)
    try:
        form = aiohttp.FormData()
        form.add_field("reqtype", "fileupload")
        form.add_field("files[]", audio, filename=filename, content_type="audio/mpeg")
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post("https://uguu.se/upload.php", data=form) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("success") and data.get("files"):
                        return data["files"][0].get("url")
    except Exception as e:
        logger.warning(f"uguu.se yuklash xatosi: {e}")

    return None


def _inline_article(title: str, description: str, text: str) -> InlineQueryResultArticle:
    """Oddiy matn maqolasini qaytaradi (xatolik/holat uchun)."""
    return InlineQueryResultArticle(
        id=uuid.uuid4().hex,
        title=title,
        description=description,
        input_message_content=InputTextMessageContent(message_text=text),
    )


@dp.inline_query()
async def inline_handler(inline_query: InlineQuery):
    """Inline rejimi: har qanday chatda '@bot matn' — ovoz xabari paydo bo'ladi."""
    uid = inline_query.from_user.id
    text = (inline_query.query or "").strip()

    # Bo'sh so'rov — yordam ko'rsatamiz
    if not text:
        await inline_query.answer(
            results=[
                _inline_article(
                    "— Ovozga aylantirish",
                    "Matn yozing — ovoz yaratib beraman",
                    "Misol: @mp3speak_bot Salom dunyo",
                )
            ],
            cache_time=1,
            is_personal=True,
        )
        return

    # Inline so'rov uzunligi cheklangan (256 belgi)
    text = text[:256]

    # Kunlik limitni tekshiramiz
    if not await db.check_daily_limit(uid, DAILY_LIMIT):
        await inline_query.answer(
            results=[
                _inline_article(
                    "— Limit tugadi",
                    "Bugungi limit tugadi",
                    T.ERR_DAILY_LIMIT.format(limit=DAILY_LIMIT),
                )
            ],
            cache_time=60,
            is_personal=True,
        )
        return

    # Foydalanuvchi sozlamalari + tez til aniqlash
    settings = await db.get_settings(uid)
    lang = detect_lang_fast(text)
    rate = EDGE_TTS_RATES.get(settings["speed"], "+0%")

    # Katalogdan tanlangan aniq ovoz (agar bo'lsa) — ustunlikka ega
    sel_id, sel_engine = selected_voice(settings)
    engine_label = "Edge TTS"

    async with TTS_SEMAPHORE:
        if sel_engine == "kokoro":
            engine_label = "Kokoro TTS"
            audio = await kokoro_tts(text, sel_id)
        elif sel_engine == "fish":
            engine_label = "Fish Audio"
            audio = await fish_audio_tts(
                text, sel_id, lang=lang,
                speed=FISH_SPEEDS.get(settings["speed"], 1.0),
            )
        else:
            voice = EDGE_TTS_VOICES.get(lang, EDGE_TTS_VOICES["uz"]).get(
                settings["voice_gender"], "uz-UZ-SardorNeural"
            )
            # Edge TTS — tez, ~0.5-1s
            audio = await edge_tts_speak(text, voice, rate=rate)

    if not audio:
        await inline_query.answer(
            results=[
                _inline_article(
                    "— Xatolik",
                    "Ovoz yaratib bo'lmadi",
                    T.ERR_NO_VOICE,
                )
            ],
            cache_time=60,
            is_personal=True,
        )
        return

    # URL olish uchun yuklaymiz
    url = await publish_audio(audio)
    if not url:
        await inline_query.answer(
            results=[
                _inline_article(
                    "— Xatolik",
                    "Audio host ishlamayapti",
                    T.ERR_NO_VOICE,
                )
            ],
            cache_time=60,
            is_personal=True,
        )
        return

    result = InlineQueryResultVoice(
        id=uuid.uuid4().hex,
        voice=url,
        caption=T.TTS_DONE.format(
            engine=engine_label, lang=lang.upper(), chars=len(text)
        ),
    )
    await inline_query.answer(
        results=[result], cache_time=3600, is_personal=True
    )

    # Hisobni yuritamiz
    await db.add_history(uid, text)
    await db.increment_usage(uid)


# =============================================
# ISHGA TUSHIRISH
# =============================================


async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN topilmadi! .env faylni tekshiring.")
        return
    if not GEMINI_API_KEY:
        logger.warning("MIYYA_API_KEY topilmadi — AI funksiyalar (chat/STT/intent) ishlamaydi.")
    if not OPENROUTER_API_KEY:
        logger.warning("OPENROUTER_API_KEY topilmadi — Fish Audio TTS ishlamaydi.")
    if not OPENROUTER_THINKING_KEY:
        logger.warning("OPENROUTER_THINKING_KEY topilmadi — matnni tayyorlash o'tkaziladi.")
    if not GTTS_AVAILABLE:
        logger.warning("gTTS o'rnatilmagan — TTS faqat Edge/Kokoro/Fish Audio orqali ishlaydi.")

    # Bazani ishga tushiramiz
    await db.init_db()

    bot = Bot(token=BOT_TOKEN)
    logger.info("AI Ovoz Bot ishga tushdi!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
