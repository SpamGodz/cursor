/**
 * End-to-end check of the PDF export.
 *
 *   node tools/verify_export.js            # all scenarios
 *   node tools/verify_export.js full       # one scenario, keeps the PDF
 *
 * Drives index.html in Chromium, fills the form the way a technician would
 * (taps, typed answers, drawn signatures, camera uploads), exports the PDF and
 * asserts what landed in it. Written PDFs go to tools/.verify-out/ so the
 * stamped form can be eyeballed against assets/FPGROC_Service_Checklist.pdf.
 *
 * Requires: npm i -D playwright   (browsers already installed)
 * Set PW_CHROMIUM=/path/to/chrome if Playwright cannot find its own browser.
 */
const { chromium } = require('playwright');
const http = require('http');
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');

const ROOT = path.resolve(__dirname, '..');
const OUT_DIR = path.join(__dirname, '.verify-out');
const VENDOR_DIR = path.join(__dirname, '.vendor');   // optional offline copies
const PORT = 8123;

const MIME = { '.html': 'text/html', '.pdf': 'application/pdf', '.js': 'text/javascript' };
const failures = [];

function check(name, cond, extra) {
  console.log(`  ${cond ? 'ok  ' : 'FAIL'}  ${name}${cond ? '' : '   <- ' + JSON.stringify(extra)}`);
  if (!cond) failures.push(name);
}

function serve() {
  const server = http.createServer((req, res) => {
    const file = path.join(ROOT, decodeURIComponent(req.url.split('?')[0]));
    fs.readFile(file, (err, data) => {
      if (err) { res.writeHead(404); res.end('not found'); return; }
      res.writeHead(200, { 'Content-Type': MIME[path.extname(file)] || 'application/octet-stream' });
      res.end(data);
    });
  });
  return new Promise(r => server.listen(PORT, () => r(server)));
}

// Serve the CDN libraries from tools/.vendor when it exists, so the check can
// run without network access.
async function routeVendor(page) {
  const local = {
    'pdf-lib': path.join(VENDOR_DIR, 'pdf-lib.min.js'),
    'signature_pad': path.join(VENDOR_DIR, 'signature_pad.umd.min.js'),
    'tailwindcss': path.join(VENDOR_DIR, 'tailwind.js')
  };
  const available = Object.keys(local).filter(k => fs.existsSync(local[k]));
  if (!available.length) return;
  await page.route('**/*', route => {
    const url = route.request().url();
    const hit = available.find(k => url.includes(k));
    if (!hit) return route.continue();
    route.fulfill({ status: 200, contentType: 'text/javascript', body: fs.readFileSync(local[hit], 'utf8') });
  });
}

async function open(browser) {
  const ctx = await browser.newContext({ viewport: { width: 420, height: 900 }, acceptDownloads: true });
  const page = await ctx.newPage();
  page.on('pageerror', e => { console.log('  PAGE EXCEPTION:', e.message); failures.push('pageerror'); });
  await routeVendor(page);
  await page.goto(`http://127.0.0.1:${PORT}/index.html`, { waitUntil: 'networkidle' });
  await page.waitForFunction(() => !!window.PDFLib && !!window.SignaturePad, null, { timeout: 30000 });
  return page;
}

const idle = page => page.waitForFunction(() => document.getElementById('busy').classList.contains('hidden'), null, { timeout: 30000 });
const answer = (page, field, value) => page.click(`[data-field="${field}"][data-value="${value}"]`);

// A photo, without shipping binary fixtures: drawn in the page, handed back as
// a buffer and fed through the real file input.
async function attachPhoto(page, key, w, h, label) {
  const dataUrl = await page.evaluate(([w, h, label]) => {
    const c = document.createElement('canvas');
    c.width = w; c.height = h;
    const x = c.getContext('2d');
    x.fillStyle = '#dde8ff'; x.fillRect(0, 0, w, h);
    x.strokeStyle = '#111'; x.lineWidth = 6; x.strokeRect(10, 10, w - 20, h - 20);
    x.fillStyle = '#111'; x.font = `bold ${Math.round(Math.min(w, h) / 8)}px sans-serif`;
    x.fillText(label, 24, h / 2);
    return c.toDataURL('image/jpeg', 0.8);
  }, [w, h, label]);
  await page.setInputFiles(`[data-key="${key}"]`, {
    name: `${key}.jpg`, mimeType: 'image/jpeg', buffer: Buffer.from(dataUrl.split(',')[1], 'base64')
  });
  await idle(page);
}

