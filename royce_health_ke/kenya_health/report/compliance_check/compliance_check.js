// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

frappe.query_reports["Compliance Check"] = {
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "status" && data) {
			const colour = { Pass: "green", Fail: "red", Advice: "blue" }[data.status] || "gray";
			return `<span class="indicator-pill ${colour}"><span>${frappe.utils.escape_html(__(data.status))}</span></span>`;
		}
		return value;
	},
};
