// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

// The vaccine fridge's monthly temperature recording sheet.
frappe.query_reports["Fridge Temperature Sheet"] = {
	filters: [
		{
			fieldname: "fridge",
			label: __("Fridge"),
			fieldtype: "Link",
			options: "Cold Chain Fridge",
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(frappe.datetime.get_today()),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To"),
			fieldtype: "Date",
			default: frappe.datetime.month_end(frappe.datetime.get_today()),
			reqd: 1,
		},
	],
	formatter(value, row, column, data, default_formatter) {
		const out = default_formatter(value, row, column, data);
		const flag = data && { am_temp: data.am_flag, pm_temp: data.pm_flag }[column.fieldname];
		if (flag)
			return `<span style="color:var(--${
				flag === "Too cold" ? "blue" : "red"
			}-600);font-weight:600" title="${__(flag)}">${out}</span>`;
		return out;
	},
};
