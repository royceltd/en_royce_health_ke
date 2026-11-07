// Turns the guides into client PDFs: A4, Royce cover line, page numbers,
// full-resolution screenshots. Links between guides point at the sibling PDFs.
//
//   NODE_MODULES=<node_modules with micromark, micromark-extension-gfm, playwright-core> \
//   CHROME=<chromium binary> \
//   node make_pdfs.mjs .. "<output folder>"
//
// Run from docs/guides/tools. Update the guide list and the "Guide checked" date
// below when guides are added or re-checked.
import fs from "fs";
import path from "path";
import { createRequire } from "module";
const N = process.env.NODE_MODULES; // a node_modules with micromark, micromark-extension-gfm, playwright-core
if (!N) throw new Error("Set NODE_MODULES");
const { micromark } = await import(N + "/micromark/index.js");
const { gfm, gfmHtml } = await import(N + "/micromark-extension-gfm/index.js");
const require = createRequire(import.meta.url);
const { chromium } = require(N + "/playwright-core");

const [guidesDirArg, outDir] = process.argv.slice(2);
const guidesDir = path.resolve(guidesDirArg);
const chrome = process.env.CHROME;
const workDir = fs.mkdtempSync(path.join((await import("os")).tmpdir(), "guides-pdf-"));
fs.mkdirSync(outDir, { recursive: true });
const guides = [
  ["01-overview.md", "01 RoyceERP Health - Overview"],
  ["02-outpatient.md", "02 RoyceERP Health - Outpatient Workflow"],
  ["03-inpatient.md", "03 RoyceERP Health - Inpatient Workflow"],
  ["04-insurance.md", "04 RoyceERP Health - Insurance Workflow"],
  ["05-maternity.md", "05 RoyceERP Health - Maternity Workflow"],
  ["06-pharmacy-and-stock.md", "06 RoyceERP Health - Pharmacy and Stock"],
  ["07-cashier-day-end.md", "07 RoyceERP Health - Cashier Day-End"],
  ["08-administrator-setup.md", "08 RoyceERP Health - Administrator Setup"],
];
const css = `
@page { size: A4; margin: 18mm 16mm 20mm 16mm; }
body { font-family: "Inter", "Segoe UI", "Helvetica Neue", Arial, sans-serif; font-size: 10.5pt; line-height: 1.5; color: #1f2328; }
.cover { border-bottom: 2px solid #0b6e4f; padding-bottom: 10px; margin-bottom: 18px; }
.cover .brand { color: #0b6e4f; font-weight: 700; letter-spacing: .04em; font-size: 9.5pt; text-transform: uppercase; }
.cover .meta { color: #59636e; font-size: 9pt; margin-top: 4px; }
h1 { font-size: 20pt; margin: 6px 0 4px; line-height: 1.25; }
h2 { font-size: 13.5pt; margin: 22px 0 6px; padding-top: 4px; border-top: 1px solid #d0d7de; break-after: avoid; }
p, li { orphans: 3; widows: 3; }
ol, ul { padding-left: 22px; }
li { margin: 2px 0; }
table { border-collapse: collapse; width: 100%; margin: 8px 0 12px; font-size: 9.5pt; break-inside: avoid; }
th, td { border: 1px solid #d0d7de; padding: 4px 7px; text-align: left; vertical-align: top; }
th { background: #f0f5f3; }
img { max-width: 100%; border: 1px solid #d0d7de; border-radius: 4px; display: block; margin: 8px auto 2px; break-inside: avoid; }
p:has(> img) { break-inside: avoid; break-after: avoid; margin-bottom: 0; }
em { color: #424a53; }
p.caption { font-size: 9pt; color: #59636e; text-align: center; margin: 2px 0 12px; }
a { color: #0b6e4f; text-decoration: none; }
code { font-size: 9pt; background: #f6f8fa; padding: 0 3px; border-radius: 3px; }
`;
const browser = await chromium.launch({ executablePath: chrome });
const page = await browser.newPage();
for (const [file, title] of guides) {
  let md = fs.readFileSync(path.join(guidesDir, file), "utf8");
  md = md.replace(/\]\(((?:0[1-8])-[a-z-]+)\.md\)/g, "]($1.pdf)");
  let body = micromark(md, { extensions: [gfm()], htmlExtensions: [gfmHtml()] });
  const cover = `<div class="cover"><div class="brand">RoyceERP Health · Royce Technologies Ltd</div><div class="meta">Guide checked 7 November 2026 on the demo hospital (Kijani Valley Hospital Ltd). All patients, staff and records shown are fictional.</div></div>`;
  const html = `<!doctype html><html><head><meta charset="utf-8"><base href="file://${guidesDir}/"><title>${title}</title><style>${css}</style></head><body>${cover}${body}</body></html>`;
  const htmlPath = path.join(workDir, file.replace(".md", ".html"));
  fs.writeFileSync(htmlPath, html);
  await page.goto("file://" + htmlPath, { waitUntil: "load" });
  await page.evaluate(() => { for (const p of document.querySelectorAll("p")) { const nodes = [...p.childNodes].filter(n => !(n.nodeType === 3 && !n.textContent.trim())); if (nodes.length === 1 && nodes[0].nodeName === "EM") p.classList.add("caption"); } });
  await page.evaluate(async () => { await Promise.all([...document.images].map(i => i.complete ? null : new Promise(r => { i.onload = i.onerror = r; }))); });
  const out = path.join(outDir, title + ".pdf");
  await page.pdf({ path: out, format: "A4", printBackground: true, displayHeaderFooter: true,
    headerTemplate: "<span></span>",
    footerTemplate: `<div style="font-size:8px;color:#59636e;width:100%;padding:0 16mm;display:flex;justify-content:space-between;"><span>${title.slice(3)}</span><span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span></div>`,
    margin: { top: "16mm", bottom: "18mm", left: "16mm", right: "16mm" } });
  const missing = await page.evaluate(() => [...document.images].filter(i => !i.naturalWidth).map(i => i.getAttribute("src")));
  console.log("PDF", path.basename(out), (fs.statSync(out).size / 1048576).toFixed(1) + " MB", missing.length ? "MISSING " + missing.join(",") : "images ok");
}
await browser.close();
