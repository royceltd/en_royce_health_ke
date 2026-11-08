# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Existing sites: make the hospital print formats the default once (new sites
get this at install). A default the client already chose is left alone."""

from royce_health_ke.printing import set_default_print_formats


def execute():
	set_default_print_formats()
