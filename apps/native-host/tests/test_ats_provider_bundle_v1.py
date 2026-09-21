from __future__ import annotations

import pytest

from munshi_apply_native.application_plan_handoff_v2 import (
    KNOWN_PROVIDER_RECIPES as HANDOFF_RECIPES,
)
from munshi_apply_native.career_os_handoff import SUPPORTED_PROVIDERS
from munshi_apply_native.plan_browser_adapter import (
    KNOWN_PROVIDER_RECIPES,
    provider_for_url,
)

CASES = [
    ("RIPPLING", "rippling.com"),
    ("ICIMS", "icims.com"),
    ("BRASSRING", "brassring.com"),
    ("JAZZHR", "applytojob.com"),
    ("JOBVITE", "jobvite.com"),
    ("BREEZYHR", "breezy.hr"),
    ("ORACLE_RECRUITING", "oraclecloud.com"),
    ("PAYLOCITY", "paylocity.com"),
    ("UKG_ULTIPRO", "ultipro.com"),
    ("UKG_ULTIPRO", "ukg.net"),
    ("ZOHO_RECRUIT", "zohorecruit.com"),
    ("ADP", "adp.com"),
    ("DOVER", "dover.com"),
    ("GEM", "gem.com"),
    ("SAP_SUCCESSFACTORS", "successfactors.com"),
    ("TEAMTAILOR", "teamtailor.com"),
    ("PHENOM", "phenompeople.com"),
    ("DAYFORCE", "dayforcehcm.com"),
    ("CAREERPLUG", "careerplug.com"),
    ("HIREOLOGY", "hireology.com"),
]


@pytest.mark.parametrize(("family", "domain"), CASES)
def test_extended_ats_domains_resolve_to_shared_provider_recipe(
    family: str, domain: str
) -> None:
    assert provider_for_url(f"https://{domain}/jobs/123") == family
    assert provider_for_url(f"https://jobs.{domain}/apply/123") == family


def test_provider_registries_remain_aligned() -> None:
    expected = set(KNOWN_PROVIDER_RECIPES)
    assert set(HANDOFF_RECIPES) == expected
    assert {name.upper() for name in SUPPORTED_PROVIDERS} == expected


def test_suffix_matching_rejects_lookalikes() -> None:
    assert provider_for_url("https://notindeed.com/jobs/1") == "GENERIC"
    assert provider_for_url("https://evilgreenhouse.io.example/jobs/1") == "GENERIC"
