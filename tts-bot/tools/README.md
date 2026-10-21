# tools/ — yordamchi skriptlar

## seal.js
GitHub Actions secrets uchun NaCl sealed-box shifrlash (libsodium crypto_box_seal).
libsodium-wrappers npm paketi kerak:
`
npm install libsodium-wrappers
`

## set_secrets.ps1
.env dagi kalitlarni GitHub Actions secrets sifatida shifrlab qo'yadi:
`
powershell -ExecutionPolicy Bypass -File tools\set_secrets.ps1 kot
`
(repo nomi: kot yoki 	ts-bot)

Qaysi secretlar qo'yiladi: BOT_TOKEN, MIYYA_API_KEY, OPENROUTER_API_KEY,
OPENROUTER_THINKING_KEY, HF_TOKEN