async function drawSignature(page, id, seed) {
  await idle(page);
  await page.evaluate(canvasId => document.getElementById(canvasId).scrollIntoView({ block: 'center' }), 'sig_' + id);
  await page.waitForTimeout(200);
  const box = await page.locator('#sig_' + id).boundingBox();
  const y0 = box.y + box.height * 0.62;
  await page.mouse.move(box.x + 24, y0);
  await page.mouse.down();
  for (let i = 0; i <= 40; i++) {
    const t = i / 40;
    await page.mouse.move(box.x + 24 + t * (box.width - 60), y0 - Math.sin(t * Math.PI * 3 + seed) * box.height * 0.22 - t * 8);
  }
  await page.mouse.up();
  await page.waitForTimeout(120);
}

async function exportPdf(page, name) {
  const b64 = await page.evaluate(async () => {
    const bytes = await window.__fpgroc.buildPdf();
    let bin = '';
    for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    return btoa(bin);
  });
  const buf = Buffer.from(b64, 'base64');
  fs.mkdirSync(OUT_DIR, { recursive: true });
  fs.writeFileSync(path.join(OUT_DIR, name + '.pdf'), buf);
  return buf;
}

// pdf-lib writes object and content streams deflated, so read the PDF by
// inflating every stream in it rather than grepping the raw bytes.
function inflate(buf) {
  const raw = buf.toString('latin1');
  let out = raw;
  const re = /stream\r?\n/g;
  let m;
  while ((m = re.exec(raw)) !== null) {
    const start = m.index + m[0].length;
    // Prefer the declared /Length: binary payloads can contain "endstream".
    const dict = raw.slice(Math.max(0, m.index - 500), m.index);
    const len = /\/Length\s+(\d+)[^\d]*$/.exec(dict);
    const ends = [];
    if (len) ends.push(start + parseInt(len[1], 10));
    const marker = raw.indexOf('endstream', start);
    if (marker > 0) ends.push(marker);
    for (const end of ends) {
      try {
        out += '\n' + zlib.inflateSync(Buffer.from(raw.slice(start, end), 'latin1'),
          { finishFlush: zlib.constants.Z_SYNC_FLUSH }).toString('latin1');
        break;
      } catch (e) { /* try the next boundary */ }
    }
  }
  return out;
}

// The template is one page; anything beyond it is photo/addendum overflow.
function pageCount(buf) {
  const m = inflate(buf).match(/\/Type\s*\/Page(?![s])/g);
  return m ? m.length : 0;
}

// pdf-lib writes drawn text as hex strings, e.g. <57616C...> Tj.
function pdfContains(buf, needle) {
  const corpus = inflate(buf);
  const hex = Buffer.from(needle, 'latin1').toString('hex').toUpperCase();
  return corpus.includes(needle) || corpus.toUpperCase().includes(hex);
}

/* ------------------------------- scenarios ------------------------------- */

