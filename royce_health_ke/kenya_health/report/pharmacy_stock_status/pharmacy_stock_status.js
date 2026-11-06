// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

const STATUS_COLOURS = {
	"Out of Stock": "red",
	"Below Reorder Level": "orange",
	"Low Cover": "orange",
	Expiring: "yellow",
	OK: "green",
};

frappe.query_reports["Pharmacy Stock Status"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: ["", "Out of Stock", "Below Reorder Level", "Low Cover", "Expiring", "OK"] },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "status" && data && data.status) {
			value = `<span class="indicator-pill ${STATUS_COLOURS[data.status] || "gray"}">${__(data.status)}</span>`;
		}
		return value;
	},
};
