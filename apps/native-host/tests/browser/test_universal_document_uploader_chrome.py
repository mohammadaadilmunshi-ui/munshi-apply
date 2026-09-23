from __future__ import annotations

import hashlib
import os

import pytest

from munshi_apply_native.browser_runtime import resolve_browser_executable
from munshi_apply_native.universal_document_uploader import (
    DocumentSpec,
    UniversalDocumentUploader,
)

pytestmark = pytest.mark.skipif(
    os.getenv("MUNSHI_RUN_BROWSER_TESTS") != "1",
    reason="real browser integration lane is opt-in",
)

RESUME_BYTES = b"%PDF-1.4\nresume\n%%EOF\n"
COVER_BYTES = b"%PDF-1.4\ncover\n%%EOF\n"
RESUME_SHA = hashlib.sha256(RESUME_BYTES).hexdigest()
COVER_SHA = hashlib.sha256(COVER_BYTES).hexdigest()


def _resume():
    return DocumentSpec(
        role="resume",
        filename="resume.pdf",
        mime_type="application/pdf",
        sha256=RESUME_SHA,
        data=RESUME_BYTES,
    )


def _cover():
    return DocumentSpec(
        role="cover_letter",
        filename="cover_letter.pdf",
        mime_type="application/pdf",
        sha256=COVER_SHA,
        data=COVER_BYTES,
    )


def _browser():
    playwright = pytest.importorskip("playwright.sync_api")
    pw = playwright.sync_playwright().start()
    browser = pw.chromium.launch(
        headless=True,
        executable_path=resolve_browser_executable(),
    )
    return pw, browser


def test_hidden_native_resume_input_uploads_and_hash_verifies():
    pw, browser = _browser()
    try:
        page = browser.new_page()
        page.set_content(
            """
            <label for="resume">Resume / CV</label>
            <input id="resume" name="resume" type="file" hidden>
            """
        )
        uploader = UniversalDocumentUploader(page)
        result = uploader.upload(resume=_resume(), cover_letter=None)
        assert result["resume"] == RESUME_SHA
        count = page.locator("#resume").evaluate(
            "el => el.files ? el.files.length : 0"
        )
        assert count == 1
    finally:
        browser.close()
        pw.stop()


def test_single_generic_native_slot_accepts_resume_even_when_cover_exists():
    pw, browser = _browser()
    try:
        page = browser.new_page()
        page.set_content(
            """
            <label for="attachment">Upload document</label>
            <input id="attachment" name="attachment" type="file">
            """
        )
        uploader = UniversalDocumentUploader(page)
        result = uploader.upload(resume=_resume(), cover_letter=_cover())
        assert result["resume"] == RESUME_SHA
        assert "cover_letter" not in result
    finally:
        browser.close()
        pw.stop()


def test_generic_multiple_bucket_accepts_resume_and_cover_letter():
    pw, browser = _browser()
    try:
        page = browser.new_page()
        page.set_content(
            """
            <label for="docs">Upload documents</label>
            <input id="docs" name="docs" type="file" multiple>
            """
        )
        uploader = UniversalDocumentUploader(page)
        result = uploader.upload(resume=_resume(), cover_letter=_cover())
        assert result["resume"] == RESUME_SHA
        assert result["cover_letter"] == COVER_SHA
        count = page.locator("#docs").evaluate(
            "el => el.files ? el.files.length : 0"
        )
        assert count == 2
    finally:
        browser.close()
        pw.stop()


def test_explicit_cover_letter_and_resume_slots_are_kept_separate():
    pw, browser = _browser()
    try:
        page = browser.new_page()
        page.set_content(
            """
            <label for="r">Resume</label>
            <input id="r" name="resume" type="file">
            <label for="c">Cover Letter</label>
            <input id="c" name="cover_letter" type="file">
            """
        )
        uploader = UniversalDocumentUploader(page)
        result = uploader.upload(resume=_resume(), cover_letter=_cover())
        assert result["resume"] == RESUME_SHA
        assert result["cover_letter"] == COVER_SHA
    finally:
        browser.close()
        pw.stop()


