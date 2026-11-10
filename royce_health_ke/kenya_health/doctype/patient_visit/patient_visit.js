// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

const STATIONS = [
	"Triage",
	"Consultation",
	"Casualty",
	"Laboratory",
	"Radiology",
	"Pharmacy",
	"Procedure Room",
	"Cashier",
	"Admission",
];

frappe.ui.form.on("Patient Visit", {
	setup(frm) {
		frm.set_query("insurance_policy", () => ({
			filters: { patient: frm.doc.patient, insurance_payor: frm.doc.insurance_payor, docstatus: 1 },
		}));
		frm.set_query("insurance_plan", () => ({ filters: { insurance_payor: frm.doc.insurance_payor } }));
		frm.set_query("practitioner", () => ({ filters: { status: "Active" } }));
	},

	refresh(frm) {
		if (frm.is_new() || frm.doc.status !== "Open") return;
		const call = (method, args, message) =>
			frappe.call({ method: `royce_health_ke.visits.${method}`, args, freeze: true }).then(() => {
				if (message) frappe.show_alert({ message, indicator: "green" });
				frm.reload_doc();
			});

		if (frm.doc.queue_status === "Waiting") {
			frm.add_custom_button(__("Seen"), () => call("acknowledge", { visit: frm.doc.name }, __("Seen"))).addClass(
				"btn-primary",
			);
		}
		frm.add_custom_button(__("Send To"), () => send_to_dialog(frm, call));

		const make = (doctype, label, values) =>
			frm.add_custom_button(label, () => frappe.new_doc(doctype, values), __("Record"));
		make("Vital Signs", __("Vital Signs"), {
			patient: frm.doc.patient,
			company: frm.doc.company,
			ke_patient_visit: frm.doc.name,
		});
		make("Patient Encounter", __("Consultation"), {
			patient: frm.doc.patient,
			practitioner: frm.doc.practitioner,
			appointment_type: frm.doc.appointment_type,
			medical_department: frm.doc.department,
			company: frm.doc.company,
			ke_patient_visit: frm.doc.name,
		});
		if (frm.doc.vital_signs) {
			frm.add_custom_button(__("Latest Vital Signs"), () => frappe.set_route("Form", "Vital Signs", frm.doc.vital_signs), __("View"));
		}
		if (frm.doc.encounter) {
			frm.add_custom_button(__("Latest Consultation"), () => frappe.set_route("Form", "Patient Encounter", frm.doc.encounter), __("View"));
		}
		frm.add_custom_button(__("Complete Visit"), () =>
			frappe.confirm(__("Complete this visit? The patient leaves every waiting list."), () =>
				call("complete", { visit: frm.doc.name }, __("Visit completed")),
			),
		__("Status"));
		frm.add_custom_button(__("Cancel Visit"), () =>
			frappe.prompt({ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 }, (v) =>
				call("cancel", { visit: frm.doc.name, reason: v.reason }, __("Visit cancelled")),
			),
		__("Status"));

		if (frm.doc.vitals_status === "Abnormal") {
			frm.dashboard.set_headline(__("Abnormal vitals at triage. See the latest vital signs."), "red");
		}
	},

	patient(frm) {
		if (frm.doc.patient && frm.doc.payment_method === "Insurance") fill_policy(frm);
	},
	payment_method(frm) {
		if (frm.doc.patient && frm.doc.payment_method === "Insurance") fill_policy(frm);
	},
	insurance_policy(frm) {
		if (!frm.doc.insurance_policy) return;
		frappe.db
			.get_value("Patient Insurance Policy", frm.doc.insurance_policy, [
				"insurance_payor",
				"insurance_plan",
				"policy_number",
				"ke_relation",
				"ke_principal_member",
				"ke_principal_member_number",
			])
			.then(({ message: p }) => {
				if (!p) return;
				frm.set_value({
					insurance_payor: p.insurance_payor,
					insurance_plan: p.insurance_plan,
					member_number: p.policy_number,
					relation: p.ke_relation || "Principal",
					principal_member: p.ke_principal_member,
					principal_member_number: p.ke_principal_member_number,
				});
			});
	},
});

// The patient's active policy, when there is exactly one.
function fill_policy(frm) {
	if (frm.doc.insurance_policy) return;
	frappe.call("royce_health_ke.visits.patient_policies", { patient: frm.doc.patient }).then(({ message }) => {
		if (message && message.length === 1) frm.set_value("insurance_policy", message[0].name);
		else if (message && message.length > 1)
			frappe.show_alert({ message: __("This patient has {0} active policies: choose one.", [message.length]), indicator: "blue" });
	});
}

function send_to_dialog(frm, call) {
	const d = new frappe.ui.Dialog({
		title: __("Send {0} to", [frm.doc.patient_name]),
		fields: [
			{
				fieldname: "station",
				fieldtype: "Select",
				label: __("Station"),
				options: STATIONS.filter((s) => s !== frm.doc.current_station || frm.doc.queue_status !== "Waiting"),
				reqd: 1,
				default: frm.doc.current_station === "Triage" ? "Consultation" : undefined,
			},
			{
				fieldname: "practitioner",
				fieldtype: "Link",
				options: "Healthcare Practitioner",
				label: __("Practitioner"),
				default: frm.doc.practitioner,
				depends_on: "eval:doc.station == 'Consultation'",
			},
			{ fieldname: "note", fieldtype: "Data", label: __("Note") },
		],
		primary_action_label: __("Send"),
		primary_action(v) {
			d.hide();
			call("send_to", { visit: frm.doc.name, ...v }, __("Sent to {0}", [__(v.station)]));
		},
	});
	d.show();
}
