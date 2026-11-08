// Screenshots for 09-patient-sms.md. Unlike capture_screenshots.js this one
// clicks through dialogs and actually sends, so run it only against a demo site
// whose Bulk SMS Settings point at a mock RoyceTalk API (never a live key: real
// SMS cost money and would go to the demo's made-up numbers). At the end it sets
// the API URL to https://roycetalk.com for the settings screenshot.
//
//   PW=<node_modules/playwright-core> CHROME=<chromium> \
//   BASE=http://healthdemo.localhost:8003 ADMIN_PASSWORD=<password> \
//   node capture_sms.js ../images/sms

const fs = require("fs");
const path = require("path");
const { chromium } = require(process.env.PW || "playwright-core");

const base = process.env.BASE;
const outDir = process.argv[2];
const PATIENT = "Faith Njeri Wambui";

async function later(page) {
	const btn = page.getByRole("button", { name: "Remind me later" });
	if (await btn.count()) {
		await btn.first().click();
		await page.waitForTimeout(800);
	}
}

async function open(page, url) {
	await page.goto(base + url, { waitUntil: "networkidle", timeout: 60000 });
	await page.waitForTimeout(2000);
	await later(page);
}

async function scrollTo(page, label, offset = 80) {
	await page
		.locator(".section-head, .form-section .section-head, h4, .head-title")
		.filter({ hasText: label })
		.first()
		.evaluate((el, offset) => {
			el.scrollIntoView({ block: "start" });
			window.scrollBy(0, -offset);
		}, offset);
	await page.waitForTimeout(700);
}

async function shot(page, file) {
	await page.screenshot({ path: path.join(outDir, file) });
	console.log("shot", file);
}

(async () => {
	fs.mkdirSync(outDir, { recursive: true });
	const browser = await chromium.launch({ executablePath: process.env.CHROME });
	const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
	await page.goto(base + "/login");
	const login = await page.request.post(base + "/api/method/login", {
		data: { usr: "Administrator", pwd: process.env.ADMIN_PASSWORD },
	});
	if (login.status() !== 200) throw new Error("login failed " + login.status());

	// Kenya Health Settings > Patient SMS (just that section)
	await open(page, "/desk/kenya-health-settings");
	const section = page.locator(".form-section").filter({ hasText: "Send Appointment Reminders" }).first();
	await section.scrollIntoViewIfNeeded();
	await page.waitForTimeout(500);
	await section.screenshot({ path: path.join(outDir, "02-health-settings.png") });
	console.log("shot 02-health-settings.png");
	if (process.env.ONLY_SETTINGS) return browser.close();

	// Patient: consent tick and the SMS menu
	await open(page, "/desk/patient/" + PATIENT);
	await page.locator('.inner-group-button[data-label="SMS"] button').first().click();
	await page.waitForTimeout(600);
	await shot(page, "03-patient-sms-menu.png");

	// Send SMS dialog. The menu renders outside the normal DOM, so click the
	// first item by its position under the SMS button.
	const box = await page.locator('.inner-group-button[data-label="SMS"] button').first().boundingBox();
	await page.mouse.click(box.x + 40, box.y + box.height + 22);
	await page.waitForSelector(".modal:visible select[data-fieldname='template']");
	await page.selectOption(".modal:visible select[data-fieldname='template']", { index: 1 });
	await page.waitForTimeout(600);
	await shot(page, "04-send-dialog.png");
	await page.locator('.modal:visible button:has-text("Send")').last().click();
	await page.waitForTimeout(1800);
	await shot(page, "05-sent.png");

	// SMS history for the patient
	await open(
		page,
		"/desk/bulk-sms-log?reference_doctype=Patient&reference_name=" + encodeURIComponent(PATIENT)
	);
	await shot(page, "06-sms-history.png");

	// Campaign
	await open(page, "/desk/patient-sms-campaign/new");
	await page.fill("input[data-fieldname='title']", "Women's health day - November");
	await page.fill("input[data-fieldname='sex']", "Female");
	await page.waitForTimeout(900);
	await page.keyboard.press("Escape");
	await page.fill("input[data-fieldname='age_from']", "18");
	await page.fill("input[data-fieldname='age_to']", "49");
	await page.fill(
		"textarea[data-fieldname='message']",
		"Free cervical cancer screening for women this Saturday, 8am to 1pm, at Kijani Valley Hospital. Walk in, no appointment needed."
	);
	await page.keyboard.press("Control+s");
	await page.waitForTimeout(2500);
	await scrollTo(page, "Who Receives It");
	await shot(page, "07-campaign-form.png");
	await page.locator('button:has-text("Preview Recipients & Cost")').first().click();
	await page.waitForTimeout(2500);
	await shot(page, "08-campaign-preview.png");
	await page.keyboard.press("Escape");
	await page.waitForTimeout(800);
	await page.keyboard.press("Control+s");
	await page.waitForTimeout(1200);
	await page.locator('.modal:visible button:has-text("Yes")').last().click();
	// Wait for the background send to finish before touching the settings.
	const name = decodeURIComponent(new URL(page.url()).pathname.split("/").pop());
	for (let i = 0; i < 40; i++) {
		const r = await page.request.get(
			base + "/api/method/frappe.client.get_value?doctype=Patient SMS Campaign&fieldname=status&filters=" +
				encodeURIComponent(JSON.stringify({ name }))
		);
		const status = ((await r.json()).message || {}).status;
		if (status === "Completed" || status === "Failed") {
			console.log("campaign", name, status);
			break;
		}
		await page.waitForTimeout(1500);
	}
	const campaign = page.url();
	await open(page, new URL(campaign).pathname);
	await scrollTo(page, "Message", 60);
	await shot(page, "09-campaign-result.png");

	// Bulk SMS Settings, shown with the real API address
	await page.request.post(base + "/api/method/frappe.client.set_value", {
		headers: { "X-Frappe-CSRF-Token": await page.evaluate(() => frappe.csrf_token) },
		data: {
			doctype: "Bulk SMS Settings",
			name: "Bulk SMS Settings",
			fieldname: "api_base_url",
			value: "https://roycetalk.com",
		},
	});
	await open(page, "/desk/bulk-sms-settings");
	await shot(page, "01-bulk-sms-settings.png");

	await browser.close();
})().catch((e) => {
	console.error(e);
	process.exit(1);
});