def test_file_chooser_button_path():
    pw, browser = _browser()
    try:
        page = browser.new_page()
        page.set_content(
            """
            <input id="hidden-file" type="file" style="display:none">
            <button id="upload-resume">Upload Resume</button>
            <div id="status"></div>
            <script>
              const input = document.querySelector('#hidden-file');
              const button = document.querySelector('#upload-resume');
              const status = document.querySelector('#status');
              button.addEventListener('click', () => input.click());
              input.addEventListener('change', () => {
                status.textContent = input.files[0] ? input.files[0].name : '';
              });
            </script>
            """
        )
        uploader = UniversalDocumentUploader(page)
        proxies = uploader._proxy_targets()
        target = next(item for item in proxies if item["role"] == "resume")
        assert uploader._filechooser_upload(target=target, spec=_resume()) is True
    finally:
        browser.close()
        pw.stop()


def test_drag_drop_zone_path():
    pw, browser = _browser()
    try:
        page = browser.new_page()
        page.set_content(
            """
            <div id="resume-drop" class="dropzone" role="region">
              Drag and drop resume here
            </div>
            <div id="status"></div>
            <script>
              const zone = document.querySelector('#resume-drop');
              const status = document.querySelector('#status');
              zone.addEventListener('dragover', e => e.preventDefault());
              zone.addEventListener('drop', e => {
                e.preventDefault();
                const file = e.dataTransfer.files[0];
                status.textContent = file ? file.name : '';
              });
            </script>
            """
        )
        uploader = UniversalDocumentUploader(page)
        proxies = uploader._proxy_targets()
        target = next(item for item in proxies if item["role"] == "resume")
        assert uploader._drop_upload(target=target, spec=_resume()) is True
    finally:
        browser.close()
        pw.stop()


def test_iframe_native_file_input_is_found():
    pw, browser = _browser()
    try:
        page = browser.new_page()
        page.set_content(
            """
            <iframe id="f"></iframe>
            <script>
              const frame = document.querySelector('#f');
              frame.srcdoc = (
                '<label for="r">Resume</label>'
                + '<input id="r" name="resume" type="file">'
              );
            </script>
            """
        )
        page.wait_for_timeout(250)
        uploader = UniversalDocumentUploader(page)
        result = uploader.upload(resume=_resume(), cover_letter=None)
        assert result["resume"] == RESUME_SHA
    finally:
        browser.close()
        pw.stop()


def test_open_shadow_dom_file_input_is_found():
    pw, browser = _browser()
    try:
        page = browser.new_page()
        page.set_content(
            """
            <resume-upload></resume-upload>
            <script>
              customElements.define('resume-upload', class extends HTMLElement {
                connectedCallback() {
                  const root = this.attachShadow({mode:'open'});
                  root.innerHTML = (
                    '<label for="r">Resume</label>'
                    + '<input id="r" name="resume" type="file">'
                  );
                }
              });
            </script>
            """
        )
        page.wait_for_timeout(100)
        uploader = UniversalDocumentUploader(page)
        result = uploader.upload(resume=_resume(), cover_letter=None)
        assert result["resume"] == RESUME_SHA
    finally:
        browser.close()
        pw.stop()


def test_multiple_ambiguous_single_file_targets_fail_closed():
    pw, browser = _browser()
    try:
        page = browser.new_page()
        page.set_content(
            """
            <label>Upload file <input name="a" type="file"></label>
            <label>Upload file <input name="b" type="file"></label>
            """
        )
        uploader = UniversalDocumentUploader(page)
        result = uploader.upload(resume=_resume(), cover_letter=None)
        assert "resume" not in result
    finally:
        browser.close()
        pw.stop()
