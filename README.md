# Freshpet Chiller Install — digital service checklist

A single-file web app that a technician fills in on their phone at the store, and which
exports **the real FPGROC Service Checklist PDF with the answers stamped onto it** — not a
lookalike rebuilt in code.

- **[`index.html`](index.html)** — the app. One self-contained file; host it anywhere, or
  open it straight off the phone. The blank checklist PDF is embedded inside it.
- **[`assets/FPGROC_Service_Checklist.pdf`](assets/FPGROC_Service_Checklist.pdf)** — the blank
  form the export is built on.
- **[`src/app.html`](src/app.html)** — editable source (same file, with a placeholder where the
  PDF gets embedded).
- **[`tools/build.py`](tools/build.py)** — embeds the PDF into the source to produce `index.html`.
- **[`tools/verify_export.js`](tools/verify_export.js)** — drives the app in a real browser and
  checks what comes out.

## How the export works

The original checklist is a flat, one-page PDF (612 × 792 pt, no AcroForm fields). Rather than
redraw it, the app loads that exact file with [pdf-lib](https://pdf-lib.js.org/) and paints
answers onto it at measured coordinates, so the printed result is the genuine form:

- **YES / NO** answers get a red ellipse drawn around the printed word, the way a pen would.
- Rows whose YES/NO cells are printed **empty** (the POG row, and the two Walmart rows) get an
  **X** in the correct cell instead.
- Free text lands on the printed rules, auto-shrinking and wrapping to fit; anything still too
  long is truncated with `...` and reproduced in full on an **addendum page**.
- Signatures are captured on a transparent canvas, trimmed to the ink, and scaled into the strip
  the form leaves for them.
- Photos are appended as **photo-evidence pages**, two per page, aspect ratio preserved.

Everything is stamped from one table of coordinates — `GEOM` near the top of the script in
`src/app.html`. Each entry carries the measurement it came from, e.g.

```js
serial: { x: 332, y: 422.9, maxW: 222 },   // rule 328.1–556.3 @ 424.7
```

Coordinates are in PDF points from the **top-left** of the page (that is how they were measured
off the source file); `toY()` flips them into pdf-lib's bottom-left origin. If the printed form
is ever reissued, re-measure and update `GEOM` — no other code should need to change.

## Working on it

```bash
python3 tools/build.py        # src/app.html + assets/*.pdf  ->  index.html
```

Edit `src/app.html`, never `index.html` directly — the latter is generated.

## Checking it

```bash
npm i -D playwright
node tools/verify_export.js               # all scenarios
node tools/verify_export.js full          # just one
```

It fills the form the way a technician would — taps, typed answers, drawn signatures, camera
uploads — then exports and asserts on the result. Scenarios cover a fully-completed visit, a
clean all-YES visit, an empty form, oversized/accented/emoji input, and a draft that survives a
page reload. Generated PDFs land in `tools/.verify-out/` so page 1 can be compared against the
blank form by eye.

Drop `pdf-lib.min.js`, `signature_pad.umd.min.js` and `tailwind.js` into `tools/.vendor/` to run
the checks without network access.

## Notes for the field

- Work is saved to the device continuously (IndexedDB, falling back to localStorage), so a
  dropped signal or a backgrounded tab does not lose the visit.
- **Generate PDF** warns about unanswered questions first, and will still export if you choose to.
- The three libraries load from a CDN. If the page is opened with no connection and they are not
  cached, a banner says so — entries are still saved, and the PDF can be generated after
  reconnecting and reloading.
- After exporting, upload the pictures and call **877-744-7334** while still on site.
