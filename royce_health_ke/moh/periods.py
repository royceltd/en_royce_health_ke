# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Quarterly and annual MOH reports: the sum of the monthly reports in the
period, so a quarter always agrees with the three monthly forms the facility
already submitted (MOH counting rules, e.g. "new cases once a month", apply
month by month exactly as on the monthly form). Every MOH 705/706/711/717
value is a count, so summing is correct; none is a rate or an average."""

MONTH, QUARTER, YEAR = "Month", "Quarter", "Year"
PERIODS = (MONTH, QUARTER, YEAR)


def months_in(filters):
	"""[(year, month)] covered by the report filters (period defaults to Month)."""
	year = int(filters["year"])
	period = filters.get("period") or MONTH
	if period == YEAR:
		return [(year, m) for m in range(1, 13)]
	if period == QUARTER:
		first = (int(filters.get("quarter") or 1) - 1) * 3 + 1
		return [(year, m) for m in range(first, first + 3)]
	return [(year, int(filters["month"]))]


def combine(monthly_rows, key=("indicator",)):
	"""Add up monthly row lists. Rows match on `key`; numbers are summed, a
	value that is None every month stays None (e.g. "not captured yet"), and
	text keeps the first month's. Rows appearing only in some months (e.g.
	"sex not recorded") are kept, in order of first appearance."""
	out, order = {}, []
	for rows in monthly_rows:
		section = None
		for row in rows:
			if row.get("is_section"):
				section = row.get("indicator")
			# The same indicator can appear under two sections (e.g. per ward).
			k = (section, *(row.get(f) for f in key))
			if k not in out:
				out[k] = dict(row)
				order.append(k)
				continue
			total = out[k]
			for field, value in row.items():
				if field in key or isinstance(value, bool):
					continue
				if isinstance(value, int | float):
					current = total.get(field)
					total[field] = (current if isinstance(current, int | float) else 0) + value
				elif total.get(field) in (None, "") and value not in (None, ""):
					total[field] = value
	return [out[k] for k in order]


def label(filters):
	period = filters.get("period") or MONTH
	if period == QUARTER:
		return f"Q{int(filters.get('quarter') or 1)} {filters['year']}"
	if period == YEAR:
		return str(filters["year"])
	return None
