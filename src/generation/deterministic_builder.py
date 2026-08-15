"""
src/generation/deterministic_builder.py

Builds the 4 deterministic sections without calling the LLM:
1. Reporting Period
2. Serious Cases / 15-Day Alerts
3. History of Actions
4. Case Index / Listing
"""

import json

def build_reporting_period(metadata: dict) -> str:
    start = metadata.get("reporting_period_start", "Unknown")
    end = metadata.get("reporting_period_end", "Unknown")
    source_file = metadata.get("source_file", "Unknown")
    
    return (
        f"This Periodic Adverse Drug Experience Report (PADER) covers the reporting period "
        f"from **{start}** to **{end}**.\n\n"
        f"The data was sourced from `{source_file}`."
    )

def build_alerts(alerts: dict, case_summary: dict) -> str:
    total_cases = alerts.get("total_cases", 0)
    expedited_cases = alerts.get("expedited_cases", 0)
    
    if total_cases == 0:
        return "No cases were reported during this period."
        
    percent = (expedited_cases / total_cases) * 100 if total_cases > 0 else 0
    
    text = (
        f"During the reporting period, **{expedited_cases}** cases meeting the supplied "
        f"expedited criteria (15-day alerts) were received, representing {percent:.1f}% "
        f"of the total {total_cases} cases.\n\n"
        "### Seriousness Criteria Breakdown\n"
    )
    
    criteria = alerts.get("seriousness_criteria_breakdown", [])
    if criteria:
        text += "| Criterion | Cases |\n|---|---|\n"
        for c in criteria:
            text += f"| {c['criterion_label']} | {c['cases_meeting_criterion']} |\n"
    else:
        text += "No specific seriousness criteria breakdown was available.\n"
        
    text += "\n*Note: Criteria are not mutually exclusive; the same case may meet multiple criteria.*"
    return text

def build_history_of_actions(capabilities: dict) -> str:
    history = capabilities.get("history_of_actions", {})
    available = history.get("available", False)
    
    if not available:
        reason = history.get("reason", "No history-of-actions data supplied.")
        return reason
        
    return "History of actions information is available but no specific actions were noted."

def build_case_listing(case_listing: list[dict]) -> str:
    """
    Returns only the intro paragraph. The actual table is appended
    by the MarkdownWriter to avoid massive strings in memory.
    """
    total = len(case_listing)
    return (
        f"The following table provides a listing of all **{total}** unique cases "
        "received during the reporting period. Cases are ordered by reporting date."
    )
