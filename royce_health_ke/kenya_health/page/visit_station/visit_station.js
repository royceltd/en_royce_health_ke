// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

// A queue row opens what the station does with the patient (IT demo, 17 Nov
// 2026): Triage the vital signs, the Doctor's Queue the consultation; anyone
// else the visit (royce_health_ke.visits.open_station). This page only
// redirects, replacing itself in the history so Back returns to the queue.
frappe.pages["visit-station"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({ parent: wrapper, title: __("Opening..."), single_column: true });
};

frappe.pages["visit-station"].on_page_show = function () {
	const visit = frappe.get_route()[1];
	if (!visit) return frappe.set_route("List", "Patient Visit");
	frappe.xcall("royce_health_ke.visits.open_station", { visit }).then((r) => {
		frappe.route_flags.replace_route = true;
		if (r.name) {
			frappe.set_route("Form", r.doctype, r.name);
		} else {
			frappe.new_doc(r.doctype, r.new);
		}
	});
};
