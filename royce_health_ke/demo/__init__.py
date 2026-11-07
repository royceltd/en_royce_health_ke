# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""One-command demo: a fictional Kenyan private hospital and one patient's
journey from walk-in to discharge.

    bench --site <site> set-config royce_health_demo 1
    bench --site <site> execute royce_health_ke.demo.load

Refuses to run unless the site opts in, so it can never touch a client's
live data. Idempotent: masters are created only when missing, and the
journey only when the demo patient doesn't exist yet. Everything is marked
fictional (patient details say DEMO)."""

import frappe

DEMO_COMPANY = "Kijani Valley Hospital Ltd"


def load(company: str = DEMO_COMPANY):
	if not frappe.conf.get("royce_health_demo"):
		frappe.throw(
			"Demo data is off for this site. Run `bench --site <site> set-config royce_health_demo 1` "
			"first - only on a demo or test site, never a client's live site."
		)
	frappe.set_user("Administrator")
	# frappe.locale.get_locale_value raises UnboundLocalError when no language
	# is set (bench console on a fresh site); bench execute and the desk set one.
	frappe.local.lang = frappe.local.lang or "en"

	from royce_health_ke.demo import (
		insurance,
		journey,
		kitchen_laundry,
		masters,
		maternity,
		radiology,
		theatre,
	)

	masters.ensure_company(company)
	frappe.db.commit()
	masters.load(company)
	insurance.setup(company)
	theatre.setup(company)
	radiology.setup(company)
	frappe.db.commit()
	result = {"cash_patient": journey.run(company)}
	frappe.db.commit()
	result["insured_patient"] = insurance.run(company)
	frappe.db.commit()
	result["maternity_patient"] = maternity.run(company)
	frappe.db.commit()
	result["theatre_patient"] = theatre.run(company)
	frappe.db.commit()
	result["radiology_patient"] = radiology.run(company)
	frappe.db.commit()
	result["kitchen_laundry"] = kitchen_laundry.run(company)
	frappe.db.commit()
	return result
