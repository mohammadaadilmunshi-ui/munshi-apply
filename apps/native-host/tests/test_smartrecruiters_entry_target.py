from munshi_apply_native.plan_browser_adapter import smartrecruiters_verified_oneclick



BASE = "https://jobs.smartrecruiters.com/DohlerGmbH/744000154149608-human-resources-coordinator"
GOOD = (
    "https://jobs.smartrecruiters.com/oneclick-ui/company/DohlerGmbH/"
    "publication/925695ab-68a9-4300-8c29-e68da157aefc?dcr_ci=DohlerGmbH"
)


def test_same_company_duplicate_links_collapse_without_guessing():
    links = [{"label": "I'm interested", "href": GOOD}] * 3
    links.append({
        "label": "I'm interested",
        "href": GOOD.replace("jobs.smartrecruiters.com", "www.smartr.me"),
    })
    assert smartrecruiters_verified_oneclick(BASE, links) == GOOD


def test_cross_company_or_wrong_origin_never_advanced():
    assert not smartrecruiters_verified_oneclick(
        BASE, [{"label": "I'm interested", "href": GOOD.replace("DohlerGmbH", "OtherEmployer")}]
    )
    assert not smartrecruiters_verified_oneclick(
        BASE, [{"label": "I'm interested", "href": "https://evil.example/oneclick-ui/anything"}]
    )


def test_distinct_publication_targets_fail_closed():
    other = GOOD.replace("925695ab", "125695ab")
    assert not smartrecruiters_verified_oneclick(
        BASE, [{"label": "I'm interested", "href": GOOD},
               {"label": "I'm interested", "href": other}]
    )


def test_exact_entry_label_required():
    assert not smartrecruiters_verified_oneclick(BASE, [{"label": "Submit", "href": GOOD}])
