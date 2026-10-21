// GitHub Actions secrets uchun NaCl sealed-box (libsodium crypto_box_seal)
// node seal.js <recipient_pubkey_base64> <plaintext_file> <out_file>
const fs = require("fs");
const path = require("path");

// libsodium-wrappers npm paketi (temporaly papkaga o'rnatilgan)
const sodium = require(
  path.join(
    process.env.APPDATA || "",
    "..",
    "Local",
    "Temp",
    "opencode",
    "nacl",
    "node_modules",
    "libsodium-wrappers"
  )
);

sodium.ready.then(() => {
  const [, , pubB64, plainFile, outFile] = process.argv;
  if (!pubB64 || !plainFile || !outFile) {
    console.error("Foydalanish: node seal.js <pub_b64> <plain_file> <out_file>");
    process.exit(1);
  }

  const recipientRaw = Buffer.from(pubB64, "base64");
  if (recipientRaw.length !== sodium.crypto_box_PUBLICKEYBYTES) {
    console.error("Kalit uzunligi noto'g'ri: " + recipientRaw.length);
    process.exit(1);
  }

  const plaintext = fs.readFileSync(plainFile);
  const sealed = sodium.crypto_box_seal(plaintext, recipientRaw);
  fs.writeFileSync(outFile, Buffer.from(sealed).toString("base64"));
  console.log("OK " + sealed.length + " bayt");
}).catch((e) => {
  console.error("XATO: " + e.message);
  process.exit(1);
});
