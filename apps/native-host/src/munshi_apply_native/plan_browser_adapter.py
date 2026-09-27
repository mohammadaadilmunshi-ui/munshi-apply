"""Plan adapter over the existing extension scanner/classifier/fill implementation.

The caller supplies an already selected Playwright page, scoped artifact reader,
and Hunter freshness validator. No credentials, browser launch or navigation to
an employer happens at module import or plan acceptance.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .execution_policy import prepare_permissions, safe_evidence
from .hunter_plan_semantic_bridge import (
    answer_matches_question,
    logical_field_fingerprint,
    protected_answer_matches_question,
)
from .review_reconciliation_v1 import reconcile_provider_review
from .universal_document_uploader import DocumentSpec, UniversalDocumentUploader

RESUME_UPLOAD_ENV = "MUNSHI_APPLY_RESUME_UPLOAD_ENABLED"
NORMAL_AUTOFILL_ENV = "MUNSHI_APPLY_NORMAL_ANSWER_AUTOFILL_ENABLED"
SUBMIT_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH"})


def _enabled(name: str) -> bool:
    return str(os.getenv(name) or "").strip().casefold() in {"1", "true", "yes", "on"}


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


KNOWN_PROVIDER_RECIPES = {
    "GREENHOUSE": ("greenhouse.io",),
    "WORKDAY": ("myworkdayjobs.com", "myworkdaysite.com"),
    "NAUKRI": ("naukri.com",),
    "INDEED": ("indeed.com",),
    "LEVER": ("lever.co",),
    "ASHBY": ("ashbyhq.com",),
    "RIPPLING": ("rippling.com",),
    "ICIMS": ("icims.com",),
    "BRASSRING": ("brassring.com",),
    "BAMBOOHR": ("bamboohr.com",),
    "WORKABLE": ("workable.com",),
    "JAZZHR": ("jazzhr.com", "jazz.co", "applytojob.com"),
    "JOBVITE": ("jobvite.com",),
    "BREEZYHR": ("breezy.hr",),
    "ORACLE_RECRUITING": ("oraclecloud.com",),
    "TALEO": ("taleo.net",),
    "PAYLOCITY": ("paylocity.com",),
    "SMARTRECRUITERS": ("smartrecruiters.com",),
    "UKG_ULTIPRO": ("ultipro.com", "ukg.com", "ukg.net"),
    "ZOHO_RECRUIT": ("zohorecruit.com",),
    "ADP": ("adp.com",),
    "DOVER": ("dover.com",),
    "GEM": ("gem.com",),
    "SAP_SUCCESSFACTORS": ("successfactors.com",),
    "RECRUITEE": ("recruitee.com",),
    "PINPOINT": ("pinpointhq.com",),
    "TEAMTAILOR": ("teamtailor.com",),
    "POLYMER": ("polymer.co",),
    "PHENOM": ("phenom.com", "phenompeople.com"),
    "DAYFORCE": ("dayforcehcm.com", "dayforce.com"),
    "JOIN": ("join.com",),
    "CAREERPLUG": ("careerplug.com",),
    "HIREOLOGY": ("hireology.com",),
    "AGILE_ATS": ("agile-ats.com",),
}


def provider_for_url(url: str) -> str:
    """Return an optimization recipe hint, never an execution eligibility verdict."""
    host = (urlsplit(url).hostname or "").casefold().rstrip(".")
    for provider, domains in KNOWN_PROVIDER_RECIPES.items():
        if any(host == domain or host.endswith("." + domain) for domain in domains):
            return provider
    return "GENERIC"


class PlanBrowserAdapter:
    def __init__(
        self,
        page: Any,
        *,
        artifact_reader: Callable[[dict[str, Any]], bytes],
        current_plan: Callable[[dict[str, Any]], bool],
        runtime_path: Path,
        cover_letter_reader: Callable[[dict[str, Any]], bytes] | None = None,
        protected_value_resolver: Callable[
            [dict[str, Any], dict[str, Any]], dict[str, Any]
        ]
        | None = None,
        legal_attestation_authorizer: Callable[
            [dict[str, Any], dict[str, Any]], dict[str, Any]
        ]
        | None = None,
    ) -> None:
        self.page = page
        self.artifact_reader = artifact_reader
        self.cover_letter_reader = cover_letter_reader
        self.protected_value_resolver = protected_value_resolver
        self.legal_attestation_authorizer = legal_attestation_authorizer
        self.current_plan = current_plan
        self.runtime_path = runtime_path
        self.on_event: Callable[[str, dict[str, Any]], None] = lambda _kind, _evidence: None
        # Exact browser-verified upload evidence survives SPA element replacement
        # within this adapter/session.  It is always plan-bound and never sourced
        # from provider text, filenames, or optimistic DOM state.
        self._verified_uploads: dict[tuple[str, str], str] = {}

    def _scan(self) -> dict[str, Any]:
        if not self.page.evaluate("typeof MunshiPlanRuntime !== 'undefined'"):
            self.page.add_script_tag(content=self.runtime_path.read_text(encoding="utf-8"))
        return self.page.evaluate("MunshiPlanRuntime.describeForm()")

    def _dismiss_cookie_consent(self) -> bool:
        """Dismiss only bounded, recognizably cookie-specific consent overlays.

        This intentionally refuses generic form-consent buttons. A candidate is
        clicked only when its label is an allow/accept-cookie action and the
        surrounding component is clearly a cookie/CMP surface.
        """
        try:
            result = self.page.evaluate(
                r"""() => {
                  const visible = element => {
                    if (!(element instanceof HTMLElement)) return false;
                    const style = getComputedStyle(element);
                    const rect = element.getBoundingClientRect();
                    return style.display !== 'none'
                      && style.visibility !== 'hidden'
                      && Number(style.opacity || 1) !== 0
                      && rect.width > 0 && rect.height > 0;
                  };
                  const labelOf = element => (
                    element.innerText
                    || element.value
                    || element.getAttribute('aria-label')
                    || element.getAttribute('title')
                    || ''
                  ).replace(/\s+/g, ' ').trim().toLowerCase();
                  const accepted = new Set([
                    'accept all',
                    'accept all cookies',
                    'accept cookies',
                    'allow all',
                    'allow all cookies',
                    'i agree',
                    'agree to all',
                    'agree & continue',
                    'agree and continue',
                    'accept & continue',
                    'accept and continue',
                    'got it',
                  ]);
                  const candidates = Array.from(document.querySelectorAll(
                    'button,[role="button"],input[type="button"],input[type="submit"]'
                  )).slice(0, 250);
                  for (const element of candidates) {
                    if (!visible(element)) continue;
                    const label = labelOf(element);
                    if (!accepted.has(label)) continue;
                    const container = element.closest(
                      '[role="dialog"],[aria-modal="true"],'
                      + '#onetrust-banner-sdk,#CybotCookiebotDialog,'
                      + '[id*="cookie" i],[class*="cookie" i],'
                      + '[id*="onetrust" i],[class*="onetrust" i],'
                      + '[id*="cookiebot" i],[class*="cookiebot" i],'
                      + '[id*="trustarc" i],[class*="trustarc" i],'
                      + '[id*="didomi" i],[class*="didomi" i],'
                      + '[id*="quantcast" i],[class*="quantcast" i],'
                      + '[id*="consentmanager" i],[class*="consentmanager" i]'
                    );
                    const context = String(
                      (container && container.innerText)
                      || (element.parentElement && element.parentElement.innerText)
                      || ''
                    ).toLowerCase();
                    const identity = String(
                      element.id + ' ' + element.className + ' '
                      + (container ? container.id + ' ' + container.className : '')
                    ).toLowerCase();
                    const cookieContext = (
                      /\bcookies?\b|tracking technologies|cookie settings/
                    ).test(context);
                    const knownCmp = (
                      /(onetrust|cookiebot|cookie|trustarc|didomi|quantcast|consentmanager)/
                    ).test(identity);
                    if (!cookieContext && !knownCmp) continue;
                    element.click();
                    return { dismissed: true, label };
                  }
                  return { dismissed: false };
                }"""
            )
        except Exception:
            return False
        if not isinstance(result, dict) or result.get("dismissed") is not True:
            return False
        self.on_event(
            "COOKIE_CONSENT_DISMISSED",
            {"strategy": "bounded_cookie_accept", "label": str(result.get("label") or "")[:80]},
        )
        with suppress(Exception):
            self.page.wait_for_timeout(100)
        return True

    def inspect_job(self, *, plan: dict[str, Any]) -> dict[str, Any]:
        expected = urlsplit(plan["job"]["apply_url"] or plan["job"]["job_url"])
        actual = urlsplit(self.page.url)
        # Keep the exact posting binding while allowing an ATS to move into a
        # descendant application route for that same posting.  Workday, for
        # example, appends /apply and additional application steps beneath the
        # exact job path.  A sibling job or a generic account route remains
        # outside this binding and fails closed.
        exact = (actual.scheme, actual.netloc, actual.path, actual.query) == (
            expected.scheme,
            expected.netloc,
            expected.path,
            expected.query,
        )
        expected_path = expected.path.rstrip("/")
        application_path = expected_path + "/apply"
        application_child = (
            actual.scheme == expected.scheme
            and actual.netloc == expected.netloc
            and bool(expected_path)
            and (
                actual.path == application_path
                or actual.path.startswith(application_path + "/")
            )
        )
        same = exact or application_child
        scan = self._scan()["page"]
        provider_policy = dict(plan.get("provider_policy") or {})
        declared_provider = str(provider_policy.get("provider") or "GENERIC").upper()
        return {
            "provider": declared_provider,
            "provider_recipe": provider_for_url(self.page.url),
            "job_id": str(plan["job"]["id"]) if same else "",
            "current_url": self.page.url,
            "page_id": scan["pageId"],
            "page_fingerprint": scan["pageFingerprint"],
            "security_checkpoint": scan["securityCheckpoint"],
        }

    def _element(self, control_id: str) -> Any:
        handle = self.page.evaluate_handle("id => MunshiPlanRuntime.element(id)", control_id)
        element = handle.as_element()
        if element is None:
            raise ValueError("Observed control disappeared")
        return element

    @staticmethod
    def _field_committed(field: dict[str, Any]) -> bool:
        return bool(field.get("satisfied")) and field.get("invalid") is not True

    def _control_committed(self, control_id: str) -> bool:
        described = self._scan()
        return any(
            isinstance(field, dict)
            and str(field.get("control_id") or "") == control_id
            and self._field_committed(field)
            for field in described.get("fields", [])
        )

    @staticmethod
    def _workday_option_text(value: Any) -> str:
        return " ".join(str(value or "").split()).casefold()

    def _workday_prompt_selected_value(self, element: Any, answer: str) -> str:
        """Return an exact provider-backed selected prompt value, never typed query text."""
        wanted = self._workday_option_text(answer)
        if not wanted:
            return ""
        try:
            result = element.evaluate(
                r"""(element, answer) => {
                  const compact = value => String(value || '').replace(/\s+/g, ' ').trim();
                  const wanted = compact(answer).toLowerCase();
                  const direct = compact(
                    element.getAttribute('data-value')
                    || element.getAttribute('aria-valuetext')
                    || ''
                  );
                  if (direct && direct.toLowerCase() === wanted) return direct;

                  const optionValue = item => {
                    const option = item.matches?.(
                      '[data-automation-id="promptOption"],'
                      + '[role="option"],[role="menuitem"]'
                    )
                      ? item
                      : item.querySelector?.(
                          '[data-automation-id="promptOption"],'
                          + '[role="option"],[role="menuitem"]'
                        );
                    const candidate = option || item;
                    return compact(
                      candidate.getAttribute?.('data-automation-label')
                      || candidate.getAttribute?.('aria-label')
                      || candidate.getAttribute?.('title')
                      || candidate.getAttribute?.('data-value')
                      || candidate.getAttribute?.('data-option-value')
                      || candidate.textContent
                      || ''
                    );
                  };

                  let scope = element.parentElement;
                  for (
                    let depth = 0;
                    scope && depth < 10;
                    depth += 1, scope = scope.parentElement
                  ) {
                    const selected = Array.from(
                      scope.querySelectorAll(
                        '[data-automation-id^="selectedItem"],'
                        + '[role="option"][aria-selected="true"],'
                        + '[data-automation-id="promptOption"][aria-selected="true"]'
                      )
                    );
                    if (!selected.length) continue;
                    const matches = [...new Set(
                      selected.map(optionValue).filter(Boolean)
                    )].filter(value => value.toLowerCase() === wanted);
                    if (matches.length === 1) return matches[0];
                    if (matches.length > 1) return '';
                  }
                  return '';
                }""",
                str(answer),
            )
        except Exception:
            return ""
        return str(result or "").strip()

    def _workday_source_selected_value(self, element: Any, answer: str) -> str:
        """Compatibility wrapper for older production tests."""
        return self._workday_prompt_selected_value(element, answer)

    def _workday_prompt_committed(self, element: Any, answer: str) -> bool:
        selected = self._workday_prompt_selected_value(element, answer)
        return self._workday_option_text(selected) == self._workday_option_text(answer)

    def _workday_source_committed(self, element: Any, answer: str) -> bool:
        """Compatibility wrapper for older production tests."""
        return self._workday_prompt_committed(element, answer)

    @staticmethod
    def _workday_locator_id(value: str) -> str:
        return str(value or "").replace("\\", "\\\\").replace('"', '\\"')

    def _workday_click_exact_option(
        self,
        answer: str,
        *,
        trigger: Any | None = None,
        timeout_ms: int = 4500,
        poll_ms: int = 75,
        press_enter: bool = False,
    ) -> bool:
        """Activate exactly one visible Workday option from the provider popup.

        Keyboard guessing is intentionally excluded. The press_enter argument is
        retained only for call-site compatibility and is ignored.
        """
        del press_enter
        wanted = self._workday_option_text(answer)
        if not wanted:
            return False
        timeout_ms = max(250, min(int(timeout_ms), 7000))
        poll_ms = max(25, min(int(poll_ms), 250))

        controlled_ids: list[str] = []
        if trigger is not None:
            try:
                raw_ids = trigger.evaluate(
                    r"""element => [
                      element.getAttribute('aria-controls') || '',
                      element.getAttribute('aria-owns') || ''
                    ].join(' ')"""
                )
                controlled_ids = [
                    item for item in str(raw_ids or "").split() if item
                ]
            except Exception:
                controlled_ids = []

        selector = (
            "[data-automation-id='promptOption'],"
            "[data-automation-id*='promptOption'],"
            "[data-automation-id='dropdownOption'],"
            "[role='option'],[role='menuitem'],"
            "[data-value],[data-option-value]"
        )

        def candidate_metadata(candidate: Any) -> tuple[bool, list[Any], str]:
            try:
                raw = candidate.evaluate(
                    r"""element => ({
                      selectedContainer: Boolean(
                        element.closest('[data-automation-id^="selectedItem"]')
                      ),
                      values: [
                        element.innerText || '',
                        element.textContent || '',
                        element.getAttribute('aria-label') || '',
                        element.getAttribute('title') || '',
                        element.getAttribute('data-value') || '',
                        element.getAttribute('data-option-value') || '',
                        element.getAttribute('data-automation-label') || ''
                      ],
                      id: element.id || ''
                    })"""
                )
            except Exception:
                return False, [], ""
            if isinstance(raw, dict):
                return (
                    bool(raw.get("selectedContainer")),
                    list(raw.get("values") or []),
                    str(raw.get("id") or ""),
                )
            return False, [raw], ""

        def collect(locator: Any, limit: int) -> list[Any]:
            matches: list[Any] = []
            seen: set[str] = set()
            try:
                count = min(locator.count(), limit)
            except Exception:
                return []
            for index in range(count):
                candidate = locator.nth(index)
                with suppress(Exception):
                    if not candidate.is_visible():
                        continue
                    selected_container, values, token_id = candidate_metadata(candidate)
                    if selected_container:
                        continue
                    exact = any(
                        self._workday_option_text(raw) == wanted
                        or any(
                            self._workday_option_text(line) == wanted
                            for line in str(raw or "").splitlines()
                        )
                        for raw in values
                    )
                    if not exact:
                        continue
                    token = token_id or f"candidate:{index}"
                    if token in seen:
                        continue
                    seen.add(token)
                    matches.append(candidate)
            return matches

        def candidates() -> list[Any]:
            scoped: list[Any] = []
            for popup_id in controlled_ids:
                escaped = self._workday_locator_id(popup_id)
                with suppress(Exception):
                    popup = self.page.locator(f'[id="{escaped}"]')
                    if popup.count() != 1 or not popup.first.is_visible():
                        continue
                    scoped.extend(collect(popup.first.locator(selector), 250))
            if controlled_ids:
                return scoped
            return collect(self.page.locator(selector), 300)

        def activate(candidate: Any) -> bool:
            target = candidate
            try:
                nearest = candidate.locator(
                    "xpath=ancestor-or-self::*[@role='option'][1]"
                )
                if nearest.count() == 1:
                    target = nearest
            except Exception:
                target = candidate
            try:
                radio = target.locator(
                    "input[type='radio'],[data-automation-id='radioBtn']"
                )
                if radio.count() == 1:
                    radio.first.click()
                else:
                    target.click()
                return True
            except Exception:
                try:
                    candidate.click()
                    return True
                except Exception:
                    return False

        deadline = time.monotonic() + (timeout_ms / 1000.0)
        while time.monotonic() <= deadline:
            matches = candidates()
            if len(matches) == 1:
                return activate(matches[0])
            if len(matches) > 1:
                return False
            self.page.wait_for_timeout(poll_ms)
        return False

    def _workday_public_prompt_fallback(self, element: Any, answer: str) -> bool:
        """One deterministic slow retype; no blind key or nudge behavior."""
        try:
            element.click()
            element.press("Control+A")
            element.press("Backspace")
            element.type(str(answer), delay=90)
            self.page.wait_for_timeout(250)
        except Exception:
            return False
        if not self._workday_click_exact_option(
            str(answer), trigger=element, timeout_ms=3500
        ):
            return False
        self.page.wait_for_timeout(250)
        return self._workday_prompt_committed(element, answer)

    def _wait_for_control_committed(
        self,
        control_id: str,
        *,
        timeout_ms: int = 2500,
        poll_ms: int = 100,
    ) -> bool:
        timeout_ms = max(0, min(int(timeout_ms), 5000))
        poll_ms = max(10, min(int(poll_ms), 250))
        attempts = max(1, (timeout_ms // poll_ms) + 1)
        for attempt in range(attempts):
            if self._control_committed(control_id):
                return True
            if attempt + 1 < attempts:
                self.page.wait_for_timeout(poll_ms)
        return False

    # WORKDAY_PHONE_CANONICAL_VARIANTS_V1
    @staticmethod
    def _workday_phone_variants(value: str) -> list[str]:
        raw = " ".join(str(value or "").split()).strip()
        if not raw:
            return []
        digits = re.sub(r"\D+", "", raw)
        variants: list[str] = [raw]
        if digits:
            variants.append(digits)
        local = digits
        if len(digits) == 11 and digits.startswith("1"):
            local = digits[1:]
            variants.append(local)
        if len(local) == 10:
            area, prefix, line = local[:3], local[3:6], local[6:]
            variants.extend(
                [
                    f"({area}) {prefix}-{line}",
                    f"{area}-{prefix}-{line}",
                    f"{area} {prefix} {line}",
                    f"{area}{prefix}{line}",
                ]
            )
            if len(digits) == 11 and digits.startswith("1"):
                variants.extend(
                    [
                        f"+1 {area}-{prefix}-{line}",
                        f"+1 ({area}) {prefix}-{line}",
                    ]
                )
        unique: list[str] = []
        seen: set[str] = set()
        for item in variants:
            candidate = str(item or "").strip()
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            unique.append(candidate)
        return unique

    def _legal_attestation_identity(
        self,
        *,
        question: dict[str, Any],
        control: dict[str, Any],
    ) -> dict[str, Any]:
        """Build a hash-only identity for one exact legal-attestation surface."""
        control_id = str(control.get("controlId") or "")
        element = self._element(control_id)
        surface = element.evaluate(
            r"""element => {
              const compact = value => String(value || '').replace(/\s+/g, ' ').trim();
              let scope = element.closest(
                'fieldset,section,[role="group"],[data-automation-id*="section" i]'
              );
              if (!scope) scope = element.parentElement;
              const links = scope
                ? Array.from(scope.querySelectorAll('a[href]')).slice(0, 20).map(link => ({
                    href: new URL(link.getAttribute('href') || '', document.baseURI).href,
                    label: compact(
                      link.innerText
                      || link.getAttribute('aria-label')
                      || link.getAttribute('title')
                      || ''
                    ),
                  }))
                : [];
              return {
                scopeText: compact(scope?.innerText || ''),
                links,
              };
            }"""
        )
        if not isinstance(surface, dict):
            surface = {}
        label = " ".join(
            str(value or "").strip()
            for value in (
                question.get("rawText"),
                question.get("label"),
                control.get("label"),
                control.get("ariaLabel"),
            )
            if str(value or "").strip()
        )
        fingerprint = logical_field_fingerprint(question, control)
        if not fingerprint:
            raise ValueError("Legal attestation has no stable logical field fingerprint")
        terms_material = {
            "scope_text_digest": digest(str(surface.get("scopeText") or "")),
            "links": [
                {
                    "href_digest": digest(str(item.get("href") or "")),
                    "label_digest": digest(str(item.get("label") or "")),
                }
                for item in list(surface.get("links") or [])
                if isinstance(item, dict)
            ],
        }
        return {
            "semantic_type": "LEGAL_ATTESTATION",
            "logical_field_fingerprint": digest(fingerprint),
            "label_digest": digest(label),
            "terms_identity_digest": digest(terms_material),
            "provider_host": str(urlsplit(self.page.url).hostname or "")
            .casefold()
            .rstrip("."),
        }

    def _workday_fill_control(
        self,
        *,
        control: dict[str, Any],
        question: dict[str, Any],
        value: str,
    ) -> dict[str, Any] | None:
        if provider_for_url(self.page.url) != "WORKDAY":
            return None

        control_id = str(control.get("controlId") or "")
        element = self._element(control_id)
        metadata = element.evaluate(
            """element => ({
              tag: element.tagName.toLowerCase(),
              type: String(element.type || '').toLowerCase(),
              role: element.getAttribute('role') || '',
              hasPopup: element.getAttribute('aria-haspopup') || '',
              autocomplete: element.getAttribute('aria-autocomplete') || '',
              automationId: element.getAttribute('data-automation-id') || '',
              id: element.id || '',
              name: element.getAttribute('name') || ''
            })"""
        )
        tag = str(metadata.get("tag") or "")
        input_type = str(metadata.get("type") or "")
        role = str(metadata.get("role") or "").casefold()
        has_popup = str(metadata.get("hasPopup") or "").casefold()
        aria_autocomplete = str(metadata.get("autocomplete") or "").casefold()
        automation_id = str(metadata.get("automationId") or "").casefold()
        semantic = str(
            question.get("semanticType") or question.get("semantic_type") or ""
        ).upper()
        question_text = str(
            question.get("rawText") or question.get("question") or ""
        ).casefold()
        kind = str(control.get("kind") or "").upper()
        prompt_like = (
            tag in {"input", "textarea"}
            and (
                role == "combobox"
                or has_popup in {"listbox", "tree", "grid"}
                or aria_autocomplete in {"list", "both"}
                or any(
                    token in automation_id
                    for token in ("prompt", "search", "lookup", "typeahead")
                )
            )
        )
        choice_like = (
            kind in {"SELECT", "COMBOBOX"}
            or role in {"combobox", "listbox"}
            or has_popup not in {"", "false", "none"}
            or aria_autocomplete in {"list", "both"}
            or prompt_like
            or "select one" in question_text
        )

        if prompt_like and self._workday_prompt_committed(element, str(value)):
            return {
                "status": "FILLED",
                "reason": "Workday prompt already has the exact selected item",
                "strategy": "WORKDAY_PROMPT_SELECTED_ITEM",
                "verification": "POST_ACTION_PROVIDER_VERIFIED",
            }

        if (
            semantic == "PHONE"
            and tag in {"input", "textarea"}
            and input_type not in {
                "file","password","hidden","submit","button","reset",
                "radio","checkbox","date",
            }
        ):
            for candidate in self._workday_phone_variants(str(value)):
                with suppress(Exception):
                    element = self._element(control_id)
                    element.click()
                    element.press("Control+A")
                    element.press("Backspace")
                    element.type(candidate, delay=35)
                    try:
                        element.press("Tab")
                    except Exception:
                        self.page.keyboard.press("Tab")
                    self.page.wait_for_timeout(400)
                    if self._wait_for_control_committed(
                        control_id, timeout_ms=1800, poll_ms=100
                    ):
                        return {
                            "status": "FILLED",
                            "reason": "Workday phone committed from canonical phone digits",
                            "strategy": "WORKDAY_PHONE_CANONICAL_VARIANT",
                            "verification": "POST_ACTION_PROVIDER_VERIFIED",
                        }
            return {
                "status": "FAILED",
                "reason": "Workday rejected all equivalent canonical phone renderings",
                "strategy": "WORKDAY_PHONE_CANONICAL_VARIANT",
                "verification": "FAILED_CLOSED",
            }

        if tag in {"input", "textarea"} and input_type not in {
            "file","password","hidden","submit","button","reset",
            "radio","checkbox","date",
        }:
            element.click()
            element.press("Control+A")
            element.press("Backspace")
            element.type(str(value), delay=75 if prompt_like else 10)

            if choice_like:
                clicked = self._workday_click_exact_option(
                    str(value), trigger=element, press_enter=False
                )
                if prompt_like:
                    self.page.wait_for_timeout(250)
                    committed_early = self._workday_prompt_committed(
                        element, str(value)
                    )
                    if not committed_early:
                        fallback_ok = self._workday_public_prompt_fallback(
                            element, str(value)
                        )
                        clicked = clicked or fallback_ok
                        committed_early = self._workday_prompt_committed(
                            element, str(value)
                        )
                    if not clicked or not committed_early:
                        return {
                            "status": "FAILED",
                            "reason": (
                                "Workday exact prompt option did not reach "
                                "provider-selected state"
                            ),
                            "strategy": "WORKDAY_PROVIDER_PROMPT",
                            "verification": "FAILED_CLOSED",
                        }
                elif not clicked:
                    return {
                        "status": "FAILED",
                        "reason": "Workday exact provider option was unavailable",
                        "strategy": "WORKDAY_PROVIDER_CHOICE",
                        "verification": "FAILED_CLOSED",
                    }

                try:
                    element.press("Tab")
                except Exception:
                    with suppress(Exception):
                        self.page.keyboard.press("Tab")
            else:
                element.press("Tab")

            self.page.wait_for_timeout(500)
            committed = (
                self._workday_prompt_committed(element, str(value))
                if prompt_like
                else self._wait_for_control_committed(control_id)
            )
            return {
                "status": "FILLED" if committed else "FAILED",
                "reason": (
                    "Workday provider value committed"
                    if committed
                    else "Workday kept the field uncommitted after exact provider interaction"
                ),
                "strategy": "WORKDAY_PROVIDER_PROMPT" if prompt_like
                    else "WORKDAY_TRUSTED_PLAYWRIGHT",
                "verification": (
                    "POST_ACTION_PROVIDER_VERIFIED" if committed else "FAILED_CLOSED"
                ),
            }

        if tag == "select":
            try:
                element.select_option(label=str(value))
            except Exception:
                try:
                    element.select_option(value=str(value))
                except Exception:
                    return {
                        "status": "FAILED",
                        "reason": "Workday native select exact option was unavailable",
                        "strategy": "WORKDAY_TRUSTED_PLAYWRIGHT",
                        "verification": "FAILED_CLOSED",
                    }
            self.page.keyboard.press("Tab")
            committed = self._wait_for_control_committed(control_id)
            return {
                "status": "FILLED" if committed else "FAILED",
                "reason": "Workday native selection committed" if committed
                    else "Workday native selection remained uncommitted",
                "strategy": "WORKDAY_TRUSTED_PLAYWRIGHT",
                "verification": "POST_ACTION_PROVIDER_VERIFIED" if committed
                    else "FAILED_CLOSED",
            }

        if choice_like or tag == "button":
            element.click()
            if not self._workday_click_exact_option(str(value), trigger=element):
                return {
                    "status": "FAILED",
                    "reason": "Workday custom exact option was unavailable",
                    "strategy": "WORKDAY_TRUSTED_PLAYWRIGHT",
                    "verification": "FAILED_CLOSED",
                }
            self.page.keyboard.press("Tab")
            committed = self._wait_for_control_committed(control_id)
            return {
                "status": "FILLED" if committed else "FAILED",
                "reason": "Workday custom selection committed" if committed
                    else "Workday custom selection remained uncommitted",
                "strategy": "WORKDAY_TRUSTED_PLAYWRIGHT",
                "verification": "POST_ACTION_PROVIDER_VERIFIED" if committed
                    else "FAILED_CLOSED",
            }

        return None

    def _file_sha256(self, control_id: str) -> str:
        hashes = UniversalDocumentUploader._file_hashes(
            self._element(control_id)
        )
        if len(hashes) != 1:
            return ""
        return str(hashes[0] or "").strip().lower()

    @staticmethod
    def _upload_key(plan: dict[str, Any], role: str) -> tuple[str, str]:
        return (str(plan.get("plan_id") or ""), str(role))

    def _remember_verified_upload(
        self, *, plan: dict[str, Any], role: str, expected_sha256: str
    ) -> None:
        if self.current_plan(plan) is not True:
            raise ValueError("Hunter plan is stale")
        self._verified_uploads[self._upload_key(plan, role)] = str(
            expected_sha256
        ).strip().lower()

    def _remembered_upload(self, *, plan: dict[str, Any], role: str) -> str:
        if self.current_plan(plan) is not True:
            return ""
        return self._verified_uploads.get(self._upload_key(plan, role), "")

    def _universal_document_upload(
        self,
        *,
        plan: dict[str, Any],
        permissions: dict[str, bool],
    ) -> dict[str, str]:
        if self.current_plan(plan) is not True:
            raise ValueError("Hunter plan is stale")

        resume_spec = None
        if permissions.get("resume_upload") and _enabled(RESUME_UPLOAD_ENV):
            resume = dict(plan.get("resume") or {})
            resume_spec = DocumentSpec(
                role="resume",
                filename=str(resume.get("filename") or ""),
                mime_type=str(resume.get("mime_type") or ""),
                sha256=str(resume.get("artifact_sha256") or ""),
                data=self.artifact_reader(plan),
            )

        cover_spec = None
        cover = dict(plan.get("cover_letter") or {})
        if (
            cover
            and permissions.get("cover_letter_upload")
            and self.cover_letter_reader is not None
        ):
            cover_spec = DocumentSpec(
                role="cover_letter",
                filename=str(cover.get("filename") or ""),
                mime_type=str(cover.get("mime_type") or ""),
                sha256=str(cover.get("artifact_sha256") or ""),
                data=self.cover_letter_reader(plan),
            )

        if resume_spec is None and cover_spec is None:
            return {}

        uploader = UniversalDocumentUploader(self.page, on_event=self.on_event)
        verified = uploader.upload(
            resume=resume_spec,
            cover_letter=cover_spec,
        )
        for role, sha256 in verified.items():
            self._remember_verified_upload(
                plan=plan,
                role=role,
                expected_sha256=sha256,
            )
        return verified

    def _advance_application_entry_surface(self, plan: dict[str, Any]) -> bool:
        """Enter a generic application surface from a job-details shell.

        This is intentionally provider-neutral.  It runs only when the scanner
        sees no application questions and no final-submit boundary, and only one
        visible button has an exact, non-destructive application-entry label.
        """
        if self.current_plan(plan) is not True:
            raise ValueError("Hunter plan is stale")
        described = self._scan()
        page = described["page"]
        controls = {
            str(item.get("controlId") or ""): item
            for item in page.get("controls") or []
            if isinstance(item, dict)
        }
        visible_editable_questions = [
            question
            for question in page.get("questions") or []
            if isinstance(question, dict)
            and isinstance(controls.get(str(question.get("controlId") or "")), dict)
            and controls[str(question.get("controlId") or "")].get("visible") is True
            and controls[str(question.get("controlId") or "")].get("disabled") is not True
            and str(controls[str(question.get("controlId") or "")].get("kind") or "")
            != "BUTTON"
        ]
        if any(
            item.get("action") == "FINAL_SUBMIT" and not item.get("disabled")
            for item in page.get("navigationCandidates") or []
        ):
            return False
        result = self.page.evaluate(
            r"""({ anchorOnly }) => {
              const visible = element => {
                if (!(element instanceof HTMLElement)) return false;
                const style = getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                return style.display !== 'none'
                  && style.visibility !== 'hidden'
                  && Number(style.opacity || 1) !== 0
                  && rect.width > 0 && rect.height > 0;
              };
              const normalized = element => String(
                element.innerText
                || element.value
                || element.getAttribute('aria-label')
                || element.getAttribute('title')
                || ''
              ).replace(/\s+/g, ' ').trim().toLowerCase();
              const allowed = new Set([
                'apply',
                'apply now',
                'start application',
                'begin application',
                'start my application',
              ]);
              const candidates = Array.from(document.querySelectorAll(
                'button,[role="button"],input[type="button"],a'
              )).filter(element => visible(element) && allowed.has(normalized(element)));
              const safeCandidates = anchorOnly
                ? candidates.filter(element => {
                    if (element.tagName !== 'A' || element.closest('form')) return false;
                    const rawHref = element.getAttribute('href') || '';
                    if (!rawHref) return false;
                    const destination = new URL(rawHref, document.baseURI);
                    const current = new URL(document.URL);
                    const currentPath = current.pathname.replace(/\/$/, '');
                    return destination.origin === current.origin
                      && destination.pathname === currentPath + '/apply';
                  })
                : candidates;
              if (safeCandidates.length !== 1) {
                return { advanced: false, count: safeCandidates.length };
              }
              const candidate = safeCandidates[0];
              candidate.click();
              return {
                advanced: true,
                label: normalized(candidate),
                href: candidate.tagName === 'A' ? candidate.href : '',
              };
            }""",
            {"anchorOnly": bool(visible_editable_questions)},
        )
        if not isinstance(result, dict) or result.get("advanced") is not True:
            return False
        self.on_event(
            "APPLICATION_ENTRY_ADVANCED",
            {"strategy": "unique_safe_entry_label", "label": str(result.get("label") or "")[:80]},
        )
        with suppress(Exception):
            self.page.wait_for_timeout(500)
        return True

    @staticmethod
    def _binding_material(binding: dict[str, Any]) -> dict[str, str]:
        return {
            "binding_type": str(binding.get("binding_type") or ""),
            "control_id": str(binding.get("control_id") or ""),
            "action": str(binding.get("action") or ""),
            "method": str(binding.get("method") or "").upper(),
        }

    def _submit_binding(self) -> dict[str, str] | None:
        candidates = [
            item
            for item in self._scan()["page"]["navigationCandidates"]
            if item["action"] == "FINAL_SUBMIT" and not item["disabled"]
        ]
        if len(candidates) != 1:
            return None
        control_id = str(candidates[0]["controlId"])
        observed = self._element(control_id).evaluate(
            r"""element => {
              const form = element.form || element.closest('form');
              if (form) {
                const method = (
                  element.getAttribute('formmethod')
                  || form.getAttribute('method')
                  || 'get'
                ).trim().toUpperCase();
                const rawAction = (
                  element.getAttribute('formaction')
                  || form.getAttribute('action')
                  || document.URL
                );
                return {
                  binding_type: 'NATIVE_FORM',
                  action: new URL(rawAction, document.baseURI).href,
                  method,
                };
              }

              const rawAction = (
                element.getAttribute('data-submit-url')
                || element.getAttribute('data-submit-endpoint')
                || element.getAttribute('data-endpoint')
                || element.getAttribute('data-action')
                || element.getAttribute('data-url')
                || element.getAttribute('href')
                || ''
              ).trim();
              if (!rawAction) return null;
              const method = (
                element.getAttribute('data-method')
                || element.getAttribute('data-http-method')
                || element.getAttribute('formmethod')
                || 'POST'
              ).trim().toUpperCase();
              return {
                binding_type: 'DECLARATIVE_CONTROL',
                action: new URL(rawAction, document.baseURI).href,
                method,
              };
            }"""
        )
        if not isinstance(observed, dict):
            return None
        material = self._binding_material(
            {
                **observed,
                "control_id": control_id,
            }
        )
        if (
            material["binding_type"] not in {"NATIVE_FORM", "DECLARATIVE_CONTROL"}
            or material["method"] not in SUBMIT_MUTATING_METHODS
            or not material["action"]
        ):
            return None
        return {
            **material,
            "binding_digest": digest(material),
        }

    @staticmethod
    def _allowed_submit_action(plan: dict[str, Any], action: str) -> bool:
        parsed = urlsplit(action)
        host = (parsed.hostname or "").casefold().rstrip(".")
        if (
            parsed.scheme.casefold() != "https"
            or not host
            or parsed.username
            or parsed.password
            or parsed.fragment
        ):
            return False
        policy = dict(plan.get("provider_policy") or {})
        allowed = {
            str(value).casefold().rstrip(".")
            for value in policy.get("allowed_hosts") or []
            if str(value).strip()
        }
        target = str(
            dict(plan.get("job") or {}).get("apply_url")
            or dict(plan.get("job") or {}).get("job_url")
            or ""
        )
        target_host = (urlsplit(target).hostname or "").casefold().rstrip(".")
        if target_host:
            allowed.add(target_host)
        return not allowed or any(
            host == suffix or host.endswith("." + suffix) for suffix in allowed
        )

    def _confirmation_snapshot(self) -> dict[str, str] | None:
        result = self.page.evaluate(
            r"""() => {
              const visible = element => {
                if (!(element instanceof HTMLElement)) return false;
                const style = getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                return style.display !== 'none'
                  && style.visibility !== 'hidden'
                  && Number(style.opacity || 1) !== 0
                  && rect.width > 0 && rect.height > 0;
              };
              const patterns = [
                ['application-submitted', /\bapplication\b.{0,80}\bsubmitted\b/i],
                ['application-received', /\bapplication\b.{0,80}\breceived\b/i],
                ['thank-you-applying', /\bthank(?:s| you)\b.{0,80}\bapply(?:ing|ied)\b/i],
                ['successfully-submitted', /\bsuccessfully\b.{0,40}\bsubmitted\b/i],
                ['application-complete', /\bapplication\b.{0,40}\bcomplete(?:d)?\b/i],
              ];
              const selectors = [
                '#application_confirmation',
                '.application-confirmation',
                '[id*="confirmation" i]',
                '[class*="confirmation" i]',
                '[data-testid*="confirmation" i]',
                '[data-qa*="confirmation" i]',
                '[role="status"]',
                '[role="alert"]',
                'main',
                'body',
              ];
              const seen = new Set();
              for (const selector of selectors) {
                const elements = Array.from(
                  document.querySelectorAll(selector)
                ).slice(0, 80);
                for (const element of elements) {
                  if (seen.has(element) || !visible(element)) continue;
                  seen.add(element);
                  const text = String(element.innerText || '')
                    .replace(/\s+/g, ' ').trim();
                  if (!text) continue;
                  for (const [marker, pattern] of patterns) {
                    if (pattern.test(text)) {
                      return {
                        marker,
                        text: text.slice(0, 1000),
                      };
                    }
                  }
                }
              }
              return null;
            }"""
        )
        if not isinstance(result, dict):
            return None
        marker = str(result.get("marker") or "").strip()
        text = str(result.get("text") or "").strip()
        if not marker or not text:
            return None
        return {"marker": marker, "text": text}

    @staticmethod
    def _payload_application_id(payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""
        queue: list[tuple[dict[str, Any], int]] = [(payload, 0)]
        while queue:
            current, depth = queue.pop(0)
            for key, value in current.items():
                normalized = "".join(
                    character
                    for character in str(key).casefold()
                    if character.isalnum()
                )
                if (
                    isinstance(value, (str, int))
                    and (
                        normalized in {
                            "applicationid",
                            "candidateapplicationid",
                            "submissionid",
                            "applicationsubmissionid",
                        }
                        or ("application" in normalized and normalized.endswith("id"))
                    )
                ):
                    candidate = str(value).strip()
                    if candidate:
                        return candidate[:240]
                if depth < 3 and isinstance(value, dict):
                    queue.append((value, depth + 1))
        return ""

    def _observe(self, plan: dict[str, Any]) -> dict[str, Any]:
        described = self._scan()
        page, fields = described["page"], described["fields"]
        files = [c for c in page["controls"] if c.get("inputType") == "file"]
        resume_sha = ""
        cover_letter_sha = ""
        cover_letter_field_present = False
        expected_cover = (
            dict(plan["cover_letter"]) if isinstance(plan.get("cover_letter"), dict) else None
        )
        for control in files:
            identity = (
                str(control.get("name") or "")
                + " "
                + str(control.get("label") or "")
                + " "
                + str(control.get("ariaLabel") or "")
            ).casefold()
            if "cover" in identity:
                cover_letter_field_present = True
            # Independently hash the actual File bytes in the browser.
            file_sha = self._file_sha256(control["controlId"])
            if file_sha and file_sha == plan["resume"]["artifact_sha256"]:
                resume_sha = file_sha
                self._remember_verified_upload(
                    plan=plan, role="resume", expected_sha256=file_sha
                )
            elif (
                file_sha
                and expected_cover is not None
                and file_sha == expected_cover["artifact_sha256"]
            ):
                cover_letter_sha = file_sha
                self._remember_verified_upload(
                    plan=plan, role="cover_letter", expected_sha256=file_sha
                )
        if not resume_sha:
            resume_sha = self._remembered_upload(plan=plan, role="resume")
        if expected_cover is not None and not cover_letter_sha:
            cover_letter_sha = self._remembered_upload(
                plan=plan, role="cover_letter"
            )
        required = [f for f in fields if f["required"]]
        # Some controlled ATS widgets do not expose required/aria-required until
        # provider validation runs. Once a provider marks a control invalid it is
        # blocking even if the raw DOM did not classify it as required.
        blocking = [f for f in fields if f["required"] or f["invalid"]]
        unresolved = [
            {
                "question_key": f["question_key"],
                "control_id": f["control_id"],
                "question": f["question"],
                "semantic_type": f["semantic_type"],
                "semantic_confidence": f.get("semantic_confidence", 0.0),
                "sensitivity": f["sensitivity_class"],
                "question_observation": dict(f.get("question_observation") or {}),
                "reason": "Required or browser-invalid answer is unresolved",
            }
            for f in blocking
            if not self._field_committed(f)
        ]
        # Only safe field summaries enter durable evidence; pageContext never does.
        review_fields = safe_evidence(fields)
        submit_binding = self._submit_binding()
        form_digest = digest(
            {
                "url": self.page.url,
                "fields": review_fields,
                "resume_sha256": resume_sha,
                **({"cover_letter_sha256": cover_letter_sha} if expected_cover is not None else {}),
                "submit_binding": submit_binding,
            }
        )
        return {
            **self.inspect_job(plan=plan),
            "form_digest": form_digest,
            "submit_binding": submit_binding,
            "resume_uploaded": bool(resume_sha),
            "resume_sha256": resume_sha,
            **(
                {
                    "cover_letter_field_present": cover_letter_field_present,
                    "cover_letter_uploaded": bool(cover_letter_sha),
                    "cover_letter_sha256": cover_letter_sha,
                }
                if expected_cover is not None
                else {}
            ),
            "required_fields": len(required),
            "completed_required_fields": sum(
                self._field_committed(f) for f in required
            ),
            "completed_control_ids": [
                f["control_id"] for f in fields if self._field_committed(f)
            ],
            "pending_control_ids": [
                f["control_id"] for f in blocking if not self._field_committed(f)
            ],
            "review_fields": review_fields,
            "unresolved": unresolved,
            "validation_errors": ["Field validation failed" for f in fields if f["invalid"]],
        }

    def prepare_form(
        self,
        *,
        plan: dict[str, Any],
        checkpoint: dict[str, Any] | None,
        resolved_values: dict[str, Any],
    ) -> dict[str, Any]:
        permissions = prepare_permissions(plan)
        normal_fill_enabled = _enabled(NORMAL_AUTOFILL_ENV) and permissions[
            "normal_answer_autofill"
        ]
        if self.current_plan(plan) is not True:
            raise ValueError("Hunter plan is stale")
        accumulated_review_fields: dict[tuple[str, str], dict[str, Any]] = {}
        prepared_page_ids: set[str] = set()
        for _step in range(10):
            # Cookie/CMP overlays are reversible UI chrome and may otherwise
            # intercept clicks. Dismiss them before each page scan/navigation step.
            self._dismiss_cookie_consent()
            if self.current_plan(plan) is not True:
                raise ValueError("Hunter plan is stale")
            self._advance_application_entry_surface(plan)
            observed = self.inspect_job(plan=plan)
            if observed["security_checkpoint"] or not observed["job_id"]:
                raise ValueError("Browser identity or security checkpoint blocks preparation")
            self._universal_document_upload(
                plan=plan,
                permissions=permissions,
            )
            described = self._scan()
            self.on_event("PAGE_SCANNED", {"page_id": described["page"]["pageId"]})
            for question in described["page"]["questions"]:
                controls = {c["controlId"]: c for c in self._scan()["page"]["controls"]}
                control = controls.get(question["controlId"])
                if not control or control["disabled"]:
                    continue
                if control.get("inputType") == "file":
                    identity = (
                        str(control.get("name") or "") + " " + str(control.get("label") or "")
                    ).casefold()
                    file_controls = [
                        item
                        for item in controls.values()
                        if item.get("inputType") == "file" and not item.get("disabled")
                    ]
                    cover_letter_role = (
                        "cover" in identity and "letter" in identity
                    )
                    resume_role = bool(
                        any(token in identity for token in ("resume", "curriculum vitae"))
                        or re.search(r"(^|\W)cv($|\W)", identity)
                        or (
                            len(file_controls) == 1
                            and not cover_letter_role
                        )
                    )
                    if resume_role:
                        if not _enabled(RESUME_UPLOAD_ENV):
                            raise ValueError("Resume upload is disabled")
                        if self.current_plan(plan) is not True:
                            raise ValueError("Hunter plan is stale")
                        data = self.artifact_reader(plan)
                        if hashlib.sha256(data).hexdigest() != plan["resume"]["artifact_sha256"]:
                            raise ValueError("Resume artifact digest mismatch")
                        self._element(control["controlId"]).set_input_files(
                            {
                                "name": plan["resume"]["filename"],
                                "mimeType": plan["resume"]["mime_type"],
                                "buffer": data,
                            }
                        )
                        observed_sha = self._file_sha256(control["controlId"])
                        if observed_sha != plan["resume"]["artifact_sha256"]:
                            raise ValueError("Resume upload browser digest mismatch")
                        self._remember_verified_upload(
                            plan=plan,
                            role="resume",
                            expected_sha256=observed_sha,
                        )
                        self.on_event(
                            "RESUME_UPLOADED", {"sha256": observed_sha}
                        )
                        continue
                    if (
                        cover_letter_role
                        and isinstance(plan.get("cover_letter"), dict)
                    ):
                        if self.current_plan(plan) is not True:
                            raise ValueError("Hunter plan is stale")
                        if self.cover_letter_reader is None:
                            raise ValueError("Cover-letter artifact reader is unavailable")
                        cover = dict(plan["cover_letter"])
                        data = self.cover_letter_reader(plan)
                        if hashlib.sha256(data).hexdigest() != cover["artifact_sha256"]:
                            raise ValueError("Cover-letter artifact digest mismatch")
                        self._element(control["controlId"]).set_input_files(
                            {
                                "name": cover["filename"],
                                "mimeType": cover["mime_type"],
                                "buffer": data,
                            }
                        )
                        observed_sha = self._file_sha256(control["controlId"])
                        if observed_sha != cover["artifact_sha256"]:
                            raise ValueError("Cover-letter upload browser digest mismatch")
                        self._remember_verified_upload(
                            plan=plan,
                            role="cover_letter",
                            expected_sha256=observed_sha,
                        )
                        self.on_event("COVER_LETTER_UPLOADED", {"sha256": observed_sha})
                    continue
                if not control["visible"]:
                    continue
                if control.get("inputType") == "password":
                    continue

                semantic = str(
                    question.get("semanticType")
                    or question.get("semantic_type")
                    or ""
                ).upper()
                sensitivity = str(
                    question.get("sensitivityClass")
                    or question.get("sensitivity_class")
                    or ("PROTECTED" if question.get("sensitive") else "NORMAL")
                ).upper()
                protected_lane = bool(question.get("sensitive")) or sensitivity in {
                    "PROTECTED",
                    "SELF_ID",
                }
                legal_attestation_lane = semantic == "LEGAL_ATTESTATION"

                if legal_attestation_lane:
                    if self.legal_attestation_authorizer is None:
                        continue
                    identity = self._legal_attestation_identity(
                        question=question,
                        control=control,
                    )
                    proof = self.legal_attestation_authorizer(plan, identity)
                    if (
                        proof.get("authorized") is not True
                        or dict(proof.get("attestation_identity") or {}) != identity
                        or proof.get("submission_authority") is not False
                    ):
                        raise PermissionError(
                            "Legal attestation authorization proof is invalid"
                        )
                    value = "true"
                elif protected_lane:
                    protected_candidates = [
                        a
                        for a in plan["answers"]
                        if protected_answer_matches_question(a, question, control)
                    ]
                    if len(protected_candidates) != 1:
                        continue
                    if self.protected_value_resolver is None:
                        raise RuntimeError(
                            "Protected Workday/application answer requires scoped Hunter resolver"
                        )
                    resolved = self.protected_value_resolver(
                        plan,
                        dict(protected_candidates[0]),
                    )
                    value = resolved.get("value")
                    if value is None:
                        continue
                else:
                    if not normal_fill_enabled:
                        continue
                    candidates = [
                        a
                        for a in plan["answers"]
                        if a.get("autofill_allowed") is True
                        and a.get("sensitivity_class") == "NORMAL"
                        and a.get("execution_value") is not None
                        and answer_matches_question(a, question, control)
                    ]
                    value = resolved_values.get(control["name"])
                    if value is None and len(candidates) == 1:
                        value = candidates[0]["execution_value"]
                    if value is None:
                        continue
                result = self._workday_fill_control(
                    control=control,
                    question=question,
                    value=str(value),
                )
                if result is None:
                    result = self.page.evaluate(
                        "instructions => MunshiPlanRuntime.applyFillInstructions(instructions)",
                        [
                            {
                                "controlId": control["controlId"],
                                "frameId": control["frameId"],
                                "value": str(value),
                                "sensitive": bool(protected_lane),
                                "approved": True,
                            }
                        ],
                    )[0]
                self.on_event(
                    "FIELD_VERIFIED" if result["status"] == "FILLED" else "NEEDS_INPUT",
                    {"control_id": control["controlId"], "status": result["status"]},
                )
            result = self._observe(plan)
            page_id = str(result.get("page_id") or described["page"].get("pageId") or "")
            if page_id:
                prepared_page_ids.add(page_id)
            for field in list(result.get("review_fields") or []):
                if not isinstance(field, dict):
                    continue
                control_id = str(field.get("control_id") or "")
                question_key = str(field.get("question_key") or "")
                identity = control_id or question_key
                if not identity:
                    continue
                accumulated_review_fields[(page_id, identity)] = safe_evidence(dict(field))
            result["review_fields"] = list(accumulated_review_fields.values())
            result["prepared_page_count"] = len(prepared_page_ids)
            if result["resume_uploaded"]:
                self.on_event("RESUME_VERIFIED", {"sha256": result["resume_sha256"]})
            if isinstance(plan.get("cover_letter"), dict) and result.get("cover_letter_uploaded"):
                self.on_event("COVER_LETTER_VERIFIED", {"sha256": result["cover_letter_sha256"]})
            navigation = self._scan()["page"]["navigationCandidates"]
            next_steps = [n for n in navigation if n["action"] == "NEXT" and not n["disabled"]]
            final_submit_steps = [
                n
                for n in navigation
                if n["action"] == "FINAL_SUBMIT" and not n["disabled"]
            ]
            if (
                provider_for_url(self.page.url) == "WORKDAY"
                and not result["unresolved"]
                and not result["validation_errors"]
                and len(final_submit_steps) == 1
            ):
                # Raw provider Review text is transient input only. The
                # reconciler returns a digest and safe mismatch codes; the raw
                # rendering is never placed in durable preparation evidence.
                review_text = str(
                    self.page.evaluate(
                        "() => String(document.body?.innerText || '')"
                    )
                    or ""
                )
                result["review_reconciliation"] = reconcile_provider_review(
                    review_text=review_text,
                    prepared_fields=result["review_fields"],
                    expected_resume_sha256=str(plan["resume"]["artifact_sha256"]),
                    observed_resume_sha256=str(result.get("resume_sha256") or ""),
                    final_submission_boundary=True,
                )
            if result["unresolved"] or result["validation_errors"] or len(next_steps) != 1:
                return result
            outcome = self.page.evaluate(
                "id => MunshiPlanRuntime.applyNavigationAction(id)", next_steps[0]["controlId"]
            )
            if outcome.get("status") != "NAVIGATED":
                return result
            self.on_event("STEP_COMPLETED", {"page_id": result["page_id"]})
        raise ValueError("Preparation exceeded bounded step budget")

    def inspect_submission(self, *, plan: dict[str, Any]) -> dict[str, Any]:
        return {
            **self._observe(plan),
            "supported": True,
            "execution_mode": "GENERIC_DOM_ARIA",
            "plan_current": self.current_plan(plan) is True,
        }

    def submit(self, *, plan: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
        from .execution_policy import validate_submit_observation

        # A late cookie overlay must not masquerade as a changed reviewed form.
        # This remains a bounded cookie-only action and never grants submit authority.
        self._dismiss_cookie_consent()
        observation = self.inspect_submission(plan=plan)
        validate_submit_observation(observation, plan, review)
        buttons = [
            item
            for item in self._scan()["page"]["navigationCandidates"]
            if item["action"] == "FINAL_SUBMIT" and not item["disabled"]
        ]
        if len(buttons) != 1:
            return {"action_executed": False, "verification_status": "BLOCKED"}

        final_observation = self.inspect_submission(plan=plan)
        validate_submit_observation(final_observation, plan, review)
        final_buttons = [
            item
            for item in self._scan()["page"]["navigationCandidates"]
            if item["action"] == "FINAL_SUBMIT" and not item["disabled"]
        ]
        if len(final_buttons) != 1 or final_buttons[0]["controlId"] != buttons[0]["controlId"]:
            return {"action_executed": False, "verification_status": "BLOCKED"}

        submit_binding = final_observation.get("submit_binding")
        if not isinstance(submit_binding, dict):
            return {"action_executed": False, "verification_status": "BLOCKED"}
        expected_binding_type = str(submit_binding.get("binding_type") or "")
        expected_control_id = str(submit_binding.get("control_id") or "")
        expected_submit_url = str(submit_binding.get("action") or "")
        expected_submit_method = str(submit_binding.get("method") or "").upper()
        expected_binding_digest = str(submit_binding.get("binding_digest") or "")
        expected_material = self._binding_material(submit_binding)
        if (
            expected_binding_type not in {"NATIVE_FORM", "DECLARATIVE_CONTROL"}
            or expected_control_id != str(final_buttons[0]["controlId"])
            or expected_submit_method not in SUBMIT_MUTATING_METHODS
            or not expected_submit_url
            or not self._allowed_submit_action(plan, expected_submit_url)
            or expected_binding_digest != digest(expected_material)
        ):
            return {"action_executed": False, "verification_status": "BLOCKED"}

        before_url = str(self.page.url)
        before_confirmation = self._confirmation_snapshot()
        observed_responses: list[Any] = []

        def capture_response(response: Any) -> None:
            try:
                request_method = str(response.request.method).upper()
                response_url = str(response.url)
            except Exception:
                return
            if request_method == expected_submit_method and response_url == expected_submit_url:
                observed_responses.append(response)

        self.page.on("response", capture_response)
        try:
            clicked = self.page.evaluate(
                r"""({ controlId, expected }) => {
                  const element = MunshiPlanRuntime.element(controlId);
                  if (!element) return false;

                  const binding = (() => {
                    const form = element.form || element.closest('form');
                    if (form) {
                      const method = (
                        element.getAttribute('formmethod')
                        || form.getAttribute('method')
                        || 'get'
                      ).trim().toUpperCase();
                      const rawAction = (
                        element.getAttribute('formaction')
                        || form.getAttribute('action')
                        || document.URL
                      );
                      return {
                        binding_type: 'NATIVE_FORM',
                        action: new URL(rawAction, document.baseURI).href,
                        method,
                      };
                    }
                    const rawAction = (
                      element.getAttribute('data-submit-url')
                      || element.getAttribute('data-submit-endpoint')
                      || element.getAttribute('data-endpoint')
                      || element.getAttribute('data-action')
                      || element.getAttribute('data-url')
                      || element.getAttribute('href')
                      || ''
                    ).trim();
                    if (!rawAction) return null;
                    const method = (
                      element.getAttribute('data-method')
                      || element.getAttribute('data-http-method')
                      || element.getAttribute('formmethod')
                      || 'POST'
                    ).trim().toUpperCase();
                    return {
                      binding_type: 'DECLARATIVE_CONTROL',
                      action: new URL(rawAction, document.baseURI).href,
                      method,
                    };
                  })();

                  if (
                    !binding
                    || binding.binding_type !== expected.binding_type
                    || binding.method !== expected.method
                    || binding.action !== expected.action
                  ) return false;
                  element.click();
                  return true;
                }""",
                {
                    "controlId": expected_control_id,
                    "expected": {
                        "binding_type": expected_binding_type,
                        "action": expected_submit_url,
                        "method": expected_submit_method,
                    },
                },
            )
            if clicked is not True:
                return {"action_executed": False, "verification_status": "BLOCKED"}

            for _attempt in range(50):
                confirmation = self._confirmation_snapshot()
                if observed_responses and confirmation is not None:
                    break
                self.page.wait_for_timeout(100)
        finally:
            self.page.remove_listener("response", capture_response)

        confirmation = self._confirmation_snapshot()
        if confirmation is None:
            return {
                "action_executed": True,
                "verification_status": "SUBMISSION_UNVERIFIED",
                "submission_url": self.page.url,
            }

        exact_response: Any | None = None
        response_status = 0
        response_url = ""
        response_payload: Any = None
        for response in reversed(observed_responses):
            try:
                candidate_status = int(response.status)
                candidate_url = str(response.url)
            except Exception:
                candidate_status = 0
                candidate_url = ""
            if not 200 <= candidate_status < 400 or candidate_url != expected_submit_url:
                continue
            exact_response = response
            response_status = candidate_status
            response_url = candidate_url
            try:
                response_payload = response.json()
            except Exception:
                response_payload = None
            break

        if exact_response is None:
            return {
                "action_executed": True,
                "verification_status": "SUBMISSION_UNVERIFIED",
                "submission_url": self.page.url,
                "success_evidence": {
                    "completion_marker": confirmation["marker"],
                    "confirmation_message": confirmation["text"][:500],
                    "exact_action_verified": False,
                },
            }

        expected_job_id = str(plan["job"]["id"])
        if isinstance(response_payload, dict):
            payload_job_id = str(
                response_payload.get("job_id") or response_payload.get("jobId") or ""
            ).strip()
            if payload_job_id and payload_job_id != expected_job_id:
                return {
                    "action_executed": True,
                    "verification_status": "SUBMISSION_UNVERIFIED",
                    "submission_url": self.page.url,
                }
            payload_state = str(
                response_payload.get("status")
                or response_payload.get("state")
                or response_payload.get("result")
                or ""
            ).strip().casefold()
            if payload_state in {"failed", "error", "rejected", "invalid"}:
                return {
                    "action_executed": True,
                    "verification_status": "SUBMISSION_UNVERIFIED",
                    "submission_url": self.page.url,
                }

        confirmation_changed = (
            before_confirmation is None
            or digest(before_confirmation) != digest(confirmation)
        )
        url_changed = str(self.page.url) != before_url
        try:
            post_candidates = [
                item
                for item in self._scan()["page"]["navigationCandidates"]
                if item["action"] == "FINAL_SUBMIT" and not item["disabled"]
            ]
            submit_control_gone = not any(
                str(item.get("controlId") or "") == expected_control_id
                for item in post_candidates
            )
        except Exception:
            submit_control_gone = True

        if not confirmation_changed and not url_changed and not submit_control_gone:
            return {
                "action_executed": True,
                "verification_status": "SUBMISSION_UNVERIFIED",
                "submission_url": self.page.url,
            }

        provider_policy = dict(plan.get("provider_policy") or {})
        declared_provider = str(provider_policy.get("provider") or "GENERIC").upper()
        provider_recipe = provider_for_url(expected_submit_url)
        external_application_id = self._payload_application_id(response_payload)
        confirmation_digest = digest(confirmation)
        submission_reference = "submission-ref-" + digest(
            {
                "job_id": expected_job_id,
                "reviewed_destination": str(review.get("destination_url") or ""),
                "submit_action": expected_submit_url,
                "submit_method": expected_submit_method,
                "action_binding_digest": expected_binding_digest,
                "response_status": response_status,
                "response_url": response_url,
                "confirmation_evidence_digest": confirmation_digest,
                "post_submit_url": str(self.page.url),
            }
        )[:32]
        provider_application_id = external_application_id or submission_reference

        success_evidence = {
            "completion_marker": confirmation["marker"],
            "confirmation_message": confirmation["text"][:500],
            "confirmation_evidence_digest": confirmation_digest,
            "provider": declared_provider,
            "provider_recipe": provider_recipe,
            "job_id": expected_job_id,
            "provider_application_id": provider_application_id,
            "provider_application_id_source": (
                "EMPLOYER_RESPONSE"
                if external_application_id
                else "DERIVED_EXACT_ACTION_EVIDENCE"
            ),
            "submission_reference": submission_reference,
            "reviewed_destination": str(review.get("destination_url") or ""),
            "submit_action": expected_submit_url,
            "submit_method": expected_submit_method,
            "action_binding_digest": expected_binding_digest,
            "response_status": response_status,
            "response_url": response_url,
            "submission_response_marker": "exact-approved-action-response",
            "exact_action_verified": True,
            "post_submit_state_changed": bool(
                confirmation_changed or url_changed or submit_control_gone
            ),
        }
        provider_observation = {
            "verification_method": "EXACT_APPROVED_ACTION_RESPONSE_AND_CONFIRMATION",
            "exact_action_confirmed": True,
            "provider": declared_provider,
            "provider_recipe": provider_recipe,
            "provider_application_id": provider_application_id,
            "submission_reference": submission_reference,
            "target_url": str(review.get("destination_url") or ""),
            "submit_action": expected_submit_url,
            "submit_method": expected_submit_method,
            "response_status": response_status,
            "response_url": response_url,
            "action_binding_digest": expected_binding_digest,
            "confirmation_evidence_digest": confirmation_digest,
            "external_observation_id": "browser-evidence-" + digest(success_evidence)[:32],
            "observed_status": "submitted",
            "lookup_confirmed": False,
        }
        return {
            "action_executed": True,
            "verification_status": "VERIFIED",
            "submission_url": self.page.url,
            "provider_application_id": provider_application_id,
            "submission_reference": submission_reference,
            "success_evidence": success_evidence,
            "provider_observation": provider_observation,
        }