async function scenarioFull(browser) {
  console.log('\nfull - every question answered, four signatures, seven photos');
  const page = await open(browser);
  await page.fill('#storeName', 'Walmart Supercenter #2718 - Northlake Blvd');
  await page.fill('#location', 'Palm Beach Gardens, FL');
  await answer(page, 'q1', 'YES');
  await answer(page, 'q2', 'NO');
  await page.fill('#q2_why_text', 'Unit is 5FT - floor install per policy');
  await answer(page, 'q3', 'NO');
  await page.fill('#q3_why_text', 'Store insisted on their own layout');
  await page.fill('#q3_manager_name', 'Denise Halloway');
  await drawSignature(page, 'q3', 0.4);
  await answer(page, 'q4', 'NO');
  await page.check('input[name="q4_reason"][value="C"]');
  await page.fill('#q4_other', 'Tag printer offline until Monday');
  await page.fill('#q4_manager_name', 'Marcus Webb - Asst. Mgr');
  await drawSignature(page, 'q4', 1.1);
  await answer(page, 'q5', 'NO');
  await page.fill('#q5_why_text', 'Two cases held in back cooler, no room');
  await answer(page, 'q6', 'YES');
  await answer(page, 'q6b', 'NO');

  await attachPhoto(page, 'serial', 400, 260, 'SERIAL');
  await attachPhoto(page, 'thermo', 260, 400, 'THERMO');
  await attachPhoto(page, 'aisle', 480, 270, 'AISLE 12');
  await attachPhoto(page, 'pog', 300, 420, 'POG');
  await answer(page, 'photo_pog', 'NO');
  await page.fill('#photo_pog_why_text', 'POG photo taken before store undid the reset');

  await page.fill('#serialNumber', 'TRU-GDM-49-2214887');
  await answer(page, 'q9', 'YES');
  await page.check('input[name="electric"][value="4"]');
  await answer(page, 'q11', 'YES');
  await page.fill('#q11_damage_desc', 'Lower left corner of frame dented in transit and one shelf clip snapped.');
  await attachPhoto(page, 'damage', 420, 300, 'DENT');
  await page.fill('#generalComments', 'Install completed 0740-0915. Receiving door blocked so the unit came through the garden centre.');

  await page.check('#isWalmart');
  await answer(page, 'w9', 'YES');
  await answer(page, 'w10', 'NO');
  await page.fill('#w10_why_text', 'Manager would not approve base deck for a 5FT unit');
  await page.fill('#walmart_manager', 'Denise Halloway - Store Manager');
  await drawSignature(page, 'walmart', 2.2);

  await attachPhoto(page, 'completed', 360, 480, 'DONE');
  await drawSignature(page, 'store', 0.9);
  await page.fill('#store_print_name', 'Denise Halloway');
  await page.fill('#store_title', 'Store Manager');
  await page.fill('#tech_name', 'Field Tech');
  await page.waitForTimeout(400);

  const sigs = await page.evaluate(() => Object.keys(window.__fpgroc.state.signatures).sort());
  const pads = await page.evaluate(() => Object.keys(window.__fpgroc.pads).map(id => {
    const c = document.getElementById('sig_' + id);
    const r = c.getBoundingClientRect();
    return Math.abs(c.width - r.width * Math.max(devicePixelRatio, 1)) < 2;
  }));
  const buf = await exportPdf(page, 'full');

  check('progress reaches 100%', (await page.textContent('#progressText')) === '100%');
  check('all four signatures captured', JSON.stringify(sigs) === '["q3","q4","store","walmart"]', sigs);
  check('every pad bitmap matches its box', pads.every(Boolean), pads);
  check('typed answers reach the pdf', pdfContains(buf, 'Walmart Supercenter') && pdfContains(buf, 'TRU-GDM-49-2214887'));
  check('photo pages appended', pageCount(buf) === 5, pageCount(buf));
  check('pdf is well formed', buf.slice(0, 5).toString() === '%PDF-' && buf.toString('latin1').includes('%%EOF'));
  await page.context().close();
}

async function scenarioMinimal(browser) {
  console.log('\nminimal - all YES, no photos, no signatures, no Walmart block');
  const page = await open(browser);
  await page.fill('#storeName', 'Kroger #418');
  await page.fill('#location', 'Cincinnati, OH');
  for (const f of ['q1', 'q2', 'q3', 'q4', 'q5', 'photo_serial', 'photo_thermo', 'photo_aisle', 'photo_pog', 'q9']) {
    await answer(page, f, 'YES');
  }
  await answer(page, 'q6', 'NO');
  await answer(page, 'q11', 'NO');
  await page.fill('#serialNumber', 'TRU-91-004512');
  await page.check('input[name="electric"][value="1"]');
  await page.fill('#tech_name', 'Field Tech');
  const buf = await exportPdf(page, 'minimal');
  check('stays a single page', pageCount(buf) === 1, pageCount(buf));
  check('serial made it in', pdfContains(buf, 'TRU-91-004512'));
  await page.context().close();
}

async function scenarioEmpty(browser) {
  console.log('\nempty - nothing filled in at all');
  const page = await open(browser);
  const buf = await exportPdf(page, 'empty');
  check('exports without throwing', buf.length > 1000);
  check('stays a single page', pageCount(buf) === 1, pageCount(buf));
  await page.context().close();
}

async function scenarioStress(browser) {
  console.log('\nstress - overlong answers, smart quotes, accents, emoji');
  const page = await open(browser);
  const LONG = 'Store manager Renée O’Brien — “no base deck” – refused sign-off; the unit blocked ' +
    'receiving for 90+ minutes while the overnight team moved pallets, then the scan coordinator left ' +
    'for the day so tags could not be printed 🚚📦 (see photos).';
  await page.fill('#storeName', 'Café Fresh Market #77 — Ünïcode & Co. ' + 'X'.repeat(60));
  await page.fill('#location', 'Ciudad Juárez, México ' + 'Y'.repeat(40));
  await answer(page, 'q1', 'NO');
  await page.fill('#q1_why_text', LONG);
  await answer(page, 'q5', 'NO');
  await page.fill('#q5_why_text', LONG);
  await answer(page, 'q11', 'YES');
  await page.fill('#q11_damage_desc', LONG + ' ' + LONG);
  await page.fill('#generalComments', LONG + ' ' + LONG + ' ' + LONG);
  await page.fill('#serialNumber', 'TRU-' + '9'.repeat(40));
  const buf = await exportPdf(page, 'stress');
  check('exports without throwing on non-WinAnsi text', buf.length > 1000);
  check('shortened entries get an addendum page', pageCount(buf) === 2, pageCount(buf));
  await page.context().close();
}

