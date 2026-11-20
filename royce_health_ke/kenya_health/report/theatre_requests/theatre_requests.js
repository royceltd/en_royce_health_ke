// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

// Procedures sent to Theatre, waiting to be booked. Book opens a Theatre
// Booking filled from the request (patient, procedure, urgency, admission).
frappe.query_reports["Theatre Requests"] = {
	filters: [],
	formatter(value, row, column, data, default_formatter) {
		if (column.fieldname === "book" && data && data.name)
			return `<button class="btn btn-xs btn-primary" onclick='royce_health_ke_book_theatre(${frappe.utils.escape_html(
				JSON.stringify(data.name)
			)}); return false;'>${__("Book")}</button>`;
		const out = default_formatter(value, row, column, data);
		if (column.fieldname === "urgency" && data && data.urgency !== "Elective")
			return `<b style="color:var(--red-600)">${out}</b>`;
		return out;
	},
};

window.royce_health_ke_book_theatre = function (request) {
	const rows = frappe.query_report.data || [];
	const r = rows.find((x) => x.name === request);
	if (!r) return;
	frappe.new_doc("Theatre Booking", {
		service_request: r.name,
		patient: r.patient,
		procedure_template: r.template_dn,
		priority: r.urgency,
		inpatient_record: r.inpatient_record || "",
	});
};
