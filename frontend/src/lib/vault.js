// On-device encryption vault: Argon2id key derivation + XChaCha20-Poly1305.
//
// The key exists only in memory after unlock. Disk holds the salt and a
// sentinel ciphertext (for passphrase verification) — both useless alone.
// Hard wipe deletes the salt: the key becomes underivable even with the
// passphrase, so every ciphertext is instantly unrecoverable (crypto-erase).

// The "-sumo" build, NOT the default "libsodium-wrappers". Argon2id
// (crypto_pwhash) is only compiled into sumo; the stripped default build leaves
// every crypto_pwhash_* export undefined, so key derivation fails at the first
// randombytes_buf(SALTBYTES) with "length can't be undefined/null".
import _sodium from "libsodium-wrappers-sumo";

const SALT_KEY = "nucleus.vault.salt";
const SENTINEL_KEY = "nucleus.vault.sentinel";
const SENTINEL_VALUE = "nucleus-vault-v1";

let sodium = null;
let key = null;

async function ready() {
  if (!sodium) {
    await _sodium.ready;
    sodium = _sodium;
  }
  return sodium;
}

function deriveKey(passphrase, salt) {
  return sodium.crypto_pwhash(
    sodium.crypto_aead_xchacha20poly1305_ietf_KEYBYTES,
    passphrase,
    salt,
    sodium.crypto_pwhash_OPSLIMIT_INTERACTIVE,
    sodium.crypto_pwhash_MEMLIMIT_INTERACTIVE,
    sodium.crypto_pwhash_ALG_ARGON2ID13
  );
}

function encryptString(plaintext) {
  const nonce = sodium.randombytes_buf(
    sodium.crypto_aead_xchacha20poly1305_ietf_NPUBBYTES
  );
  const cipher = sodium.crypto_aead_xchacha20poly1305_ietf_encrypt(
    plaintext, null, null, nonce, key
  );
  const packed = new Uint8Array(nonce.length + cipher.length);
  packed.set(nonce);
  packed.set(cipher, nonce.length);
  return sodium.to_base64(packed);
}

function decryptString(packedB64) {
  const packed = sodium.from_base64(packedB64);
  const nonceLen = sodium.crypto_aead_xchacha20poly1305_ietf_NPUBBYTES;
  const plain = sodium.crypto_aead_xchacha20poly1305_ietf_decrypt(
    null, packed.slice(nonceLen), null, packed.slice(0, nonceLen), key
  );
  return sodium.to_string(plain);
}

export async function vaultStatus() {
  await ready();
  if (key) return "unlocked";
  return localStorage.getItem(SALT_KEY) ? "locked" : "new";
}

export async function setupVault(passphrase) {
  await ready();
  const salt = sodium.randombytes_buf(sodium.crypto_pwhash_SALTBYTES);
  key = deriveKey(passphrase, salt);
  localStorage.setItem(SALT_KEY, sodium.to_base64(salt));
  localStorage.setItem(SENTINEL_KEY, encryptString(SENTINEL_VALUE));
}

export async function unlockVault(passphrase) {
  await ready();
  const saltB64 = localStorage.getItem(SALT_KEY);
  if (!saltB64) throw new Error("No vault exists — set a passphrase first");
  const candidate = deriveKey(passphrase, sodium.from_base64(saltB64));
  const previous = key;
  key = candidate;
  try {
    decryptString(localStorage.getItem(SENTINEL_KEY));
  } catch {
    key = previous;
    throw new Error("Wrong passphrase");
  }
}

export function lockVault() {
  key = null;
}

export function isUnlocked() {
  return key !== null;
}

export function encryptJSON(value) {
  if (!key) throw new Error("Vault is locked");
  return encryptString(JSON.stringify(value));
}

export function decryptJSON(ciphertext) {
  if (!key) throw new Error("Vault is locked");
  return JSON.parse(decryptString(ciphertext));
}

// Crypto-erase: without the salt the key can never be re-derived, so all
// remaining ciphertext (and any disk residue of it) is permanently dead.
export function destroyVaultKey() {
  key = null;
  localStorage.removeItem(SALT_KEY);
  localStorage.removeItem(SENTINEL_KEY);
}
