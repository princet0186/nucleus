// On-device semantic index over the chat for MEDEVAC context retrieval.
//
// Each message is embedded locally (MiniLM via transformers.js — one ~25MB
// download, then cached and fully offline). "Generate Evacuation" ranks all
// stored vectors against a fixed evacuation-relevance probe and sends only
// the top-K messages onward, never the whole transcript. When the embedding
// model is unavailable (e.g. first run without internet), retrieval degrades
// to keyword-overlap scoring so the button always works.

import { allVectors, putVector, LEGACY_THREAD_ID } from "./chatStore";

const EVAC_PROBE =
  "casualty injuries wounds triage category treatment applied tourniquet " +
  "location grid coordinates callsign radio frequency patient count litter " +
  "ambulatory security enemy marking evacuation";

const KEYWORDS = EVAC_PROBE.split(" ");
const TOP_K = 8;
const ALWAYS_INCLUDE_RECENT = 4;

let embedderPromise = null;

function getEmbedder() {
  if (!embedderPromise) {
    embedderPromise = import("@xenova/transformers")
      .then(({ pipeline }) =>
        pipeline("feature-extraction", "Xenova/all-MiniLM-L6-v2")
      )
      .catch(() => null);
  }
  return embedderPromise;
}

async function embed(text) {
  const embedder = await getEmbedder();
  if (!embedder) return null;
  const output = await embedder(text, { pooling: "mean", normalize: true });
  return Array.from(output.data);
}

function cosine(a, b) {
  let dot = 0;
  for (let i = 0; i < a.length; i++) dot += a[i] * b[i];
  return dot; // vectors are normalized, so dot product == cosine similarity
}

function keywordScore(content) {
  const words = content.toLowerCase();
  return KEYWORDS.reduce((score, kw) => score + (words.includes(kw) ? 1 : 0), 0);
}

export async function indexMessage({ id, threadId, role, content }) {
  const vector = await embed(content);
  await putVector({ id, threadId, role, content, vector });
}

// Retrieval is scoped to one thread: resuming an old chat and generating a
// MEDEVAC must not pull casualty details from a different conversation.
// Vectors written before multi-thread storage carry no threadId and belong to
// the migrated legacy thread.
export async function retrieveContext(threadId) {
  const entries = (await allVectors()).filter(
    (e) => e.threadId === threadId || (!e.threadId && threadId === LEGACY_THREAD_ID)
  );
  if (entries.length === 0) return "";
  entries.sort((a, b) => (a.id < b.id ? -1 : 1));

  const probeVector = await embed(EVAC_PROBE);
  const scored = entries.map((entry) => ({
    entry,
    score:
      probeVector && entry.vector
        ? cosine(probeVector, entry.vector)
        : keywordScore(entry.content),
  }));

  const relevant = [...scored]
    .sort((a, b) => b.score - a.score)
    .slice(0, TOP_K)
    .map((s) => s.entry);
  const recent = entries.slice(-ALWAYS_INCLUDE_RECENT);

  const selected = [...new Map([...relevant, ...recent].map((e) => [e.id, e])).values()];
  selected.sort((a, b) => (a.id < b.id ? -1 : 1));

  return selected
    .map((e) => `${e.role === "user" ? "USER" : "AI"}: ${e.content}`)
    .join("\n");
}
