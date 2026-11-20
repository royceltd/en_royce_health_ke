// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

frappe.query_reports["Radiology Worklist"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{
			fieldname: "exam_status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["Open", "Requested", "Performed", "Reported", "Verified", "All"],
			default: "Open",
		},
		{
			fieldname: "modality",
			label: __("Modality"),
			fieldtype: "Select",
			options: ["", "X-ray", "Ultrasound", "CT", "MRI", "Mammography", "Fluoroscopy", "Contrast study"],
		},
	],
	// Images: the exam's viewer link (radiology.viewer_url), opened on the hospital network
	formatter(value, row, column, data, default_formatter) {
		if (column.fieldname === "images")
			return value
				? `<a href="${frappe.utils.escape_html(value)}" target="_blank" rel="noopener noreferrer">${__("View")}</a>`
				: "";
		return default_formatter(value, row, column, data);
	},
};
