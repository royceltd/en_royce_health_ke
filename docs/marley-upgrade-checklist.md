# Marley / ERPNext upgrade checklist

Follow this checklist every time the pinned Marley Health (`healthcare`), ERPNext or Frappe version moves in `deploy/apps.health.json`.

The rule is that upgrades come first. We stay close to Marley and don't hold back an upgrade to protect a customisation. When an upgrade breaks something of ours, we change our code, not Marley's.

## How we extend Marley (low risk, checked by the test suite)

- **Our own fields** (`ke_` prefix, `setup/custom_fields.py`). They are re-applied on every migrate.
- **Our own doctypes, pages and reports**: Patient Visit, the worklists, the Cashier, the MOH reports.
- **Form scripts that add to Marley's forms** (`doctype_js`). They never replace Marley's own scripts.
- **Doc events** (`hooks.py` `doc_events`). These run next to Marley's controllers.
- **Set-once property setters** (`forms.py`, `consultation.apply_layout`, ADR-023), for hidden fields, column choices, labels and defaults.
- **Site-data fixes** (`setup/marley_fixes.py`). Each fix only touches data that is still broken.

## The places that can break: test each one at every upgrade

1. **The Marley adapter (`marley.py`).** It holds `SUPPORTED`, the Marley version we support, and `USES`, every Marley function we call. It also replaces `healthcare.healthcare.utils.get_appointment_billing_item_and_rate` with our consultation fee rule (`fees.billing_item_and_rate`). The replacement is installed on `before_request`/`before_job`.
   - Run `test_marley`. It checks the version, that every function in `USES` still exists, our call signatures, and that no other module imports from `healthcare`.
   - Read Marley's diff of `utils.get_appointment_billing_item_and_rate`, `get_healthcare_services_to_invoice` and `get_drugs_to_invoice`. If Marley changed its rule, merge the improvement into `fees.py`.
2. **Whitelisted methods we replace** (`override_whitelisted_methods`): `get_healthcare_services_to_invoice` and `get_appointment_billing_item_and_rate`. Check that their arguments and return shape still match Marley's.
   - Test: an invoice's Get Items From > Healthcare Services, and a cash visit bill, both price correctly.
3. **Marley classes we extend** (`extend_doctype_class`):
   - `Patient Insurance Coverage` → `coverage.CoverageEligibility.set_insurance_coverage`
   - `Medication` → `formulary.MedicationLinking` (`before_naming`, `validate`, `after_insert`, `update_item_and_item_price`)

   If Marley renames or removes one of these methods, our override silently stops running. Check that each method still exists in Marley's class with the same name.
   - Test: an insured visit picks the right scheme eligibility for a drug, and a new Medication links to its item and price.
4. **Our SQL on Marley's tables.** The worklists (`lab.py`, the radiology and pharmacy worklists), `payment_status.py`, `visit_bill.py`, `consultation.py` and the MOH reports read Service Request, Lab Test, Observation, Medication Request, Patient Encounter and Lab Prescription fields directly. A renamed or removed field breaks them.
   - Run the full test suite, then walk one OPD journey on a staging site (step 7).
5. **The consultation tab layout** (`consultation.TABS` plus one `field_order` property setter). A new Marley field on Patient Encounter can land under the wrong tab. It looks wrong but nothing breaks.
   - Open a consultation and check each tab.
6. **Marley flags we rely on**: `Patient Encounter.submit_orders_on_save` (behind Send Requests), the order placement in `make_service_request`/`make_medication_request` (skips rows that already have an order), and the Lab Prescription columns (`lab_test_code` for lab tests, `observation_template` for imaging only).
7. **Walk the OPD journey on staging, signed in as role users, not Administrator**: register → visit → Cashier (fee) → triage → consultation (observation, requests, Send Requests) → Cashier → lab result → imaging report → prescription → pharmacy dispense → complete. Then repeat with an insured patient.

## Release steps

1. Move `SUPPORTED` in `marley.py` and the pin in `deploy/apps.health.json` together.
2. Run the full test suite locally and in CI.
3. Work through the checklist above and note anything found in the release notes.
4. Deploy to the demo site first, walk the journey, then deploy to the client sites.
