// Generate MapLibre SDF glyph PBFs from a TTF, one file per 256-codepoint range.
//
// MapLibre requests glyphs as /{fontstack}/{start}-{end}.pbf where each file
// covers 256 code points. Latin text needs only 0-255; we cover 0-1023 so
// Latin-1, Latin Extended, and common punctuation all render. Output goes to
// the fonts directory the generated style points at (FONT_STACK in style.py).
//
// Fully offline: reads a local system TTF, writes local PBFs. No network.

const fs = require("fs");
const path = require("path");
const fontnik = require("fontnik");

const TTF = process.argv[2];
const OUT_DIR = process.argv[3];
const FONTSTACK = process.argv[4] || "Noto Sans Regular";
const MAX_CODEPOINT = 1024; // 4 ranges of 256

if (!TTF || !OUT_DIR) {
  console.error("usage: node gen.js <font.ttf> <out-dir> [fontstack-name]");
  process.exit(1);
}

const dir = path.join(OUT_DIR, FONTSTACK);
fs.mkdirSync(dir, { recursive: true });
const font = fs.readFileSync(TTF);

let done = 0;
const ranges = [];
for (let start = 0; start < MAX_CODEPOINT; start += 256) ranges.push(start);

ranges.forEach((start) => {
  const end = start + 255;
  fontnik.range({ font, start, end }, (err, buffer) => {
    if (err) {
      console.error(`range ${start}-${end} FAILED:`, err.message);
      process.exit(1);
    }
    fs.writeFileSync(path.join(dir, `${start}-${end}.pbf`), buffer);
    done += 1;
    if (done === ranges.length) {
      console.log(`wrote ${done} glyph ranges to ${dir}`);
    }
  });
});
