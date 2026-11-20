# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""The Theatre request type (Bethesda, 20 Nov 2026: "we send patient and get
as a request in the next module"): procedures in the Surgical Procedures item
group are requested to Theatre and booked from Theatre Requests."""

from royce_health_ke import routing


def execute():
	routing.add_theatre()
