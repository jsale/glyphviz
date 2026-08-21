/**
 * parity_check.mjs -- prove the designer page and tut.py build the same scene.
 *
 * tut.py is the reference implementation; tut_designer.html is a port of it.
 * A port that quietly drifts is worse than no port, because the picture a user
 * downloads would stop matching the picture the script produces from the same
 * archive.  So this runs the PAGE'S OWN JavaScript -- extracted from the HTML,
 * not a copy of it -- against a real archive, and diffs the result against the
 * CSV tut.py writes from the same input.
 *
 * The comparison is SEMANTIC, not byte-for-byte: the two writers format
 * numbers differently (Python writes an int field bare where JavaScript may
 * write 0.000000), and both parse identically in GlyphViz, which reads by
 * column name through pandas.  What must match is every value.
 *
 * Usage:
 *   node parity_check.mjs --archive <data dir> --csv <tut.py output.csv> \
 *        [--layout tower] [--keywords data,Trump]
 */
import { readFileSync, readdirSync } from 'node:fs';
import { join, basename } from 'node:path';
import vm from 'node:vm';

/* ---------- argument parsing ---------- */
const argv = process.argv.slice(2);
const arg = (name, dflt) => {
  const i = argv.indexOf('--' + name);
  return i >= 0 && argv[i + 1] ? argv[i + 1] : dflt;
};
const ARCHIVE_DIR = arg('archive');
const CSV_PATH = arg('csv');
const LAYOUT = arg('layout', 'tower');
const KEYWORDS = arg('keywords', '').split(',').map(s => s.trim()).filter(Boolean);
if (!ARCHIVE_DIR || !CSV_PATH) {
  console.error('usage: node parity_check.mjs --archive <data dir> --csv <csv>');
  process.exit(2);
}

/* ---------- a DOM thin enough to load the page's script ---------- */
function fakeElement() {
  const el = {
    style: {}, children: [], value: '', textContent: '', innerHTML: '',
    checked: false, files: null, type: '', min: 0, max: 0, step: 0,
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    appendChild(c) { this.children.push(c); return c; },
    addEventListener() {}, removeEventListener() {}, click() {},
    setPointerCapture() {}, releasePointerCapture() {},
    getBoundingClientRect: () => ({ width: 800, height: 600, top: 0, left: 0 }),
    getContext: () => new Proxy({}, { get: () => () => {} }),
    querySelector: () => fakeElement(), querySelectorAll: () => [],
  };
  return el;
}
const doc = {
  getElementById: () => fakeElement(),
  createElement: () => fakeElement(),
  createTextNode: () => fakeElement(),
  addEventListener() {},
};
const sandbox = {
  document: doc,
  window: { addEventListener() {}, devicePixelRatio: 1 },
  requestAnimationFrame: () => 0,
  setTimeout, clearTimeout, console,
  Intl, Date, Math, JSON, Number, String, Object, Array, RegExp, Map, Set,
  Promise, Blob: class {}, URL: { createObjectURL: () => '', revokeObjectURL() {} },
};
sandbox.globalThis = sandbox;

/* ---------- extract and run the page's script ---------- */
const html = readFileSync(new URL('./tut_designer.html', import.meta.url), 'utf8');
const m = html.match(/<script>([\s\S]*?)<\/script>/);
if (!m) { console.error('no <script> block found in tut_designer.html'); process.exit(2); }
const source = m[1] + `
globalThis.__TUT = {
  buildArchive, buildScene, toCsv, relocalize, selectedPosts, COLUMNS,
  setP: o => Object.assign(P, o),
  setArchive: a => { ARCHIVE = a; },
};`;
vm.createContext(sandbox);
new vm.Script(source, { filename: 'tut_designer.html' }).runInContext(sandbox);
const T = sandbox.__TUT;

/* ---------- run it on the archive ---------- */
const WANTED = /^(tweets(-part\d+)?|account|profile|account-timezone)\.js$/i;
const files = {};
for (const name of readdirSync(ARCHIVE_DIR)) {
  if (WANTED.test(name)) files[basename(name)] = readFileSync(join(ARCHIVE_DIR, name), 'utf8');
}
T.setP({ layout: LAYOUT, keyword1: KEYWORDS[0] || '', keyword2: KEYWORDS[1] || '' });
const archive = T.buildArchive(files);
T.setArchive(archive);
T.relocalize(archive);
const rows = T.buildScene(T.selectedPosts(), 0);
console.log(`page  : @${archive.username}, ${archive.posts.length} posts, `
          + `zone ${archive.tzName} -> ${rows.length} nodes`);

/* ---------- read tut.py's CSV ---------- */
function parseCsv(text) {
  const out = [];
  let row = [], cell = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '"') { if (text[i + 1] === '"') { cell += '"'; i++; } else q = false; }
      else cell += c;
    } else if (c === '"') q = true;
    else if (c === ',') { row.push(cell); cell = ''; }
    else if (c === '\r') { /* skip */ }
    else if (c === '\n') { row.push(cell); out.push(row); row = []; cell = ''; }
    else cell += c;
  }
  if (cell.length || row.length) { row.push(cell); out.push(row); }
  const head = out.shift();
  return out.filter(r => r.length === head.length)
            .map(r => Object.fromEntries(head.map((h, i) => [h, r[i]])));
}
const ref = parseCsv(readFileSync(CSV_PATH, 'utf8'));
console.log(`tut.py: ${ref.length} nodes  (${basename(CSV_PATH)})`);

/* ---------- diff ---------- */
const NUMERIC = new Set(T.COLUMNS.filter(c => c !== 'text' && c !== 'link'));
let problems = 0;
const report = (msg) => { if (problems++ < 12) console.log('  MISMATCH ' + msg); };

if (rows.length !== ref.length) {
  console.log(`  MISMATCH node count: page ${rows.length} vs tut.py ${ref.length}`);
  problems++;
}
const n = Math.min(rows.length, ref.length);
let worst = 0, worstAt = '';
for (let i = 0; i < n; i++) {
  const a = rows[i], b = ref[i];
  for (const col of T.COLUMNS) {
    if (NUMERIC.has(col)) {
      const av = Number(a[col]), bv = Number(b[col]);
      const d = Math.abs(av - bv);
      if (!(d <= 1e-6)) report(`row ${i} id ${a.id} col ${col}: ${av} vs ${bv}`);
      else if (d > worst) { worst = d; worstAt = `row ${i} ${col}`; }
    } else {
      if (String(a[col]) !== String(b[col]))
        report(`row ${i} id ${a.id} col ${col}:\n      page  : ${JSON.stringify(a[col])}\n      tut.py: ${JSON.stringify(b[col])}`);
    }
  }
}
if (problems > 12) console.log(`  ... and ${problems - 12} more`);
console.log(problems
  ? `\nFAIL — ${problems} mismatching value(s)`
  : `\nPASS — ${n} nodes identical across every column `
    + `(largest numeric difference ${worst.toExponential(1)}${worst ? ' at ' + worstAt : ''})`);
process.exit(problems ? 1 : 0);
