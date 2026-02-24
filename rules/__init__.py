# rules/__init__.py

"""
Rules engines for all disciplines.

Exports:
- run_all_rules          : run all discipline rules on BOQ/SOQ.
- group_results_by_level : group RuleResult objects by ERROR/WARNING/INFO.
- group_results_by_discipline : group RuleResult objects by discipline.
"""

from .rules_runner import (
    run_all_rules,
    group_results_by_discipline,
    group_results_by_level,
)

__all__ = [
    "run_all_rules",
    "group_results_by_discipline",
    "group_results_by_level",
]
