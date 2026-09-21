from __future__ import annotations

import os
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from munshi_apply_native.browser_runtime import resolve_browser_executable
from munshi_apply_native.mechanics_recovery_coordinator import MechanicsRecoveryCoordinator
from munshi_apply_native.trusted_mechanics_executor import (
    TrustedMechanicsError,
    TrustedMechanicsExecutor,
)

pytestmark = pytest.mark.skipif(
    os.getenv("MUNSHI_RUN_BROWSER_TESTS") != "1",
    reason="real browser integration lane is opt-in",
)


class _Fallback:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def propose(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(payload)
        targets = {
            str(item.get("label") or ""): str(item["targetRef"])
            for item in payload["mechanicsSurface"]
            if isinstance(item, dict)
        }
        refs = {
            str(item.get("kind") or ""): str(item["ref"])
            for item in payload["availableRefs"]
            if isinstance(item, dict)
        }
        return {
            "actions": [
                {
                    "type": "UPLOAD_ARTIFACT",
                    "targetRef": targets["Choose resume"],
                    "artifactRef": refs["RESUME"],
                },
                {
                    "type": "CLICK",
                    "targetRef": targets["Country picker"],
                },
                {
                    "type": "SELECT",
                    "targetRef": targets["Country picker"],
                    "valueRef": refs["ANSWER"],
                },
                {
                    "type": "CLICK",
                    "targetRef": targets["Iframe confirmation"],
                },
                {
                    "type": "NEXT",
                    "targetRef": targets["Continue"],
                },
                {"type": "WAIT_FOR_STATE", "state": "PAGE_STABLE"},
            ],
            "reason": (
                "Use the hidden uploader, shadow picker, iframe control, then continue"
            ),
        }


class _Recipes:
    def __init__(self) -> None:
        self.lookups = 0

    def lookup(self, _payload: dict[str, object]) -> None:
        self.lookups += 1
        return None


class _Teach:
    def __init__(self) -> None:
        self.recipes = _Recipes()
        self.lessons: list[dict[str, object]] = []

    def capture(self, lesson: dict[str, object]) -> None:
        self.lessons.append(lesson)


def _html() -> str:
    return """<!doctype html>
<html>
<body>
  <div id="upload-shell">
    <button id="upload-button" type="button">Choose resume</button>
    <input id="resume-file" type="file" aria-label="Resume upload"
      style="position:absolute;left:-10000px" />
  </div>

  <div id="shadow-host"></div>

  <iframe id="mechanics-frame"
    srcdoc="<!doctype html><html><body>
      <button type='button' aria-label='Iframe confirmation'
        onclick='document.body.dataset.confirmed=&quot;yes&quot;'>
        Confirm iframe mechanics
      </button>
    </body></html>"></iframe>

  <button id="continue" type="button" aria-label="Continue">Continue</button>
  <button id="final-submit" type="submit" aria-label="Submit application">
    Submit application
  </button>

  <script>
    document.querySelector("#upload-button").addEventListener("click", () => {
      document.querySelector("#resume-file").click();
    });
    const host = document.querySelector("#shadow-host");
    const root = host.attachShadow({mode: "open"});
    root.innerHTML =
      '<button id="country" type="button" role="combobox" ' +
      'aria-label="Country picker">Country picker</button>' +
      '<div id="options" hidden>' +
      '<div role="option">United States</div>' +
      '<div role="option">Canada</div>' +
      '</div>' +
      '<input id="selected-country" aria-label="Selected country" />';
    const picker = root.querySelector("#country");
    picker.addEventListener("click", () => {
      root.querySelector("#options").hidden = false;
    });
    root.querySelectorAll("[role=option]").forEach((option) => {
      option.addEventListener("click", () => {
        root.querySelector("#selected-country").value = option.textContent;
        picker.setAttribute("data-selected", option.textContent);
        root.querySelector("#options").hidden = true;
      });
    });
    document.querySelector("#continue").addEventListener("click", () => {
      const file = document.querySelector("#resume-file").files[0];
      const country = root.querySelector("#selected-country").value;
      const frame = document.querySelector("#mechanics-frame");
      const frameConfirmed =
        frame.contentDocument.body.getAttribute("data-confirmed") === "yes";
      if (file && country === "United States" && frameConfirmed) {
        document.body.setAttribute("data-step", "review");
        document.querySelector("#continue").remove();
      }
    });
    document.querySelector("#final-submit").addEventListener("click", (event) => {
      event.preventDefault();
      document.body.setAttribute("data-submitted", "true");
    });
  </script>
</body>
</html>"""


def test_sonnet_mechanics_handles_hidden_upload_shadow_select_and_next_without_submit(
    tmp_path: Path,
) -> None:
    browser_path = resolve_browser_executable()
    fallback = _Fallback()
    teach = _Teach()
    plan = {"application_id": "app-mechanics-browser"}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=browser_path,
        )
        page = browser.new_page()
        page.set_content(_html())

        answer_ref = "answer:country"
        artifact_ref = "artifact:resume"
        resume_payload = {
            "name": "resume.pdf",
            "mimeType": "application/pdf",
            "buffer": b"%PDF-1.4 fixture\n%%EOF\n",
        }
        executor = TrustedMechanicsExecutor(
            page,
            answer_resolver=lambda ref: {
                answer_ref: "United States",
            }[ref],
            artifact_resolver=lambda ref: {
                artifact_ref: resume_payload,
            }[ref],
        )
        surface = executor.snapshot()
        assert any(item["label"] == "Resume upload" for item in surface)
        assert any(item["label"] == "Choose resume" for item in surface)
        assert any(item["label"] == "Country picker" for item in surface)
        assert any(item["label"] == "Continue" for item in surface)
        iframe_target = next(
            item for item in surface if item["label"] == "Iframe confirmation"
        )
        assert int(iframe_target["frameIndex"]) > 0
        final_target = next(
            item for item in surface if item["label"] == "Submit application"
        )
        assert final_target["finalSubmitRisk"] is True

        payload = {
            "siteOrigin": "https://careers.example.com",
            "componentFingerprint": "cfp-" + "a" * 40,
            "semanticType": "PAGE_MECHANICS",
            "controlKind": "PAGE",
            "label": "Synthetic application mechanics",
            "atsFamily": "GENERIC",
            "failureReason": "Deterministic mechanics did not advance",
            "goal": (
                "Attach resume, select country, confirm the iframe control, and continue"
            ),
            "reversible": True,
            "sensitive": False,
            "authenticationBoundary": False,
            "finalSubmit": False,
            "secretMaterialExposed": False,
            "verificationMaterialExposed": False,
            "mechanicsMode": True,
            "mechanicsSurface": surface,
            "availableRefs": [
                {
                    "ref": answer_ref,
                    "kind": "ANSWER",
                    "semanticType": "COUNTRY",
                    "label": "country",
                },
                {"ref": artifact_ref, "kind": "RESUME"},
            ],
        }

        coordinator = MechanicsRecoveryCoordinator(
            fallback_service=fallback,
            teach_service=teach,
        )

        def verify() -> bool:
            return (
                page.locator("body").get_attribute("data-step") == "review"
                and page.locator("body").get_attribute("data-submitted") is None
            )

        source = coordinator.attempt(
            plan=plan,
            payload=payload,
            executor=executor,
            allowed_value_refs={answer_ref, artifact_ref},
            verify=verify,
            context_fingerprint="browser-mechanics",
        )

        assert source == "MODEL_FALLBACK"
        assert teach.recipes.lookups == 1
        assert fallback.calls
        assert teach.lessons
        assert verify() is True
        assert page.locator("body").get_attribute("data-submitted") is None

        sent = fallback.calls[0]
        sent_text = repr(sent)
        assert "United States" not in sent_text
        assert "PDF-1.4" not in sent_text
        assert "answer:country" in sent_text
        assert "artifact:resume" in sent_text

        with pytest.raises(TrustedMechanicsError):
            executor.execute(
                [{"type": "CLICK", "targetRef": final_target["targetRef"]}],
                allowed_value_refs=set(),
            )

        browser.close()
