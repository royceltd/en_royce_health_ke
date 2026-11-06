// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on("Theatre Booking", {
	setup(frm) {
		frm.set_query("theatre", () => ({
			query: "royce_health_ke.theatre.theatre_query",
			filters: { company: frm.doc.company },
		}));
	},
	refresh(frm) {
		if (frm.is_new()) return;
		const make = (doctype, label) =>
			frm.add_custom_button(
				label,
				() => frappe.new_doc(doctype, { theatre_booking: frm.doc.name }),
				__("Records"),
			);
		const open = (doctype, name, label) =>
			frm.add_custom_button(label, () => frappe.set_route("Form", doctype, name), __("Records"));

		if (frm.doc.status === "Scheduled" || frm.doc.status === "In Theatre") {
			frm.doc.surgical_consent
				? open("Surgical Consent", frm.doc.surgical_consent, __("Consent"))
				: make("Surgical Consent", __("Record Consent"));
			frm.doc.safety_checklist
				? open("Surgical Safety Checklist", frm.doc.safety_checklist, __("Safety Checklist"))
				: make("Surgical Safety Checklist", __("Start Safety Checklist"));
			frm.doc.anaesthesia_record
				? open("Anaesthesia Record", frm.doc.anaesthesia_record, __("Anaesthesia Record"))
				: make("Anaesthesia Record", __("Anaesthesia Record"));
		}
		if (frm.doc.clinical_procedure) {
			open("Clinical Procedure", frm.doc.clinical_procedure, __("Operation Note"));
		}

		const call = (method, args, message) =>
			frappe.call({ method, args, freeze: true }).then(() => {
				frappe.show_alert({ message, indicator: "green" });
				frm.reload_doc();
			});
		if (frm.doc.status === "Scheduled") {
			frm.add_custom_button(__("Into Theatre"), () =>
				call("royce_health_ke.theatre.start", { booking: frm.doc.name }, __("Procedure started")),
			).addClass("btn-primary");
			for (const status of ["Postponed", "Cancelled"]) {
				frm.add_custom_button(
					__(status === "Postponed" ? "Postpone" : "Cancel"),
					() =>
						frappe.prompt(
							{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
							(v) =>
								call(
									"royce_health_ke.theatre.set_status",
									{ booking: frm.doc.name, status, reason: v.reason },
									__(status),
								),
						),
					__("Status"),
				);
			}
		}
		if (frm.doc.status === "Postponed") {
			frm.add_custom_button(__("Reschedule"), () =>
				call(
					"royce_health_ke.theatre.set_status",
					{ booking: frm.doc.name, status: "Scheduled", reason: "" },
					__("Scheduled"),
				),
			);
		}
		if (frm.doc.status === "In Theatre") {
			frm.add_custom_button(__("Complete"), () =>
				call("royce_health_ke.theatre.complete", { booking: frm.doc.name }, __("Procedure completed")),
			).addClass("btn-primary");
		}
	},
});
