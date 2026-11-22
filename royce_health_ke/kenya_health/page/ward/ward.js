/* global royce_health_ke */
// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

// The ward: patients waiting for a bed (admitted from the consultation),
// patients another ward is transferring here, and those on the ward
// (royce_health_ke.WardPage, public/js/ward_page.js).

frappe.pages["ward"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Ward"),
		single_column: true,
	});
	wrapper.ward_page = new royce_health_ke.WardPage(page, false);
};

frappe.pages["ward"].on_page_show = function (wrapper) {
	wrapper.ward_page && wrapper.ward_page.refresh();
};
