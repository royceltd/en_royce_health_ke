// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

// Start the day's Patient Visit from an appointment: the patient joins the queue.
frappe.ui.form.on("Patient Appointment", {
	refresh(frm) {
		if (frm.is_new() || !["Scheduled", "Open", "Confirmed", "Checked In"].includes(frm.doc.status)) return;
		if (!frappe.model.can_create("Patient Visit")) return;
		frm.add_custom_button(__("Start Visit"), () =>
			frappe.new_doc("Patient Visit", {
				patient: frm.doc.patient,
				company: frm.doc.company,
				practitioner: frm.doc.practitioner,
				department: frm.doc.department,
				appointment_type: frm.doc.appointment_type,
				appointment: frm.doc.name,
				payment_method: frm.doc.insurance_policy ? "Insurance" : "Cash",
				insurance_payor: frm.doc.insurance_payor,
				insurance_policy: frm.doc.insurance_policy,
			}),
		);
	},
});
