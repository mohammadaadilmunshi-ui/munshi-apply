"""Plan adapter over the existing extension scanner/classifier/fill implementation.

The caller supplies an already selected Playwright page, scoped artifact reader,
and Hunter freshness validator. No credentials, browser launch or navigation to
an employer happens at module import or plan acceptance.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .execution_policy import prepare_permissions, safe_evidence
from .hunter_plan_semantic_bridge import answer_matches_question

RESUME_UPLOAD_ENV = "MUNSHI_APPLY_RESUME_UPLOAD_ENABLED"
NORMAL_AUTOFILL_ENV = "MUNSHI_APPLY_NORMAL_ANSWER_AUTOFILL_ENABLED"


def _enabled(name: str) -> bool:
    return str(os.getenv(name) or "").strip().casefold() in {"1", "true", "yes", "on"}


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


KNOWN_PROVIDER_RECIPES = {
    "GREENHOUSE": ("greenhouse.io",),
    "LEVER": ("lever.co",),
    "ASHBY": ("ashbyhq.com",),
    "SMARTRECRUITERS": ("smartrecruiters.com",),
    "WORKDAY": ("myworkdayjobs.com", "myworkdaysite.com"),
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
    ) -> None:
        self.page = page
        self.artifact_reader = artifact_reader
        self.cover_letter_reader = cover_letter_reader
        self.current_plan = current_plan
        self.runtime_path = runtime_path
        self.on_event: Callable[[str, dict[str, Any]], None] = lambda _kind, _evidence: None

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
        # Exact origin/path/query binding. Redirected flows require a new plan.
        same = (actual.scheme, actual.netloc, actual.path, actual.query) == (
            expected.scheme,
            expected.netloc,
            expected.path,
            expected.query,
        )
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

    def _submit_binding(self) -> dict[str, str] | None:
        candidates = [
            item
            for item in self._scan()["page"]["navigationCandidates"]
            if item["action"] == "FINAL_SUBMIT" and not item["disabled"]
        ]
        if len(candidates) != 1:
            return None
        return self._element(candidates[0]["controlId"]).evaluate(
            """element => {
              const form = element.form || element.closest('form');
              if (!form) return null;
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
                action: new URL(rawAction, document.baseURI).href,
                method,
              };
            }"""
        )

    def _observe(self, plan: dict[str, Any]) -> dict[str, Any]:
        described = self._scan()
        page, fields = described["page"], described["fields"]
        files = [c for c in page["controls"] if c.get("inputType") == "file"]
        resume_sha = ""
        cover_letter_sha = ""
        expected_cover = (
            dict(plan["cover_letter"]) if isinstance(plan.get("cover_letter"), dict) else None
        )
        for control in files:
            # Independently hash the actual File bytes in the browser.
            data = self._element(control["controlId"]).evaluate("""async element => {
              if (!element.files || element.files.length !== 1) return null;
              const file = element.files[0];
              const bytes = await file.arrayBuffer();
              const hash = await crypto.subtle.digest('SHA-256', bytes);
              return { name: file.name, sha: Array.from(new Uint8Array(hash),
                byte => byte.toString(16).padStart(2, '0')).join('') };
            }""")
            if data and data["sha"] == plan["resume"]["artifact_sha256"]:
                resume_sha = data["sha"]
            elif (
                data
                and expected_cover is not None
                and data["sha"] == expected_cover["artifact_sha256"]
            ):
                cover_letter_sha = data["sha"]
        required = [f for f in fields if f["required"]]
        unresolved = [
            {
                "question_key": f["question_key"],
                "control_id": f["control_id"],
                "question": f["question"],
                "semantic_type": f["semantic_type"],
                "sensitivity": f["sensitivity_class"],
                "reason": "Required answer is unresolved",
            }
            for f in required
            if not f["satisfied"]
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
                    "cover_letter_uploaded": bool(cover_letter_sha),
                    "cover_letter_sha256": cover_letter_sha,
                }
                if expected_cover is not None
                else {}
            ),
            "required_fields": len(required),
            "completed_required_fields": sum(bool(f["satisfied"]) for f in required),
            "completed_control_ids": [f["control_id"] for f in fields if f["satisfied"]],
            "pending_control_ids": [f["control_id"] for f in required if not f["satisfied"]],
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
        for _step in range(10):
            # Cookie/CMP overlays are reversible UI chrome and may otherwise
            # intercept clicks. Dismiss them before each page scan/navigation step.
            self._dismiss_cookie_consent()
            if self.current_plan(plan) is not True:
                raise ValueError("Hunter plan is stale")
            observed = self.inspect_job(plan=plan)
            if observed["security_checkpoint"] or not observed["job_id"]:
                raise ValueError("Browser identity or security checkpoint blocks preparation")
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
                    if "resume" in identity:
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
                        self.on_event(
                            "RESUME_UPLOADED", {"sha256": plan["resume"]["artifact_sha256"]}
                        )
                        continue
                    if (
                        "cover" in identity
                        and "letter" in identity
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
                        self.on_event("COVER_LETTER_UPLOADED", {"sha256": cover["artifact_sha256"]})
                    continue
                if not control["visible"]:
                    continue
                if question["sensitive"] or control.get("inputType") == "password":
                    continue  # Protected execution requires a scoped resolver, never plain memory.
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
                result = self.page.evaluate(
                    "instructions => MunshiPlanRuntime.applyFillInstructions(instructions)",
                    [
                        {
                            "controlId": control["controlId"],
                            "frameId": control["frameId"],
                            "value": str(value),
                            "sensitive": False,
                            "approved": True,
                        }
                    ],
                )[0]
                self.on_event(
                    "FIELD_VERIFIED" if result["status"] == "FILLED" else "NEEDS_INPUT",
                    {"control_id": control["controlId"], "status": result["status"]},
                )
            result = self._observe(plan)
            if result["resume_uploaded"]:
                self.on_event("RESUME_VERIFIED", {"sha256": result["resume_sha256"]})
            if isinstance(plan.get("cover_letter"), dict) and result.get("cover_letter_uploaded"):
                self.on_event("COVER_LETTER_VERIFIED", {"sha256": result["cover_letter_sha256"]})
            navigation = self._scan()["page"]["navigationCandidates"]
            next_steps = [n for n in navigation if n["action"] == "NEXT" and not n["disabled"]]
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
            "supported": provider_for_url(self.page.url) == "GREENHOUSE",
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
            n
            for n in self._scan()["page"]["navigationCandidates"]
            if n["action"] == "FINAL_SUBMIT" and not n["disabled"]
        ]
        if len(buttons) != 1:
            return {"action_executed": False, "verification_status": "BLOCKED"}

        final_observation = self.inspect_submission(plan=plan)
        validate_submit_observation(final_observation, plan, review)
        final_buttons = [
            n
            for n in self._scan()["page"]["navigationCandidates"]
            if n["action"] == "FINAL_SUBMIT" and not n["disabled"]
        ]
        if len(final_buttons) != 1 or final_buttons[0]["controlId"] != buttons[0]["controlId"]:
            return {"action_executed": False, "verification_status": "BLOCKED"}

        submit_binding = final_observation.get("submit_binding")
        if not isinstance(submit_binding, dict):
            return {"action_executed": False, "verification_status": "BLOCKED"}
        expected_submit_url = str(submit_binding.get("action") or "")
        expected_submit_method = str(submit_binding.get("method") or "").upper()
        if not expected_submit_url or expected_submit_method != "POST":
            return {"action_executed": False, "verification_status": "BLOCKED"}

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
                """({ controlId, expected }) => {
                  const element = MunshiPlanRuntime.element(controlId);
                  if (!element) return false;
                  const form = element.form || element.closest('form');
                  if (!form) return false;
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
                  const action = new URL(rawAction, document.baseURI).href;
                  if (method !== expected.method || action !== expected.action) return false;
                  element.click();
                  return true;
                }""",
                {
                    "controlId": final_buttons[0]["controlId"],
                    "expected": {
                        "action": expected_submit_url,
                        "method": expected_submit_method,
                    },
                },
            )
            if clicked is not True:
                return {"action_executed": False, "verification_status": "BLOCKED"}
            try:
                self.page.locator("#application_confirmation, .application-confirmation").wait_for(
                    state="visible", timeout=5000
                )
            except Exception:
                return {"action_executed": True, "verification_status": "SUBMISSION_UNVERIFIED"}
        finally:
            self.page.remove_listener("response", capture_response)

        marker = self.page.locator("#application_confirmation, .application-confirmation").first
        message = marker.inner_text().strip()
        if not any(
            phrase in message.casefold()
            for phrase in (
                "application has been submitted",
                "application has been received",
                "thank you for applying",
                "thanks for applying",
            )
        ):
            return {"action_executed": True, "verification_status": "SUBMISSION_UNVERIFIED"}

        expected_provider = str(plan["provider_policy"]["provider"])
        expected_job_id = str(plan["job"]["id"])
        correlated: dict[str, Any] | None = None
        for response in reversed(observed_responses):
            try:
                response_status = int(response.status)
                response_url = str(response.url)
                payload = response.json()
            except Exception:
                response_status = 0
                response_url = ""
                payload = None
            if not 200 <= response_status < 300:
                continue
            if response_url != expected_submit_url:
                continue
            if provider_for_url(response_url) != expected_provider:
                continue
            if not isinstance(payload, dict):
                continue
            observed_job_id = str(payload.get("job_id") or payload.get("jobId") or "")
            provider_application_id = str(
                payload.get("application_id") or payload.get("applicationId") or ""
            ).strip()
            response_state = str(payload.get("status") or "").strip().casefold()
            if observed_job_id != expected_job_id or not provider_application_id:
                continue
            if response_state not in {"submitted", "received"}:
                continue
            correlated = {
                "provider_application_id": provider_application_id,
                "response_status": response_status,
                "response_url": response_url,
                "submit_action": expected_submit_url,
                "submit_method": expected_submit_method,
                "submission_response_marker": "provider-json-application-id",
            }
            break

        if correlated is None:
            return {
                "action_executed": True,
                "verification_status": "SUBMISSION_UNVERIFIED",
                "submission_url": self.page.url,
                "success_evidence": {
                    "completion_marker": "greenhouse-application-confirmation",
                    "confirmation_message": message[:500],
                    "provider": expected_provider,
                    "job_id": expected_job_id,
                },
            }

        return {
            "action_executed": True,
            "verification_status": "VERIFIED",
            "submission_url": self.page.url,
            "provider_application_id": correlated["provider_application_id"],
            "success_evidence": {
                "completion_marker": "greenhouse-application-confirmation",
                "confirmation_message": message[:500],
                "provider": expected_provider,
                "job_id": expected_job_id,
                **correlated,
            },
        }