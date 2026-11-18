// Turns the guides into client PDFs: A4, Royce cover line, page numbers,
// full-resolution screenshots. Links between guides point at the sibling PDFs.
//
//   NODE_MODULES=<node_modules with micromark, micromark-extension-gfm, playwright-core> \
//   CHROME=<chromium binary> \
//   node make_pdfs.mjs .. "<output folder>"
//
// Run from docs/guides/tools. Update the guide list and each guide's "checked"
// date below when guides are added or re-checked. ONLY=09 builds just guides
// whose file name starts with that.
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
  ["02-outpatient.md", "02 RoyceERP Health - Outpatient Workflow", "16 November 2026"],
  ["03-inpatient.md", "03 RoyceERP Health - Inpatient Workflow"],
  ["04-insurance.md", "04 RoyceERP Health - Insurance Workflow"],
  ["05-maternity.md", "05 RoyceERP Health - Maternity Workflow"],
  ["06-pharmacy-and-stock.md", "06 RoyceERP Health - Pharmacy and Stock", "16 November 2026"],
  ["07-cashier-day-end.md", "07 RoyceERP Health - Cashier Day-End", "16 November 2026"],
  ["08-administrator-setup.md", "08 RoyceERP Health - Administrator Setup", "16 November 2026"],
  ["09-patient-sms.md", "09 RoyceERP Health - Patient SMS", "8 November 2026"],
  ["10-theatre.md", "10 RoyceERP Health - Theatre Workflow", "11 November 2026"],
  ["11-theatre-testing.md", "11 RoyceERP Health - Theatre Testing Guide", "11 November 2026"],
  ["12-reception-queue-billing.md", "12 RoyceERP Health - Reception, Queue and Billing", "16 November 2026"],
  ["13-reception-billing-testing.md", "13 RoyceERP Health - Reception and Billing Testing Guide", "11 November 2026"],
  ["14-v0.22-testing.md", "14 RoyceERP Health - Version 0.22 Testing Guide", "11 November 2026"],
  ["15-pharmacy-setup-and-upload.md", "15 RoyceERP Health - Pharmacy and Stock Setup and Data Upload", "14 November 2026"],
  ["16-petty-cash.md", "16 RoyceERP Health - Petty Cash", "15 November 2026"],
  ["17-surveillance-growth-alerts-quality.md", "17 RoyceERP Health - Disease Surveillance, Child Growth, Clinical Alerts and Quality Measures", "16 November 2026"],
];
// Temporary guides (../temporary): setup checklists and release testing
// scripts, built with TEMPORARY=1 into their own folder.
const temporaryGuides = [
  ["bethesda-setup-v0.25.md", "Bethesda Setup for Versions 0.24 and 0.25", "13 November 2026",
    "Written 13 November 2026 for Bethesda Healthcare Services (bethesda.royceltd.com), version 0.25."],
  ["v0.25-testing.md", "Version 0.24 and 0.25 Testing Guide", "13 November 2026"],
  ["v0.27-testing.md", "Version 0.27 Lab Worklist and Results Inbox Testing Guide", "14 November 2026"],
  ["v0.28-testing.md", "Version 0.28 Pharmacy Worklist Testing Guide", "15 November 2026"],
  ["petty-cash-testing.md", "Petty Cash Testing Guide", "15 November 2026"],
  ["v0.29-testing.md", "Version 0.29 Billing Approvals and Patient Bills Testing Guide", "15 November 2026"],
  ["bethesda-go-live.md", "Bethesda Go-Live: 16 to 20 November 2026", "15 November 2026",
    "Written 15 November 2026 for Bethesda Healthcare Services (bethesda.royceltd.com), version 0.29."],
  ["v0.33-testing.md", "Version 0.30 to 0.33 Surveillance, Child Growth, Clinical Alerts and Quality Measures Testing Guide", "16 November 2026"],
  ["v0.34-testing.md", "Version 0.34 Registration, Check-in and Triage Changes Testing Guide", "16 November 2026"],
  ["v0.35-testing.md", "Version 0.35 Paying Before Service Testing Guide", "16 November 2026"],
  ["v0.36-testing.md", "Version 0.36 Consultation Tabs, Pharmacy Lock, Patient Receipt and Consultation Fee Testing Guide", "16 November 2026"],
  ["v0.36.2-testing.md", "Version 0.36.2 Create Bill Fix and Cover Price Books Testing Guide", "17 November 2026"],
  ["v0.37-testing.md", "Version 0.37 Take Payment, Cashier Before Service Points and Billing Menu Testing Guide", "17 November 2026"],
  ["v0.41-testing.md", "Version 0.41 No Consultation or Triage Before Payment Testing Guide", "18 November 2026"],
  ["v0.42-it-feedback-guide.md", "Your Feedback of 17 November: Payment Before Service, Queues, Service Prices and Categories", "18 November 2026"],
  ["v0.44-testing.md", "Version 0.44.1 Changes from the 17 and 18 November Demos Testing Guide", "18 November 2026"],
  ["v0.45-testing.md", "Version 0.45 Outpatient Changes from the Bethesda Proposals Testing Guide", "18 November 2026"],
  ["v0.43-testing.md", "Version 0.43 Security Basics: Logins, Users, Screen Lock and the Compliance Check Testing Guide", "18 November 2026"],
  ["demo-script-bethesda.md", "Demo Script for Bethesda", "15 November 2026",
    "Written 15 November 2026 for the demo of RoyceERP Health to Bethesda Healthcare Services, on hospital.royceltd.com (v0.28.1). All patients, staff and records shown are fictional."],
];
const selected = process.env.TEMPORARY ? temporaryGuides : guides;
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
for (const [file, title, checked = "7 November 2026", note] of selected) {
  if (process.env.ONLY && !file.startsWith(process.env.ONLY)) continue;
  let md = fs.readFileSync(path.join(guidesDir, file), "utf8");
  md = md.replace(/\]\((?:\.\.\/)?(\d{2}-[a-z-]+)\.md\)/g, "]($1.pdf)");
  let body = micromark(md, { extensions: [gfm()], htmlExtensions: [gfmHtml()] });
  const cover = `<div class="cover"><div class="brand">RoyceERP Health · Royce Technologies Ltd</div><div class="meta">${note || `Guide checked ${checked} on the demo hospital (Kijani Valley Hospital Ltd). All patients, staff and records shown are fictional.`}</div></div>`;
  const html = `<!doctype html><html><head><meta charset="utf-8"><base href="file://${guidesDir}/"><title>${title}</title><style>${css}</style></head><body>${cover}${body}</body></html>`;
  const htmlPath = path.join(workDir, file.replace(".md", ".html"));
  fs.writeFileSync(htmlPath, html);
  await page.goto("file://" + htmlPath, { waitUntil: "load" });
  await page.evaluate(() => { for (const p of document.querySelectorAll("p")) { const nodes = [...p.childNodes].filter(n => !(n.nodeType === 3 && !n.textContent.trim())); if (nodes.length === 1 && nodes[0].nodeName === "EM") p.classList.add("caption"); } });
  await page.evaluate(async () => { await Promise.all([...document.images].map(i => i.complete ? null : new Promise(r => { i.onload = i.onerror = r; }))); });
  const out = path.join(outDir, title + ".pdf");
  await page.pdf({ path: out, format: "A4", printBackground: true, displayHeaderFooter: true,
    headerTemplate: "<span></span>",
    footerTemplate: `<div style="font-size:8px;color:#59636e;width:100%;padding:0 16mm;display:flex;justify-content:space-between;"><span>${process.env.TEMPORARY ? title : title.slice(3)}</span><span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span></div>`,
    margin: { top: "16mm", bottom: "18mm", left: "16mm", right: "16mm" } });
  const missing = await page.evaluate(() => [...document.images].filter(i => !i.naturalWidth).map(i => i.getAttribute("src")));
  console.log("PDF", path.basename(out), (fs.statSync(out).size / 1048576).toFixed(1) + " MB", missing.length ? "MISSING " + missing.join(",") : "images ok");
}
await browser.close();
