app_name = "royce_health_ke"
app_title = "Kenya Health"
app_publisher = "Royce Technologies LTD"
app_description = "Kenyan hospital management layer for Marley Health: SHA/HIE claims, private insurance, maternity, theatre, MOH reports"
app_email = "developer@roycetechnologies.co.ke"
app_license = "mit"

# Apps
# ------------------

# healthcare = Marley Health v16. eTIMS, M-Pesa, Kenyan accounting and payroll
# are used when installed but not required, so a clinic can start smaller.
required_apps = ["frappe/erpnext", "healthcare"]

# Installation
# ------------

after_install = "royce_health_ke.setup.install.after_install"
after_migrate = "royce_health_ke.setup.install.after_migrate"

# Patient Record Access: an audit trail outlives the records it points at
ignore_links_on_delete = ["Patient Record Access"]

doc_events = {
	"*": {
		"onload": "royce_health_ke.access.log_view",
		"before_print": "royce_health_ke.access.log_print",
	},
	"Patient": {"validate": "royce_health_ke.identity.validate_patient"},
	"Healthcare Practitioner": {"validate": "royce_health_ke.identity.validate_practitioner"},
	"Sales Invoice": {
		"before_validate": [
			"royce_health_ke.visit_bill.link_invoice",
			"royce_health_ke.billing.apply_bed_charge_basis",
			"royce_health_ke.kitchen.apply_meal_charges",
			"royce_health_ke.packages.apply_maternity_package",
			"royce_health_ke.cashier.invoice_before_validate",
		],
		"before_submit": "royce_health_ke.visit_bill.invoice_before_submit",
		"on_submit": "royce_health_ke.visit_bill.invoice_changed",
		"on_cancel": "royce_health_ke.visit_bill.invoice_changed",
	},
	"Payment Entry": {
		"before_validate": "royce_health_ke.cashier.payment_entry_before_validate",
		"on_submit": "royce_health_ke.visit_bill.payment_changed",
		"on_cancel": "royce_health_ke.visit_bill.payment_changed",
	},
	"Delivery Note": {"before_submit": "royce_health_ke.visit_bill.delivery_before_submit"},
	"Journal Entry": {"on_cancel": "royce_health_ke.claims.on_settlement_cancel"},
	"Observation": {"before_insert": "royce_health_ke.radiology.before_insert_observation"},
	"Lab Test": {
		"before_insert": "royce_health_ke.visit_bill.lab_test_before_insert",
		"after_insert": "royce_health_ke.visit_bill.orders_changed",
		"before_submit": "royce_health_ke.visit_bill.lab_test_before_submit",
		"on_submit": [
			"royce_health_ke.tat.lab_test_submitted",
			"royce_health_ke.sms.lab_test_submitted",
		],
	},
	"Vital Signs": {
		"validate": [
			"royce_health_ke.visits.link_vital_signs",
			"royce_health_ke.vitals.validate_vital_signs",
		],
		"on_update": "royce_health_ke.visits.vital_signs_saved",
		"on_submit": "royce_health_ke.visits.vital_signs_saved",
	},
	"Patient Insurance Coverage": {
		"before_validate": "royce_health_ke.schemes.price_consultation_cover",
	},
	"Patient Encounter": {
		"validate": "royce_health_ke.visits.link_encounter",
		"on_update": [
			"royce_health_ke.visits.encounter_saved",
			"royce_health_ke.history.save_history_to_patient",
		],
		"on_submit": [
			"royce_health_ke.visits.encounter_saved",
			"royce_health_ke.history.save_history_to_patient",
			"royce_health_ke.schemes.cover_consultation",
			"royce_health_ke.visit_bill.orders_changed",
		],
	},
}

jinja = {
	"methods": [
		"royce_health_ke.lcg.labour_care_guide_html",
		"royce_health_ke.printing.health_print_context",
		"royce_health_ke.printing.health_lab_results",
		"royce_health_ke.printing.health_lab_people",
		"royce_health_ke.printing.health_clinician",
		"royce_health_ke.printing.health_has_text",
		"royce_health_ke.printing.health_encounter_vitals",
		"royce_health_ke.printing.health_prescription_lines",
		"royce_health_ke.printing.health_encounter_time",
		"royce_health_ke.printing.health_discharge_details",
		"royce_health_ke.printing.health_imaging_details",
		"royce_health_ke.printing.health_operation_details",
		"royce_health_ke.printing.health_patient_card",
		"royce_health_ke.printing.health_diagnostic_rows",
		"royce_health_ke.printing.health_consent_details",
		"royce_health_ke.printing.health_checklist_details",
		"royce_health_ke.printing.health_anaesthesia_details",
		"royce_health_ke.printing.health_continuation_details",
		"royce_health_ke.printing.health_treatment_sheet",
	]
}