async function scenarioRoundTrip(browser) {
  console.log('\nround-trip - draft survives a reload, button flow downloads');
  const page = await open(browser);
  await page.fill('#storeName', 'Publix #1180');
  await page.fill('#location', 'Tampa, FL');
  await answer(page, 'q1', 'YES');
  await answer(page, 'q3', 'NO');
  await page.fill('#q3_manager_name', 'A. Ruiz');
  await drawSignature(page, 'q3', 0.5);
  await attachPhoto(page, 'serial', 400, 260, 'SERIAL');
  await page.fill('#serialNumber', 'RT-TEST-001');
  await page.fill('#tech_name', 'Field Tech');
  await page.waitForTimeout(700);
  const before = await page.evaluate(() => document.getElementById('progressText').textContent);

  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForFunction(() => !!window.PDFLib);
  await page.waitForTimeout(900);

  const after = await page.evaluate(() => ({
    store: document.getElementById('storeName').value,
    serial: document.getElementById('serialNumber').value,
    mgr: document.getElementById('q3_manager_name').value,
    marked: document.querySelector('[data-field="q1"][data-value="YES"]').classList.contains('active'),
    panel: !document.getElementById('q3_manager').classList.contains('hidden'),
    photos: (window.__fpgroc.state.photos.serial || []).length,
    thumbs: document.querySelectorAll('[data-thumbs="serial"] img').length,
    ink: !window.__fpgroc.pads.q3.isEmpty(),
    progress: document.getElementById('progressText').textContent
  }));
  check('text fields restored', after.store === 'Publix #1180' && after.serial === 'RT-TEST-001' && after.mgr === 'A. Ruiz', after);
  check('yes/no + conditional panel restored', after.marked && after.panel, after);
  check('photo and thumbnail restored', after.photos === 1 && after.thumbs === 1, after);
  check('signature redrawn on the pad', after.ink, after.ink);
  check('progress unchanged by the reload', after.progress === before, [before, after.progress]);

  await page.click('#btnPDF');
  await page.waitForSelector('#missingSheet:not(.hidden)', { timeout: 8000 });
  check('incomplete form warns before exporting', (await page.locator('#missingList li').count()) > 0);
  const [download] = await Promise.all([
    page.waitForEvent('download', { timeout: 40000 }),
    page.click('#missingAnyway')
  ]);
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const saved = path.join(OUT_DIR, 'download.pdf');
  await download.saveAs(saved);
  check('download names itself after the store', /^Freshpet_Chiller_Publix_1180_\d{4}-\d{2}-\d{2}\.pdf$/.test(download.suggestedFilename()), download.suggestedFilename());
  check('download is a real pdf', fs.readFileSync(saved).slice(0, 5).toString() === '%PDF-');

  page.on('dialog', d => d.accept());
  await page.click('#resultClose');
  await page.waitForFunction(() => document.getElementById('resultSheet').classList.contains('hidden'));
  await page.click('#btnClear');
  await page.waitForTimeout(1200);
  const cleared = await page.evaluate(() => ({
    store: document.getElementById('storeName').value,
    photos: Object.keys(window.__fpgroc.state.photos).length
  }));
  check('clear wipes the device', cleared.store === '' && cleared.photos === 0, cleared);
  await page.context().close();
}

const SCENARIOS = {
  full: scenarioFull, minimal: scenarioMinimal, empty: scenarioEmpty,
  stress: scenarioStress, roundtrip: scenarioRoundTrip
};

(async () => {
  const only = process.argv[2];
  const names = only ? [only] : Object.keys(SCENARIOS);
  if (only && !SCENARIOS[only]) {
    console.error(`unknown scenario "${only}" - pick one of: ${Object.keys(SCENARIOS).join(', ')}`);
    process.exit(2);
  }
  const server = await serve();
  const launch = { args: ['--no-sandbox'] };
  if (process.env.PW_CHROMIUM) launch.executablePath = process.env.PW_CHROMIUM;
  const browser = await chromium.launch(launch);
  try {
    for (const name of names) await SCENARIOS[name](browser);
  } finally {
    await browser.close();
    server.close();
  }
  console.log(failures.length
    ? `\n${failures.length} failure(s): ${failures.join(', ')}`
    : `\nall checks passed - PDFs written to ${path.relative(ROOT, OUT_DIR)}/`);
  process.exit(failures.length ? 1 : 0);
})().catch(e => { console.error('verify failed:', e); process.exit(1); });
