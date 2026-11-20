// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

// An MOH commodity report (F-CDRR) for a month. The form's lines and their
// mapping to stock items are in Commodity Report Form.
// [first day, last day] of last month (frappe.datetime.month_start takes no date)
function ke_last_month() {
	const start = frappe.datetime.add_months(frappe.datetime.get_today(), -1).slice(0, 8) + "01";
	return [start, frappe.datetime.add_days(frappe.datetime.add_months(start, 1), -1)];
}

frappe.query_reports["Commodity Report"] = {
	filters: [
		{
			fieldname: "form",
			label: __("Form"),
			fieldtype: "Link",
			options: "Commodity Report Form",
			reqd: 1,
			get_query: () => ({ filters: { disabled: 0 } }),
		},
		{
			fieldname: "from_date",
			label: __("From"),
			fieldtype: "Date",
			default: ke_last_month()[0],
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To"),
			fieldtype: "Date",
			default: ke_last_month()[1],
			reqd: 1,
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "warehouse",
			label: __("Store (empty = all)"),
			fieldtype: "Link",
			options: "Warehouse",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		if (data && data.is_section)
			return column.fieldname === "commodity"
				? `<b>${frappe.utils.escape_html(value || "")}</b>`
				: "";
		if (data && data.not_mapped)
			return column.fieldname === "item"
				? `<span class="text-muted">${__("Not mapped")}</span>`
				: ["commodity", "unit"].includes(column.fieldname)
				? default_formatter(value, row, column, data)
				: "";
		const out = default_formatter(value, row, column, data);
		if (data && column.fieldname === "days_out" && value > 0)
			return `<span style="color:var(--red-600);font-weight:600">${out}</span>`;
		return out;
	},
};
