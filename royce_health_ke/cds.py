# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Clinical decision support: evidence-based alerts at the consultation.

- Clinical Alert Rule: the hospital's own rules (sex, age, and conditions on
  the problem list, vital signs, lab results, allergy list and the drugs
  being prescribed), each with a recommendation and its guideline. A few
  common ones are seeded; clinicians review and change them (ADR-023).
- Medication alerts: a drug flagged as recalled (Medication > Recalled) or
  with side effects to explain to the patient (Medication > Side Effects).
- Marley's own allergy and drug-interaction checks (Medication Alert Log)
  still run on prescribing; these alerts add to them.

When a consultation is saved, the rules are checked and each new alert is
logged once per consultation (Clinical Alert Log). The consultation form
shows the pending alerts; the clinician marks each "Acted on" or "Override"
with a reason. The Clinical Alert Summary report counts alerts shown and
responded to per clinician. Alerts never block saving or submitting.
Switch them all off in Kenya Health Settings (Clinical Alerts)."""

import operator

import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate, now_datetime

from royce_health_ke.moh.moh705 import codings
from royce_health_ke.vitals import _number, age_in_years

OPERATORS = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge, "=": operator.eq}
SEVERITY_ORDER = {"Critical": 0, "Warning": 1, "Info": 2}


def enabled():
	value = frappe.db.get_single_value("Kenya Health Settings", "clinical_alerts")
	return value is None or cint(value)


def _words(text):
	return [w.strip().lower() for w in (text or "").split(",") if w.strip()]


# Patient context --------------------------------------------------------------------


class Context:
	"""What the rules look at, loaded lazily for one consultation."""

	def __init__(self, encounter):
		self.encounter = encounter
		self.day = getdate(encounter.encounter_date)
		p = frappe.db.get_value("Patient", encounter.patient, ["sex", "dob", "allergies"], as_dict=True) or {}
		self.sex = p.get("sex")
		self.age = age_in_years(p.get("dob"), self.day) if p.get("dob") else None
		self._allergy_text = p.get("allergies") or ""
		self._cache = {}

	def diagnosis_codes(self, look_back_days):
		key = ("dx", look_back_days)
		if key not in self._cache:
			diagnoses = {r.diagnosis for r in self.encounter.get("diagnosis") or [] if r.diagnosis}
			if look_back_days:
				earlier = frappe.get_all(
					"Patient Encounter",
					filters={
						"patient": self.encounter.patient,
						"docstatus": 1,
						"name": ["!=", self.encounter.name or ""],
						"encounter_date": ["between", [add_days(self.day, -look_back_days), self.day]],
					},
					pluck="name",
				)
				if earlier:
					diagnoses |= set(
						frappe.get_all(
							"Patient Encounter Diagnosis",
							filters={"parenttype": "Patient Encounter", "parent": ["in", earlier]},
							pluck="diagnosis",
						)
					)
			codes = codings("Diagnosis", diagnoses)
			self._cache[key] = [
				(system, (code or "").upper()) for d in diagnoses for system, code in codes.get(d, [])
			]
		return self._cache[key]

	def vital(self, field, look_back_days):
		days = look_back_days or 1
		rows = frappe.get_all(
			"Vital Signs",
			filters={
				"patient": self.encounter.patient,
				"docstatus": ["!=", 2],
				"signs_date": ["between", [add_days(self.day, -(days - 1)), self.day]],
			},
			fields=[field],
			order_by="signs_date desc, signs_time desc, creation desc",
		)
		for row in rows:
			value = _number(row.get(field))
			if value is not None and (value or field.endswith("_z")):
				return value
		return None

	def lab_value(self, name_contains, look_back_days):
		days = look_back_days or 30
		# Marley leaves `date` empty on tests made from an order; use the result date then.
		window = [add_days(self.day, -days), self.day]
		tests = frappe.get_all(
			"Lab Test",
			filters={"patient": self.encounter.patient, "docstatus": ["!=", 2]},
			or_filters=[["date", "between", window], ["result_date", "between", window]],
			pluck="name",
			order_by="creation desc",
		)
		if not tests:
			return None
		needle = name_contains.lower()
		rows = frappe.get_all(
			"Normal Test Result",
			filters={"parenttype": "Lab Test", "parent": ["in", tests]},
			fields=["parent", "lab_test_name", "lab_test_event", "result_value"],
		)
		order = {t: i for i, t in enumerate(tests)}
		for row in sorted(rows, key=lambda r: order[r.parent]):
			label = f"{row.lab_test_name or ''} {row.lab_test_event or ''}".lower()
			value = _number(row.result_value)
			if needle in label and value is not None:
				return value
		return None

	def allergy_text(self):
		if "allergy" not in self._cache:
			names = frappe.get_all(
				"Patient Allergy",
				filters={"patient": self.encounter.patient, "status": "Active"},
				pluck="allergy",
			)
			self._cache["allergy"] = " ".join([self._allergy_text, *names]).lower()
		return self._cache["allergy"]

	def medications(self):
		"""(medication, display text) for each drug prescribed in this consultation."""
		out = []
		for row in self.encounter.get("drug_prescription") or []:
			text = " ".join(filter(None, [row.medication, row.drug_name, row.drug_code])).lower()
			out.append((row.medication, text))
		return out


def condition_met(cond, ctx):
	kind = cond.condition
	if kind == "Diagnosis":
		prefixes = [p.upper() for p in _words(cond.code_prefix)]
		return any(
			(not cond.code_system or system == cond.code_system) and code.startswith(p)
			for system, code in ctx.diagnosis_codes(cint(cond.look_back_days))
			for p in prefixes
		)
	if kind in ("Vital Sign", "Lab Result"):
		value = (
			ctx.vital(cond.vital_sign, cint(cond.look_back_days))
			if kind == "Vital Sign"
			else ctx.lab_value(cond.lab_result_name or "", cint(cond.look_back_days))
		)
		compare = OPERATORS.get(cond.operator)
		return value is not None and compare is not None and compare(value, cond.value or 0)
	if kind == "Allergy":
		text = ctx.allergy_text()
		return any(w in text for w in _words(cond.text))
	if kind == "Medication":
		return any(w in text for _m, text in ctx.medications() for w in _words(cond.text))
	return False


def rule_matches(rule, ctx):
	if rule.sex not in (None, "", "Any") and rule.sex != ctx.sex:
		return False
	if rule.min_age_years and (ctx.age is None or ctx.age < rule.min_age_years):
		return False
	if rule.max_age_years and (ctx.age is None or ctx.age >= rule.max_age_years):
		return False
	if not rule.conditions and not (
		rule.min_age_years or rule.max_age_years or rule.sex not in (None, "", "Any")
	):
		return False  # a rule with nothing to check would fire on everyone
	return all(condition_met(c, ctx) for c in rule.conditions)


# Evaluating a consultation ---------------------------------------------------------------


def evaluate(encounter):
	"""[{key, kind, rule, severity, message}] for this consultation."""
	ctx = Context(encounter)
	alerts = []
	for name in frappe.get_all("Clinical Alert Rule", filters={"enabled": 1}, pluck="name"):
		rule = frappe.get_cached_doc("Clinical Alert Rule", name)
		if rule_matches(rule, ctx):
			message = rule.recommendation
			if rule.evidence_source:
				message += "\n" + _("Source: {0}").format(rule.evidence_source)
			alerts.append(
				{
					"key": f"rule:{rule.name}",
					"kind": "Clinical Rule",
					"rule": rule.name,
					"severity": rule.severity or "Warning",
					"message": f"{rule.rule_name}: {message}",
				}
			)
	for medication, _text in ctx.medications():
		if not medication:
			continue
		m = frappe.db.get_value(
			"Medication", medication, ["ke_recalled", "ke_recall_note", "ke_side_effects"], as_dict=True
		)
		if not m:
			continue
		if cint(m.ke_recalled):
			alerts.append(
				{
					"key": f"recalled:{medication}",
					"kind": "Recalled Medication",
					"rule": None,
					"severity": "Critical",
					"message": _("{0} has been RECALLED. Do not prescribe it. {1}")
					.format(medication, m.ke_recall_note or "")
					.strip(),
				}
			)
		if m.ke_side_effects:
			alerts.append(
				{
					"key": f"side-effects:{medication}",
					"kind": "Side Effects",
					"rule": None,
					"severity": "Info",
					"message": _("{0}: tell the patient about these side effects: {1}").format(
						medication, m.ke_side_effects
					),
				}
			)
	return sorted(alerts, key=lambda a: SEVERITY_ORDER.get(a["severity"], 9))


def encounter_saved(doc, method=None):
	"""Patient Encounter on_update / on_submit: log new alerts. Never blocks the clinician."""
	if not enabled():
		return
	try:
		log_alerts(doc)
	except Exception:
		frappe.log_error(title=_("Clinical alerts: could not check {0}").format(doc.name))


def log_alerts(encounter):
	existing = set(frappe.get_all("Clinical Alert Log", filters={"encounter": encounter.name}, pluck="key"))
	created = []
	for alert in evaluate(encounter):
		if alert["key"] in existing:
			continue
		created.append(
			frappe.get_doc(
				{
					"doctype": "Clinical Alert Log",
					**alert,
					"patient": encounter.patient,
					"encounter": encounter.name,
					"company": encounter.company,
					"response": "Pending",
					"shown_to": frappe.session.user,
					"shown_on": now_datetime(),
				}
			).insert(ignore_permissions=True)
		)
	return created


@frappe.whitelist()
def pending_alerts(encounter: str):
	frappe.has_permission("Patient Encounter", "read", encounter, throw=True)
	return frappe.get_all(
		"Clinical Alert Log",
		filters={"encounter": encounter, "response": "Pending"},
		fields=["name", "kind", "severity", "message"],
		order_by="creation asc",
	)


@frappe.whitelist()
def respond(log: str, response: str, reason: str | None = None):
	"""The clinician's answer to an alert: Acted On, or Overridden with a reason."""
	if response not in ("Acted On", "Overridden"):
		frappe.throw(_("Choose Acted On or Overridden."))
	doc = frappe.get_doc("Clinical Alert Log", log)
	frappe.has_permission("Patient Encounter", "write", doc.encounter, throw=True)
	if response == "Overridden" and not (reason or "").strip():
		frappe.throw(_("Give the reason for overriding the alert."))
	doc.update(
		{
			"response": response,
			"response_reason": (reason or "").strip(),
			"responded_by": frappe.session.user,
			"responded_on": now_datetime(),
		}
	)
	doc.save(ignore_permissions=True)
	return doc.response
