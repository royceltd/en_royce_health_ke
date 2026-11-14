// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

frappe.listview_settings["Bill Approval Request"] = {
	add_fields: ["status", "request_type"],
	get_indicator(doc) {
		const colours = { Pending: "orange", Approved: "green", Rejected: "red" };
		return [__(doc.status), colours[doc.status], "status,=," + doc.status];
	},
	filters: [["status", "=", "Pending"]],
};
