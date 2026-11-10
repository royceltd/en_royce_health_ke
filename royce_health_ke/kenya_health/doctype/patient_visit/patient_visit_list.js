// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

// The waiting list: filter by Station to get one station's queue. Waiting
// time turns orange after 30 minutes and red after an hour; abnormal triage
// vitals show as a red pill.
frappe.listview_settings["Patient Visit"] = {
	add_fields: ["status", "queue_status", "current_station", "sent_at", "vitals_status"],
	filters: [["status", "=", "Open"]],
	get_indicator(doc) {
		if (doc.status === "Completed") return [__("Completed"), "green", "status,=,Completed"];
		if (doc.status === "Cancelled") return [__("Cancelled"), "red", "status,=,Cancelled"];
		const station = __(doc.current_station || "");
		return doc.queue_status === "Seen"
			? [__("{0}: seen", [station]), "blue", `current_station,=,${doc.current_station}`]
			: [__("{0}: waiting", [station]), "orange", `current_station,=,${doc.current_station}`];
	},
	formatters: {
		sent_at(value, df, doc) {
			if (!value || doc.status !== "Open" || doc.queue_status !== "Waiting") return "";
			const minutes = Math.max(0, Math.floor(moment().diff(frappe.datetime.str_to_obj(value), "minutes")));
			const colour = minutes >= 60 ? "red" : minutes >= 30 ? "orange" : "gray";
			const text = minutes >= 60 ? __("{0} h {1} min", [Math.floor(minutes / 60), minutes % 60]) : __("{0} min", [minutes]);
			return `<span class="indicator-pill ${colour}"><span>${text}</span></span>`;
		},
		vitals_status(value) {
			if (!value) return "";
			return `<span class="indicator-pill ${value === "Abnormal" ? "red" : "green"}"><span>${__(value)}</span></span>`;
		},
	},
};
