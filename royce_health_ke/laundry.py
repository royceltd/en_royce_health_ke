# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Laundry: linen as stock items moving between the linen store, each ward's
linen store and the laundry, so ERPNext's stock balances say where every
sheet is.

| Movement                  | From                     | To          |
|---------------------------|--------------------------|-------------|
| Issue to ward             | Linen store              | Ward        |
| Collect soiled from ward  | Ward                     | Laundry     |
| Return clean to store     | Laundry                  | Linen store |
| Condemn                   | Laundry (or linen store) | written off |
| Report lost               | Ward                     | written off |

Each submitted Linen Movement posts a Stock Entry (Material Transfer, or
Material Issue for a write-off); cancelling the movement cancels it. The
warehouses are in Kenya Health Settings and on each ward (Ward Linen Store)."""

import frappe
from frappe import _
from frappe.utils import get_first_day, getdate

ISSUE = "Issue to ward"
COLLECT = "Collect soiled from ward"
RETURN = "Return clean to store"
CONDEMN = "Condemn"
LOST = "Report lost"
WRITE_OFFS = (CONDEMN, LOST)


def settings():
	s = frappe.get_cached_doc("Kenya Health Settings")
	return frappe._dict(
		linen_store=s.get("linen_store"),
		laundry=s.get("laundry_warehouse"),
		item_group=s.get("linen_item_group") or "Linen",
	)


def ward_store(ward):
	store = frappe.db.get_value("Healthcare Service Unit", ward, "ke_linen_warehouse")
	if not store:
		frappe.throw(_("Set the Ward Linen Store on {0}.").format(ward))
	return store


def _need(value, label):
	if not value:
		frappe.throw(_("Set the {0} in Kenya Health Settings.").format(_(label)))
	return value


def route(doc):
	"""(from warehouse, to warehouse); to is None for a write-off."""
	s = settings()
	if doc.movement_type == ISSUE:
		return _need(s.linen_store, "Linen Store"), ward_store(doc.ward)
	if doc.movement_type == COLLECT:
		return ward_store(doc.ward), _need(s.laundry, "Laundry")
	if doc.movement_type == RETURN:
		return _need(s.laundry, "Laundry"), _need(s.linen_store, "Linen Store")
	if doc.movement_type == CONDEMN:
		if doc.condemn_from == "Linen store":
			return _need(s.linen_store, "Linen Store"), None
		return _need(s.laundry, "Laundry"), None
	if doc.movement_type == LOST:
		return ward_store(doc.ward), None
	frappe.throw(_("Unknown movement {0}.").format(doc.movement_type))


def validate_movement(doc):
	if doc.movement_type not in (ISSUE, COLLECT, LOST):
		doc.ward = None
	doc.from_warehouse, doc.to_warehouse = route(doc)
	group = settings().item_group
	groups = set()
	if frappe.db.exists("Item Group", group):
		lft, rgt = frappe.db.get_value("Item Group", group, ["lft", "rgt"])
		groups = set(
			frappe.get_all("Item Group", filters={"lft": [">=", lft], "rgt": ["<=", rgt]}, pluck="name")
		)
	for row in doc.items:
		if row.qty <= 0:
			frappe.throw(_("Row {0}: the quantity must be more than zero.").format(row.idx))
		item_group, is_stock = frappe.db.get_value("Item", row.item_code, ["item_group", "is_stock_item"])
		if not is_stock or item_group not in groups:
			frappe.throw(
				_("Row {0}: {1} isn't a linen stock item (item group {2}).").format(
					row.idx, row.item_code, group
				)
			)


def on_submit_movement(doc):
	entry = frappe.new_doc("Stock Entry")
	entry.company = doc.company
	entry.posting_date = doc.posting_date
	entry.set_posting_time = 1
	entry.stock_entry_type = "Material Issue" if doc.movement_type in WRITE_OFFS else "Material Transfer"
	entry.remarks = _("{0} {1}").format(doc.movement_type, doc.name) + (
		f": {doc.remarks}" if doc.remarks else ""
	)
	for row in doc.items:
		entry.append(
			"items",
			{
				"item_code": row.item_code,
				"qty": row.qty,
				"s_warehouse": doc.from_warehouse,
				"t_warehouse": doc.to_warehouse,
			},
		)
	entry.flags.ignore_permissions = True
	entry.insert()
	entry.submit()
	doc.db_set("stock_entry", entry.name)


def on_cancel_movement(doc):
	if doc.stock_entry and frappe.db.get_value("Stock Entry", doc.stock_entry, "docstatus") == 1:
		entry = frappe.get_doc("Stock Entry", doc.stock_entry)
		entry.flags.ignore_permissions = True
		entry.cancel()


def linen_status(company, on=None):
	"""Per linen item: quantity in the linen store, the laundry and each ward,
	and what was condemned or lost this month."""
	s = settings()
	locations = []
	if s.linen_store:
		locations.append((_("Linen Store"), s.linen_store))
	if s.laundry:
		locations.append((_("Laundry"), s.laundry))
	for ward, store in frappe.get_all(
		"Healthcare Service Unit",
		filters={"company": company, "ke_linen_warehouse": ["is", "set"]},
		fields=["name", "ke_linen_warehouse"],
		as_list=True,
		order_by="name asc",
	):
		locations.append((ward, store))
	stores = [store for _label, store in locations]
	items = frappe.get_all(
		"Item",
		filters={"item_group": s.item_group, "is_stock_item": 1, "disabled": 0},
		fields=["name", "item_name"],
		order_by="item_name asc",
	)
	qty = {}
	for item_code, warehouse, actual in frappe.db.sql(
		"select item_code, warehouse, actual_qty from tabBin where warehouse in %(w)s and item_code in %(i)s",
		{"w": stores or [""], "i": [i.name for i in items] or [""]},
	):
		qty[(item_code, warehouse)] = actual
	month_start = get_first_day(getdate(on))
	written_off = {}
	for row in frappe.db.sql(
		"""select m.movement_type, i.item_code, sum(i.qty)
		from `tabLinen Movement` m join `tabLinen Movement Item` i on i.parent = m.name
		where m.docstatus = 1 and m.company = %s and m.movement_type in %s and m.posting_date >= %s
		group by m.movement_type, i.item_code""",
		(company, WRITE_OFFS, month_start),
	):
		written_off[(row[0], row[1])] = row[2]
	return locations, items, qty, written_off
