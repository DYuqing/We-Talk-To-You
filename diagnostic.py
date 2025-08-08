"""
diagnostic.py
==============

Simple eligibility suggestion tool for Work and Income benefits.  The
diagnostic functions here encapsulate the rule‑based logic originally
present in the command‑line tool.  They can be reused both from a CLI
context and within a web application.

The logic provided below is intentionally simplistic and should be
expanded upon using up‑to‑date policy information from Work and Income.
Nevertheless it serves as a useful starting point for directing users
towards potential benefits they may wish to investigate further.
"""

from __future__ import annotations

from typing import Dict, List


def diagnose(
    age: int,
    has_partner: bool,
    has_dependents: bool,
    weekly_income: float,
    employment_status: str,
    housing_status: str,
    has_id: bool,
    has_bank_account: bool,
) -> Dict[str, List[str]]:
    """Return a dictionary of suggested benefits and general next steps.

    Args:
        age: Age in years.
        has_partner: Whether the user has a partner or spouse.
        has_dependents: Whether the user cares for dependent children or
            disabled family members.
        weekly_income: Approximate weekly income in NZD.
        employment_status: One of "employed", "unemployed", "student",
            "retired" or any other descriptor.
        housing_status: One of "own", "rent", "social‑housing",
            "homeless" or another descriptor.
        has_id: Whether valid NZ identification is available.
        has_bank_account: Whether a bank account exists.

    Returns:
        A dictionary with two keys: ``suggestions``, a list of benefit
        names or descriptions the user should look into, and ``next_steps``, a
        list of general recommendations.
    """
    suggestions: List[str] = []
    # Jobseeker Support
    if age >= 16 and employment_status in {"unemployed", "student"}:
        suggestions.append("Jobseeker Support")
    # Sole Parent Support or Childcare Subsidy
    if has_dependents and weekly_income < 1500:
        suggestions.append("Sole Parent Support or Childcare Subsidy")
    # Accommodation Supplement
    if weekly_income <= 600:
        suggestions.append("Accommodation Supplement")
    # Superannuation
    if age >= 65:
        suggestions.append("New Zealand Superannuation or Veteran's Pension")
    # Couples assistance
    if has_partner and weekly_income < 800:
        suggestions.append("Couples assistance such as Supported Living Payment")
    if not suggestions:
        suggestions.append(
            "We could not determine a specific benefit based on the information provided."
        )
    next_steps = [
        "Check the eligibility criteria for each suggested benefit on the Work and Income website.",
        "Gather necessary documents such as identification, proof of address, bank account details, and income evidence.",
        "Apply online via MyMSD or by contacting Work and Income directly.",
        "Keep copies of any letters or emails you receive from Work and Income, including sanction letters.",
        "If you receive a sanction letter, use the document upload tool to extract text and seek help if needed.",
    ]
    return {"suggestions": suggestions, "next_steps": next_steps}


def run_cli_survey() -> None:
    """Run an interactive survey on the command line.

    This convenience function collects answers from the user in a CLI
    setting, invokes :func:`diagnose` and prints the results.  It can be
    called from a standalone script.
    """
    print("Welcome to the Work and Income diagnostic tool.")
    print(
        "Please answer the following questions to help us identify benefits you may be eligible for."
    )
    try:
        age = int(input("1. What is your age? ").strip())
    except ValueError:
        print("Invalid age entered. Please enter a number.")
        return
    partner_inp = input(
        "2. Do you have a partner or spouse? (yes/no) "
    ).strip().lower()
    has_partner = partner_inp in {"yes", "y"}
    deps_inp = input(
        "3. Do you care for any dependent children or disabled family members? (yes/no) "
    ).strip().lower()
    has_dependents = deps_inp in {"yes", "y"}
    income_str = input(
        "4. What is your approximate weekly income in NZD? (enter a number) "
    ).strip()
    try:
        weekly_income = float(income_str)
    except ValueError:
        print("Invalid income entered. Please enter a number.")
        return
    employment_status = input(
        "5. What is your employment status? (employed/unemployed/student/retired) "
    ).strip().lower()
    housing_status = input(
        "6. Describe your housing situation (own/rent/social‑housing/homeless) "
    ).strip().lower()
    id_inp = input(
        "7. Do you have valid NZ identification (passport/driver's licence) available? (yes/no) "
    ).strip().lower()
    has_id = id_inp in {"yes", "y"}
    bank_inp = input(
        "8. Do you have a bank account? (yes/no) "
    ).strip().lower()
    has_bank = bank_inp in {"yes", "y"}
    result = diagnose(
        age,
        has_partner,
        has_dependents,
        weekly_income,
        employment_status,
        housing_status,
        has_id,
        has_bank,
    )
    print("\nBased on your answers, you might want to look into the following benefits and services:")
    for item in result["suggestions"]:
        print(f" - {item}")
    print("\nGeneral next steps:")
    for step in result["next_steps"]:
        print(f" - {step}")