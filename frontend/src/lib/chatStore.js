// Encrypted client-side persistence (IndexedDB + vault crypto).
//
// Three responsibilities:
//   1. Chat threads survive refresh / tab-switch — restored after vault unlock.
//      Every past thread can be resumed; a new thread starts clean.
//   2. Response cache: identical (mode + query) is served locally, no API call.
//   3. Vector store for the MEDEVAC context index (vectors derive from chat
//      content, so they are encrypted like everything else).
//
// Every value is XChaCha20-Poly1305 ciphertext; IndexedDB never sees plaintext.
// Soft wipe clears all data but keeps the vault. Hard wipe also destroys the
// vault salt — crypto-erase, nothing is recoverable.

import { encryptJSON, decryptJSON, destroyVaultKey } from "./vault";

const DB_NAME = "nucleus";
const DB_VERSION = 4;
const TRANSCRIPT_STORE = "transcript"; // legacy single-transcript store (migrated)
const THREADS_STORE = "threads";
const CACHE_STORE = "responseCache";
const VECTOR_STORE = "vectors";
const PRIVACY_STORE = "privacyLog";
const TRANSCRIPT_KEY = "current";

// Threads that predate multi-thread storage migrate under this id, so their
// vectors (which carry no threadId) can still be matched by the context index.
export const LEGACY_THREAD_ID = "legacy";

let dbPromise = null;

function openDb() {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      for (const name of [TRANSCRIPT_STORE, CACHE_STORE, VECTOR_STORE, THREADS_STORE, PRIVACY_STORE]) {
        if (!db.objectStoreNames.contains(name)) {
          db.createObjectStore(name, { keyPath: "id" });
        }
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return dbPromise;
}

function getRecord(storeName, id) {
  return openDb().then(
    (db) =>
      new Promise((resolve, reject) => {
        const req = db.transaction(storeName, "readonly").objectStore(storeName).get(id);
        req.onsuccess = () => resolve(req.result ?? null);
        req.onerror = () => reject(req.error);
      })
  );
}

function putRecord(storeName, record) {
  return openDb().then(
    (db) =>
      new Promise((resolve, reject) => {
        const t = db.transaction(storeName, "readwrite");
        t.objectStore(storeName).put(record);
        t.oncomplete = resolve;
        t.onerror = () => reject(t.error);
      })
  );
}

function getAllRecords(storeName) {
  return openDb().then(
    (db) =>
      new Promise((resolve, reject) => {
        const req = db.transaction(storeName, "readonly").objectStore(storeName).getAll();
        req.onsuccess = () => resolve(req.result ?? []);
        req.onerror = () => reject(req.error);
      })
  );
}

function clearStore(storeName) {
  return openDb().then(
    (db) =>
      new Promise((resolve, reject) => {
        const t = db.transaction(storeName, "readwrite");
        t.objectStore(storeName).clear();
        t.oncomplete = resolve;
        t.onerror = () => reject(t.error);
      })
  );
}

// "gsw to  thigh" and "GSW to thigh" share one cache entry.
function cacheKey(mode, query) {
  return `${mode}::${(query || "").trim().toLowerCase().replace(/\s+/g, " ")}`;
}

// ---- Threads --------------------------------------------------------------

function threadTitle(messages) {
  const first = messages.find((m) => m.role === "user");
  const text = (first?.content || "New chat").replace(/\s+/g, " ").trim();
  return text.length > 64 ? `${text.slice(0, 64)}…` : text;
}

// Pre-multi-thread installs kept one transcript under "current". Fold it into
// the threads store once, so it appears in Recents like any other chat.
async function migrateLegacyTranscript() {
  try {
    const record = await getRecord(TRANSCRIPT_STORE, TRANSCRIPT_KEY);
    if (!record) return;
    const messages = decryptJSON(record.cipher);
    if (Array.isArray(messages) && messages.length) {
      await saveThread(LEGACY_THREAD_ID, messages);
    }
    await clearStore(TRANSCRIPT_STORE);
  } catch {
    /* locked vault or legacy plaintext rows — leave untouched */
  }
}

// Metadata for the Recents list: [{id, title, updatedAt, count}], newest first.
export async function listThreads() {
  await migrateLegacyTranscript();
  try {
    const records = await getAllRecords(THREADS_STORE);
    return records
      .map((r) => {
        try {
          const t = decryptJSON(r.cipher);
          return {
            id: r.id,
            title: t.title,
            updatedAt: t.updatedAt,
            count: t.messages?.length ?? 0,
          };
        } catch {
          return null;
        }
      })
      .filter(Boolean)
      .sort((a, b) => (b.updatedAt || "").localeCompare(a.updatedAt || ""));
  } catch {
    return [];
  }
}

export async function loadThread(id) {
  try {
    const record = await getRecord(THREADS_STORE, id);
    if (!record) return [];
    return decryptJSON(record.cipher).messages ?? [];
  } catch {
    return [];
  }
}

export async function saveThread(id, messages) {
  if (!messages.length) return;
  try {
    await putRecord(THREADS_STORE, {
      id,
      cipher: encryptJSON({
        title: threadTitle(messages),
        updatedAt: messages[messages.length - 1]?.timestamp || new Date().toISOString(),
        messages,
      }),
    });
  } catch {
    /* best-effort: never block the UI on persistence */
  }
}

// ---- Response cache -------------------------------------------------------

export async function getCachedResponse(mode, query) {
  try {
    const record = await getRecord(CACHE_STORE, cacheKey(mode, query));
    return record ? decryptJSON(record.cipher) : null;
  } catch {
    return null;
  }
}

export async function putCachedResponse(mode, query, message) {
  try {
    await putRecord(CACHE_STORE, {
      id: cacheKey(mode, query),
      cipher: encryptJSON(message),
    });
  } catch {
    /* best-effort */
  }
}

// ---- Vector index ---------------------------------------------------------

export async function putVector(entry) {
  try {
    await putRecord(VECTOR_STORE, { id: entry.id, cipher: encryptJSON(entry) });
  } catch {
    /* best-effort */
  }
}

export async function allVectors() {
  try {
    const records = await getAllRecords(VECTOR_STORE);
    return records.map((r) => decryptJSON(r.cipher));
  } catch {
    return [];
  }
}

// ---- Privacy log ----------------------------------------------------------
// One encrypted entry per outbound exchange: what the user typed, what
// actually reached the cloud after sanitization, which mechanisms ran, and
// the differential-privacy cost. The dashboard renders these; they never
// leave the device and die with a wipe like everything else.

export async function logPrivacyEvent(entry) {
  try {
    await putRecord(PRIVACY_STORE, { id: entry.id, cipher: encryptJSON(entry) });
  } catch {
    /* best-effort */
  }
}

export async function listPrivacyEvents() {
  try {
    const records = await getAllRecords(PRIVACY_STORE);
    return records
      .map((r) => {
        try {
          return decryptJSON(r.cipher);
        } catch {
          return null;
        }
      })
      .filter(Boolean)
      .sort((a, b) => (b.ts || "").localeCompare(a.ts || ""));
  } catch {
    return [];
  }
}

// ---- Wipe -----------------------------------------------------------------

export async function softWipe() {
  await Promise.all([
    clearStore(TRANSCRIPT_STORE),
    clearStore(THREADS_STORE),
    clearStore(CACHE_STORE),
    clearStore(VECTOR_STORE),
    clearStore(PRIVACY_STORE),
  ]);
}

export async function hardWipe() {
  await softWipe();
  destroyVaultKey();
}
