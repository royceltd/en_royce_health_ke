# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Draft deliveries that took "Spontaneous vaginal delivery" by default
(Bethesda, 21 Nov 2026: the partograph showed a mode nobody chose)."""

from royce_health_ke import partograph


def execute():
	partograph.clear_default_mode_of_delivery()
