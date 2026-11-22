/* global royce_health_ke */
// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

// Casualty (Bethesda, PDF (12) points 6-7): patients sent from triage, waiting
// for a casualty bed, and those in casualty; a row opens the patient's screen
// with the Casualty tabs (royce_health_ke.WardPage, casualty.py).

frappe.pages["casualty"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Casualty"),
		single_column: true,
	});
	wrapper.casualty_page = new royce_health_ke.WardPage(page, true);
};

frappe.pages["casualty"].on_page_show = function (wrapper) {
	wrapper.casualty_page && wrapper.casualty_page.refresh();
};
