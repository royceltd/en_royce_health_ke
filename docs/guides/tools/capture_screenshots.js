// Retakes a guide's screenshots from a running RoyceERP Health site.
//
//   PW=<path to node_modules/playwright-core> \
//   CHROME=<path to a Chromium binary> \
//   BASE=https://hospital.royceltd.com ADMIN_PASSWORD=... \
//   node capture_screenshots.js shots/outpatient.json ../images/outpatient
//
// Each entry in the shots file: file, url (open it through its menu, e.g.
// /desk/outpatient/..., so the right sidebar shows), and optionally
//   scroll  - CSS selector to scroll to (e.g. [data-fieldname="items"])
//   expand  - collapsed section headings to open, first one scrolled to
//   click   - a button in the page header to press (e.g. "Nursing Dialog")
//   pane    - a pane inside the dialog that opens (e.g. "Medication")
// kenyan_accountant's "Finish setting up your documents" pop-up is dismissed
// with "Remind me later", which changes no data.
const fs = require("fs");
const path = require("path");
const { chromium } = require(process.env.PW || "playwright-core");

const [shotsFile, outDir] = process.argv.slice(2);
const shots = JSON.parse(fs.readFileSync(shotsFile, "utf8"));
const base = process.env.BASE;

async function dismissSetupPopup(page) {
	const later = page.getByRole("button", { name: "Remind me later" });
	if (await later.count()) {
		await later.first().click();
		await page.waitForTimeout(800);
	}
}

(async () => {
	fs.mkdirSync(outDir, { recursive: true });
	const browser = await chromium.launch({ executablePath: process.env.CHROME });
	const page = await (
		await browser.newContext({ viewport: { width: 1440, height: 900 } })
	).newPage();
	await page.goto(base + "/login");
	const login = await page.request.post(base + "/api/method/login", {
		data: { usr: process.env.ADMIN_USER || "Administrator", pwd: process.env.ADMIN_PASSWORD },
	});
	if (login.status() !== 200) throw new Error("login failed: " + login.status());

	for (const s of shots) {
		try {
			await page.goto(base + s.url, { waitUntil: "networkidle", timeout: 60000 });
			await page.waitForTimeout(2500);
			await dismissSetupPopup(page);
			if (s.expand) {
				for (const label of s.expand) {
					await page.locator(".section-head").filter({ hasText: label }).first().click();
					await page.waitForTimeout(1200);
				}
				await page
					.locator(".section-head")
					.filter({ hasText: s.expand[0] })
					.first()
					.evaluate((el) => {
						el.scrollIntoView({ block: "start" });
						window.scrollBy(0, -70);
					});
				await page.waitForTimeout(800);
			}
			if (s.scroll) {
				await page.evaluate((sel) => {
					const el = document.querySelector(sel);
					if (el) el.scrollIntoView({ block: "start" });
					window.scrollBy(0, -90);
				}, s.scroll);
				await page.waitForTimeout(800);
			}
			if (s.click) {
				await page
					.locator(".page-actions button, .page-head button")
					.filter({ hasText: s.click })
					.first()
					.click();
				await page.waitForTimeout(3500);
				if (s.pane) {
					await page.locator(".modal:visible").getByText(s.pane, { exact: true }).first().click();
					await page.waitForTimeout(2500);
				}
			}
			await page.screenshot({ path: path.join(outDir, s.file) });
			console.log("shot", s.file);
		} catch (e) {
			console.log("FAILED", s.file, e.message.slice(0, 160));
		}
	}
	await browser.close();
})();
