# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Desk sidebar fix for modules that ship several sidebars - Marley does.

Frappe v16 gives every sidebar of a module all of the module's workspaces
(`workspaces=context.workspaces.get(base.module)` in frappe's sidebar.py), and
the desk finds a workspace's sidebar with the first match
(`module_for_workspace` in sidebar.js). Marley's 8 sidebars are all in module
Healthcare, so every Healthcare workspace resolved to "Diagnostics", the first
alphabetically: clicking Healthcare (or Outpatient, Inpatient...) on the rail
showed the Diagnostics sidebar, and only a second click - same route, so no
re-resolve - showed the right one. FOUND 2026-11-07, still in frappe 16.55.2.

Fix, on the boot payload: among sidebars sharing a module, a workspace stays
only on the sidebars that link it. A workspace none of them links keeps its
module-wide claim, as before."""

from collections import defaultdict


def _linked_workspaces(sidebar):
	return {
		item.get("link_to")
		for item in sidebar.get("items") or []
		if item.get("type") == "Link" and item.get("link_type") == "Workspace" and item.get("link_to")
	}


def narrow_shared_module_workspaces(module_sidebars):
	by_module = defaultdict(list)
	for shell, sidebar in (module_sidebars or {}).items():
		if sidebar and sidebar.get("module"):
			by_module[sidebar["module"]].append(shell)

	for shells in by_module.values():
		if len(shells) < 2:
			continue
		linked = {shell: _linked_workspaces(module_sidebars[shell]) for shell in shells}
		claimed = set().union(*linked.values())
		for shell in shells:
			sidebar = module_sidebars[shell]
			sidebar["workspaces"] = [
				ws for ws in sidebar.get("workspaces") or [] if ws in linked[shell] or ws not in claimed
			]
	return module_sidebars


def extend_bootinfo(bootinfo):
	narrow_shared_module_workspaces(bootinfo.get("module_sidebars"))
