from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from .mechanics_actions import MechanicsActionError, validate_mechanics_actions

AnswerResolver = Callable[[str], str]
SecretResolver = Callable[[str], str]
VerificationResolver = Callable[[str], dict[str, str]]
ArtifactResolver = Callable[[str], dict[str, Any]]

_CANDIDATE_SELECTOR = (
    "input,textarea,select,button,a,[role='button'],[role='combobox'],"
    "[role='listbox'],[role='option'],[role='dialog'],[contenteditable='true'],"
    "summary,[tabindex]"
)
_FINAL_SUBMIT_RE = re.compile(
    r"\b(submit application|send application|complete application|finish application|"
    r"apply now|final submit|submit candidature|send candidature)\b",
    re.IGNORECASE,
)
_NEXT_RE = re.compile(
    r"\b(next|continue|proceed|review|save and continue|save & continue|"
    r"continue application|next step)\b",
    re.IGNORECASE,
)


class TrustedMechanicsError(ValueError):
    pass


@dataclass(frozen=True)
class MechanicsTarget:
    target_ref: str
    frame_index: int
    locator_index: int
    metadata: dict[str, Any]


class TrustedMechanicsExecutor:
    """Executes value-free mechanics while resolving secrets and artifacts locally."""

    def __init__(
        self,
        page: Any,
        *,
        answer_resolver: AnswerResolver | None = None,
        secret_resolver: SecretResolver | None = None,
        verification_resolver: VerificationResolver | None = None,
        artifact_resolver: ArtifactResolver | None = None,
        allowed_open_hosts: set[str] | None = None,
        allow_submit_controls: bool = False,
    ) -> None:
        self.page = page
        self.answer_resolver = answer_resolver
        self.secret_resolver = secret_resolver
        self.verification_resolver = verification_resolver
        self.artifact_resolver = artifact_resolver
        self.allow_submit_controls = bool(allow_submit_controls)
        self.allowed_open_hosts = {
            str(host).strip().casefold().rstrip(".")
            for host in (allowed_open_hosts or set())
            if str(host).strip()
        }
        self._targets: dict[str, tuple[Any, dict[str, Any]]] = {}
        self._initial_url = str(getattr(page, "url", "") or "")

    @staticmethod
    def _clean(value: object, limit: int = 220) -> str:
        clean = re.sub(r"\s+", " ", str(value or "")).strip()
        clean = re.sub(
            r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
            "[redacted-email]",
            clean,
            flags=re.IGNORECASE,
        )
        clean = re.sub(r"\b(?:\+?\d[\d .()/-]{7,}\d)\b", "[redacted-number]", clean)
        return clean[:limit]

    @classmethod
    def _target_ref(cls, frame_index: int, locator_index: int, meta: dict[str, Any]) -> str:
        identity = "\n".join(
            [
                str(frame_index),
                str(locator_index),
                cls._clean(meta.get("tag"), 40).casefold(),
                cls._clean(meta.get("role"), 80).casefold(),
                cls._clean(meta.get("type"), 80).casefold(),
                cls._clean(meta.get("name"), 120).casefold(),
                cls._clean(meta.get("id"), 120).casefold(),
                cls._clean(meta.get("label"), 180).casefold(),
                cls._clean(meta.get("placeholder"), 180).casefold(),
            ]
        )
        return "mt-" + hashlib.sha256(identity.encode()).hexdigest()[:24]

    @staticmethod
    def _final_submit_risk(meta: dict[str, Any]) -> bool:
        label = " ".join(
            str(meta.get(key) or "")
            for key in ("label", "ariaLabel", "title", "name")
        )
        return bool(_FINAL_SUBMIT_RE.search(label))

    def snapshot(self, *, max_targets: int = 180) -> list[dict[str, Any]]:
        self._targets.clear()
        surface: list[dict[str, Any]] = []
        frames = list(getattr(self.page, "frames", []) or [self.page.main_frame])
        for frame_index, frame in enumerate(frames[:24]):
            locator = frame.locator(_CANDIDATE_SELECTOR)
            try:
                count = min(int(locator.count()), max_targets - len(surface))
            except Exception:
                continue
            for locator_index in range(max(0, count)):
                candidate = locator.nth(locator_index)
                try:
                    meta = candidate.evaluate(
                        """element => {
                          const tag = String(element.tagName || '').toLowerCase();
                          const inputType = String(
                            element.getAttribute('type') || ''
                          ).toLowerCase();
                          const role = String(element.getAttribute('role') || '').toLowerCase();
                          const text = String(
                            element.innerText
                            || element.getAttribute('aria-label')
                            || element.getAttribute('title')
                            || ''
                          ).replace(/\s+/g, ' ').trim();
                          const labelElement =
                            element.labels && element.labels.length
                              ? element.labels[0]
                              : null;
                          const label = String(
                            (labelElement && labelElement.innerText)
                            || element.getAttribute('aria-label')
                            || element.getAttribute('placeholder')
                            || text
                            || ''
                          ).replace(/\s+/g, ' ').trim();
                          const style = element instanceof HTMLElement
                            ? getComputedStyle(element)
                            : null;
                          const rect = element instanceof HTMLElement
                            ? element.getBoundingClientRect()
                            : { width: 0, height: 0 };
                          const visible = Boolean(
                            style
                            && style.display !== 'none'
                            && style.visibility !== 'hidden'
                            && Number(style.opacity || 1) !== 0
                            && rect.width > 0
                            && rect.height > 0
                          );
                          return {
                            tag,
                            type: inputType,
                            role,
                            name: String(element.getAttribute('name') || ''),
                            id: String(element.id || ''),
                            label,
                            ariaLabel: String(element.getAttribute('aria-label') || ''),
                            placeholder: String(element.getAttribute('placeholder') || ''),
                            title: String(element.getAttribute('title') || ''),
                            visible,
                            disabled: Boolean(element.disabled)
                              || element.getAttribute('aria-disabled') === 'true',
                            required: Boolean(element.required)
                              || element.getAttribute('aria-required') === 'true',
                            fileInput: tag === 'input' && inputType === 'file',
                            hrefHost: (() => {
                              if (tag !== 'a') return '';
                              try {
                                return new URL(element.href, document.baseURI).hostname;
                              } catch {
                                return '';
                              }
                            })(),
                          };
                        }"""
                    )
                except Exception:
                    continue
                if not isinstance(meta, dict):
                    continue
                if not meta.get("visible") and not meta.get("fileInput"):
                    continue
                meta = {key: value for key, value in meta.items()}
                meta["frameIndex"] = frame_index
                target_ref = self._target_ref(frame_index, locator_index, meta)
                meta["targetRef"] = target_ref
                meta["finalSubmitRisk"] = self._final_submit_risk(meta)
                self._targets[target_ref] = (candidate, meta)
                surface.append(
                    {
                        "targetRef": target_ref,
                        "frameIndex": frame_index,
                        "tag": self._clean(meta.get("tag"), 40),
                        "type": self._clean(meta.get("type"), 80),
                        "role": self._clean(meta.get("role"), 80),
                        "name": self._clean(meta.get("name"), 120),
                        "id": self._clean(meta.get("id"), 120),
                        "label": self._clean(meta.get("label"), 180),
                        "ariaLabel": self._clean(meta.get("ariaLabel"), 180),
                        "placeholder": self._clean(meta.get("placeholder"), 180),
                        "visible": bool(meta.get("visible")),
                        "disabled": bool(meta.get("disabled")),
                        "required": bool(meta.get("required")),
                        "fileInput": bool(meta.get("fileInput")),
                        "finalSubmitRisk": bool(meta.get("finalSubmitRisk")),
                    }
                )
                if len(surface) >= max_targets:
                    return surface
        return surface

    def target_refs(self) -> set[str]:
        return set(self._targets)

    def _target(self, target_ref: str) -> tuple[Any, dict[str, Any]]:
        target = self._targets.get(target_ref)
        if target is None:
            raise TrustedMechanicsError("Mechanics target is stale or unobserved")
        return target

    def _assert_not_final_submit(
        self,
        meta: dict[str, Any],
        *,
        action_type: str,
    ) -> None:
        if meta.get("finalSubmitRisk") is True:
            raise TrustedMechanicsError("Sonnet mechanics cannot operate final-submit controls")
        if (
            not self.allow_submit_controls
            and str(meta.get("type") or "").casefold() == "submit"
            and action_type in {"CLICK", "KEY"}
        ):
            raise TrustedMechanicsError(
                "Submit-type controls require the trusted navigation/final-submit boundary"
            )

    @staticmethod
    def _ensure_ref_resolver(resolver: Any, kind: str) -> Any:
        if not callable(resolver):
            raise TrustedMechanicsError(f"{kind} resolver is unavailable")
        return resolver

    def _verification(self, ref: str) -> dict[str, str]:
        resolver = self._ensure_ref_resolver(
            self.verification_resolver,
            "verification artifact",
        )
        payload = resolver(ref)
        if not isinstance(payload, dict):
            raise TrustedMechanicsError("Verification artifact resolver returned invalid data")
        kind = str(payload.get("kind") or "").strip().upper()
        value = str(payload.get("value") or "")
        if not kind or not value:
            raise TrustedMechanicsError("Verification artifact is unavailable")
        return {"kind": kind, "value": value}

    def _artifact(self, ref: str) -> dict[str, Any]:
        resolver = self._ensure_ref_resolver(self.artifact_resolver, "file artifact")
        payload = resolver(ref)
        if not isinstance(payload, dict):
            raise TrustedMechanicsError("Artifact resolver returned invalid data")
        if not payload.get("name") or not payload.get("mimeType") or payload.get("buffer") is None:
            raise TrustedMechanicsError("Artifact payload is incomplete")
        return payload

    def _value_ref(self, ref: str) -> str:
        if ref.startswith("answer:"):
            resolver = self._ensure_ref_resolver(self.answer_resolver, "answer")
            return str(resolver(ref))
        if ref.startswith("secret:"):
            resolver = self._ensure_ref_resolver(self.secret_resolver, "secret")
            return str(resolver(ref))
        if ref.startswith("verification:"):
            return self._verification(ref)["value"]
        raise TrustedMechanicsError("Unsupported mechanics value reference")

    def _select(self, locator: Any, value: str) -> None:
        try:
            tag = str(locator.evaluate("element => element.tagName.toLowerCase()"))
        except Exception as error:
            raise TrustedMechanicsError("Select target disappeared") from error
        if tag == "select":
            matched = locator.evaluate(
                """(element, requested) => {
                  const option = Array.from(element.options || []).find(
                    item => item.label === requested || item.value === requested
                  );
                  return option ? option.value : null;
                }""",
                value,
            )
            if matched is None:
                raise TrustedMechanicsError("Exact native select option was not found")
            locator.select_option(value=str(matched))
            return
        locator.click()
        option = self.page.get_by_role("option", name=value, exact=True)
        if option.count() != 1:
            raise TrustedMechanicsError("Exact custom option is missing or ambiguous")
        option.click()

    def _wait_for_state(
        self,
        state: str,
        target_ref: str | None,
        *,
        timeout_ms: int = 2500,
    ) -> None:
        if state == "PAGE_STABLE":
            self.page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
            self.page.wait_for_timeout(150)
            return
        if state == "URL_CHANGED":
            initial = self._initial_url
            self.page.wait_for_function(
                "initial => location.href !== initial",
                arg=initial,
                timeout=timeout_ms,
            )
            self._initial_url = str(self.page.url)
            return
        if state == "AUTH_STATE_CHANGED":
            self.page.wait_for_timeout(250)
            return
        if not target_ref:
            raise TrustedMechanicsError("Target-bound wait state requires targetRef")
        locator, _meta = self._target(target_ref)
        if state == "TARGET_VISIBLE":
            locator.wait_for(state="visible", timeout=timeout_ms)
            return
        if state == "TARGET_HIDDEN":
            locator.wait_for(state="hidden", timeout=timeout_ms)
            return
        if state == "OPTIONS_VISIBLE":
            self.page.get_by_role("option").first.wait_for(state="visible", timeout=timeout_ms)
            return
        if state == "VALUE_COMMITTED":
            attempts = max(1, int(timeout_ms / 50))
            for _attempt in range(attempts):
                committed = locator.evaluate(
                    """element => {
                      if (!element || !element.isConnected) return false;
                      if ('value' in element) return String(element.value || '').length > 0;
                      return element.getAttribute('aria-checked') === 'true'
                        || element.getAttribute('aria-selected') === 'true';
                    }"""
                )
                if committed is True:
                    return
                self.page.wait_for_timeout(50)
            raise TrustedMechanicsError("Mechanics value did not commit")
        if state == "FILE_ATTACHED":
            attached = locator.evaluate(
                "element => Boolean(element.files && element.files.length)"
            )
            if attached is not True:
                raise TrustedMechanicsError("Expected file is not attached")
            return
        raise TrustedMechanicsError("Unsupported mechanics wait state")

    def execute(
        self,
        actions: object,
        *,
        allowed_value_refs: set[str],
    ) -> None:
        validated = validate_mechanics_actions(
            actions,
            allowed_target_refs=self.target_refs(),
            allowed_value_refs=allowed_value_refs,
        )
        for action in validated:
            action_type = str(action["type"])
            target_ref = (
                str(action["targetRef"]) if isinstance(action.get("targetRef"), str) else None
            )
            locator = meta = None
            if target_ref:
                locator, meta = self._target(target_ref)

            if action_type == "FOCUS":
                locator.focus()
            elif action_type == "CLICK":
                self._assert_not_final_submit(meta, action_type="CLICK")
                locator.click()
            elif action_type == "NEXT":
                self._assert_not_final_submit(meta, action_type="NEXT")
                label = " ".join(
                    str(meta.get(key) or "")
                    for key in ("label", "ariaLabel", "title", "name")
                )
                if not _NEXT_RE.search(label):
                    raise TrustedMechanicsError("NEXT target is not recognizably pre-submit")
                locator.click()
            elif action_type == "TYPE_ANSWER_REF":
                resolver = self._ensure_ref_resolver(self.answer_resolver, "answer")
                locator.fill(str(resolver(str(action["answerRef"]))))
            elif action_type == "FILL_SECRET_REF":
                resolver = self._ensure_ref_resolver(self.secret_resolver, "secret")
                locator.fill(str(resolver(str(action["secretRef"]))))
            elif action_type == "FILL_VERIFICATION_ARTIFACT":
                artifact = self._verification(str(action["verificationRef"]))
                if "LINK" in artifact["kind"]:
                    raise TrustedMechanicsError("Verification link cannot be filled into a control")
                locator.fill(artifact["value"])
            elif action_type == "UPLOAD_ARTIFACT":
                if not bool(meta.get("fileInput")):
                    raise TrustedMechanicsError("UPLOAD_ARTIFACT requires a file input target")
                locator.set_input_files(self._artifact(str(action["artifactRef"])))
            elif action_type == "SELECT":
                self._select(locator, self._value_ref(str(action["valueRef"])))
            elif action_type == "KEY":
                self._assert_not_final_submit(meta, action_type="KEY")
                locator.press(str(action["key"]))
            elif action_type == "OPEN_LINK":
                artifact = self._verification(str(action["verificationRef"]))
                if "LINK" not in artifact["kind"]:
                    raise TrustedMechanicsError("OPEN_LINK requires a link artifact")
                parsed = urlsplit(artifact["value"])
                host = str(parsed.hostname or "").casefold().rstrip(".")
                if (
                    parsed.scheme not in {"http", "https"}
                    or not host
                    or self.allowed_open_hosts
                    and not any(
                        host == suffix or host.endswith("." + suffix)
                        for suffix in self.allowed_open_hosts
                    )
                ):
                    raise TrustedMechanicsError("Verification link host is not allowed")
                self.page.goto(artifact["value"], wait_until="domcontentloaded")
            elif action_type == "WAIT_FOR_STATE":
                self._wait_for_state(str(action["state"]), target_ref)
            else:
                raise MechanicsActionError("Unsupported trusted mechanics action")