doctype_js = {
	"Patient": "public/js/patient.js",
	"Insurance Claim": "public/js/insurance_claim.js",
	"Observation": "public/js/observation.js",
	"Vital Signs": "public/js/vital_signs.js",
	"Patient Appointment": "public/js/patient_appointment.js",
	"Sales Invoice": "public/js/sales_invoice.js",
}

doctype_list_js = {"Vital Signs": "public/js/vital_signs_list.js"}

scheduler_events = {
	"daily": ["royce_health_ke.identity.remind_licence_expiry"],
	"hourly": ["royce_health_ke.sms.send_appointment_reminders"],
}

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "royce_health_ke",
# 		"logo": "/assets/royce_health_ke/logo.png",
# 		"title": "Kenya Health",
# 		"route": "/royce_health_ke",
# 		"has_permission": "royce_health_ke.api.permission.has_app_permission",
# 	}
# ]

# The dock, the rail down the left of the desk, is a document rather than a hook. Author it in
# Manage Dock on a developer-mode site and press Export to App, and it is written to
# `royce_health_ke/dock/royce_health_ke/royce_health_ke.json` for git to carry. An app that ships none has no
# rail: its sidebar gets a switcher in the header instead.
#
# A companion app, one that extends a host app rather than standing on its own, says so with
# `mount_on` on that same record, and its entries are appended to the host's rail. Mounting keeps
# the companion off the apps screen, so it takes precedence over any add_to_apps_screen above.

# Includes in <head>
# ------------------

# Marley's 8 sidebars share one module; give each only its own workspaces so
# the rail opens the sidebar clicked (see royce_health_ke/sidebar.py).
extend_bootinfo = [
	"royce_health_ke.sidebar.extend_bootinfo",
	"royce_health_ke.sms.extend_bootinfo",
	"royce_health_ke.identity.extend_bootinfo",
	"royce_health_ke.cashier.extend_bootinfo",
]

# include js, css files in header of desk.html
# app_include_css = "/assets/royce_health_ke/css/royce_health_ke.css"
# app_include_js = "/assets/royce_health_ke/js/royce_health_ke.js"

# include js, css files in header of web template
# web_include_css = "/assets/royce_health_ke/css/royce_health_ke.css"
# web_include_js = "/assets/royce_health_ke/js/royce_health_ke.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "royce_health_ke/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_kanban_js = {"doctype" : "public/js/doctype_kanban.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "royce_health_ke/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "royce_health_ke.utils.jinja_methods",
# 	"filters": "royce_health_ke.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "royce_health_ke.install.before_install"
# after_install = "royce_health_ke.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "royce_health_ke.uninstall.before_uninstall"
# after_uninstall = "royce_health_ke.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "royce_health_ke.utils.before_app_install"
# after_app_install = "royce_health_ke.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "royce_health_ke.utils.before_app_uninstall"
# after_app_uninstall = "royce_health_ke.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "royce_health_ke.build.after_build"

# To hook into the build process of other apps
# The list of apps being built is passed as an argument

# after_app_build = "royce_health_ke.build.after_app_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "royce_health_ke.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["royce_health_ke.search.awesomebar_results"]

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"royce_health_ke.tasks.all"
# 	],
# 	"daily": [
# 		"royce_health_ke.tasks.daily"
# 	],
# 	"hourly": [
# 		"royce_health_ke.tasks.hourly"
# 	],
# 	"weekly": [
# 		"royce_health_ke.tasks.weekly"
# 	],
# 	"monthly": [
# 		"royce_health_ke.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "royce_health_ke.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "royce_health_ke.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "royce_health_ke.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "royce_health_ke.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["royce_health_ke.utils.before_request"]
# after_request = ["royce_health_ke.utils.after_request"]

# Job Events
# ----------
# before_job = ["royce_health_ke.utils.before_job"]
# after_job = ["royce_health_ke.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"royce_health_ke.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []
