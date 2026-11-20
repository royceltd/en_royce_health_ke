# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Imaging: an exam's images in the hospital's viewer, from the accession
number (Kenya Health Settings, Image Viewer Link) or a link typed on the exam."""

import frappe
from frappe.tests import IntegrationTestCase

from royce_health_ke.radiology import viewer_url

SETTINGS = "Kenya Health Settings"


class TestImageViewerLink(IntegrationTestCase):
	def setUp(self):
		self.before = frappe.db.get_single_value(SETTINGS, "pacs_viewer_url")

	def tearDown(self):
		frappe.db.set_single_value(SETTINGS, "pacs_viewer_url", self.before)

	def exam(self, **values):
		exam = frappe._dict(
			ke_accession_number="RAD-2026.11.21-0007", patient="Jane Doe", ke_exam_status="Performed"
		)
		exam.update(values)
		return exam

	def test_from_the_accession_number(self):
		frappe.db.set_single_value(
			SETTINGS,
			"pacs_viewer_url",
			"http://192.168.1.20:8042/ui/app/#/filtered-studies?AccessionNumber={accession}&p={patient}",
		)
		self.assertEqual(
			viewer_url(self.exam()),
			"http://192.168.1.20:8042/ui/app/#/filtered-studies?AccessionNumber=RAD-2026.11.21-0007&p=Jane%20Doe",
		)
		# no images before the exam is performed
		self.assertIsNone(viewer_url(self.exam(ke_exam_status="Requested")))

	def test_typed_link_wins_and_only_web_links(self):
		frappe.db.set_single_value(SETTINGS, "pacs_viewer_url", "")
		self.assertIsNone(viewer_url(self.exam()))
		self.assertEqual(
			viewer_url(self.exam(ke_pacs_link="https://pacs.example/study/1")), "https://pacs.example/study/1"
		)
		self.assertIsNone(viewer_url(self.exam(ke_pacs_link="javascript:alert(1)")))
