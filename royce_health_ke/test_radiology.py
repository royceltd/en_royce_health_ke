# Copyright (c) 2026, Royce Technologies LTD and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from royce_health_ke.radiology import before_insert_observation, is_imaging


class IntegrationTestRadiology(IntegrationTestCase):
	def test_imaging_observation_gets_accession_and_status(self):
		obs = frappe.new_doc("Observation")
		obs.observation_category = "Imaging"
		before_insert_observation(obs)
		self.assertTrue(obs.ke_accession_number.startswith("RAD-"))
		self.assertEqual(obs.ke_exam_status, "Requested")

	def test_lab_and_component_observations_are_left_alone(self):
		lab = frappe.new_doc("Observation")
		lab.observation_category = "Laboratory"
		before_insert_observation(lab)
		self.assertFalse(lab.get("ke_accession_number"))
		self.assertFalse(is_imaging(lab))
		component = frappe.new_doc("Observation")
		component.update({"observation_category": "Imaging", "parent_observation": "X"})
		before_insert_observation(component)
		self.assertFalse(component.get("ke_accession_number"))

	def test_accession_numbers_are_unique(self):
		numbers = set()
		for _i in range(3):
			obs = frappe.new_doc("Observation")
			obs.observation_category = "Imaging"
			before_insert_observation(obs)
			numbers.add(obs.ke_accession_number)
		self.assertEqual(len(numbers), 3)
