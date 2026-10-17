"""Provider-neutral resume / cover-letter uploader.

Strategy ladder:
1. native file inputs, including hidden controls;
2. buttons/labels that open a browser file chooser;
3. drag/drop surfaces using DataTransfer + File.

Ambiguous multiple targets fail closed.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

_RESUME_RE = re.compile(r"\b(resume|curriculum\s+vitae|cv)\b", re.I)
_COVER_RE = re.compile(r"\bcover[\s_-]*letter\b", re.I)
_UPLOAD_RE = re.compile(
    r"\b(upload|attach|attachment|browse|choose\s+file|select\s+file|"
    r"drop\s+file|drag\s*(?:and|&)\s*drop|document|file)\b",
    re.I,
)


@dataclass(frozen=True)
class DocumentSpec:
    role: str
    filename: str
    mime_type: str
    sha256: str
    data: bytes

    def validated(self) -> "DocumentSpec":
        actual = hashlib.sha256(self.data).hexdigest()
        expected = str(self.sha256 or "").strip().lower()
        if actual != expected:
            raise ValueError(f"{self.role} artifact digest mismatch")
        if not self.filename:
            raise ValueError(f"{self.role} filename is missing")
        if not self.mime_type:
            raise ValueError(f"{self.role} MIME type is missing")
        return self

    def playwright_payload(self) -> dict[str, Any]:
        return {
            "name": self.filename,
            "mimeType": self.mime_type,
            "buffer": self.data,
        }


def classify_upload_identity(identity: str) -> str:
    text = " ".join(str(identity or "").split())
    if _COVER_RE.search(text):
        return "cover_letter"
    if _RESUME_RE.search(text):
        return "resume"
    if _UPLOAD_RE.search(text):
        return "generic"
    return "unknown"


class UniversalDocumentUploader:
    def __init__(
        self,
        page: Any,
        *,
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.page = page
        self.on_event = on_event or (lambda _kind, _evidence: None)

    @staticmethod
    def _frame_key(frame: Any) -> str:
        return str(getattr(frame, "url", "") or "")[:500]

    @staticmethod
    def _element_meta(locator: Any) -> dict[str, Any]:
        return dict(
            locator.evaluate(
                r"""element => {
                  const compact = value => String(value || '')
                    .replace(/\s+/g, ' ').trim().slice(0, 500);
                  const labelText = element.labels
                    ? Array.from(element.labels).map(label => compact(label.innerText)).join(' ')
                    : '';
                  const container = element.closest(
                    'label,fieldset,section,[role="group"],[role="region"],div'
                  );
                  const context = compact(container && container.innerText);
                  const text = compact(
                    element.innerText
                    || element.value
                    || element.getAttribute('aria-label')
                    || element.getAttribute('title')
                  );
                  return {
                    id: compact(element.id),
                    name: compact(element.getAttribute('name')),
                    accept: compact(element.getAttribute('accept')),
                    ariaLabel: compact(element.getAttribute('aria-label')),
                    title: compact(element.getAttribute('title')),
                    label: compact(labelText),
                    text,
                    context,
                    className: compact(element.className),
                    multiple: Boolean(element.multiple),
                  };
                }""",
            )
        )

    @staticmethod
    def _identity(meta: dict[str, Any]) -> str:
        return " ".join(
            str(meta.get(key) or "")
            for key in (
                "id",
                "name",
                "ariaLabel",
                "title",
                "label",
                "text",
                "context",
                "className",
                "accept",
            )
        )

    def _native_targets(self) -> list[dict[str, Any]]:
        targets: list[dict[str, Any]] = []
        for frame in list(self.page.frames):
            locator = frame.locator('input[type="file"]')
            for index in range(min(locator.count(), 50)):
                item = locator.nth(index)
                try:
                    meta = self._element_meta(item)
                except Exception:  # noqa: S112
                    continue
                targets.append(
                    {
                        "kind": "native",
                        "frame_url": self._frame_key(frame),
                        "locator": item,
                        "meta": meta,
                        "role": classify_upload_identity(self._identity(meta)),
                    }
                )
        return targets

    def _proxy_targets(self) -> list[dict[str, Any]]:
        selector = (
            'button,[role="button"],label,[role="region"],'
            '[data-testid*="upload" i],[data-automation-id*="upload" i],'
            '[class*="upload" i],[class*="dropzone" i],[class*="drop-zone" i],'
            '[class*="file-drop" i]'
        )
        targets: list[dict[str, Any]] = []
        for frame in list(self.page.frames):
            locator = frame.locator(selector)
            for index in range(min(locator.count(), 100)):
                item = locator.nth(index)
                try:
                    if not item.is_visible():
                        continue
                    meta = self._element_meta(item)
                except Exception:  # noqa: S112
                    continue
                role = classify_upload_identity(self._identity(meta))
                if role == "unknown":
                    continue
                targets.append(
                    {
                        "kind": "proxy",
                        "frame_url": self._frame_key(frame),
                        "locator": item,
                        "meta": meta,
                        "role": role,
                    }
                )
        return targets

    @staticmethod
    def _candidate_for_role(
        targets: list[dict[str, Any]],
        *,
        role: str,
        allow_generic_single: bool,
    ) -> dict[str, Any] | None:
        explicit = [target for target in targets if target["role"] == role]
        if len(explicit) == 1:
            return explicit[0]
        if len(explicit) > 1:
            return None
        if allow_generic_single:
            generic = [target for target in targets if target["role"] == "generic"]
            non_cover = [target for target in targets if target["role"] != "cover_letter"]
            if len(non_cover) == 1 and non_cover[0]["role"] in {"generic", "unknown"}:
                return non_cover[0]
            if len(generic) == 1 and len(targets) == 1:
                return generic[0]
        return None

    @staticmethod
    def _file_hashes(locator: Any) -> list[str]:
        # Hash actual browser File bytes without requiring crypto.subtle.
        # FileReader also works in valid non-secure/about:blank contexts.
        values = locator.evaluate(
            r"""async element => {
              if (!element.files) return [];
              const read = file => new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => resolve(String(reader.result || ''));
                reader.onerror = () => reject(
                  reader.error || new Error('file_read_failed')
                );
                reader.readAsDataURL(file);
              });
              return await Promise.all(Array.from(element.files).map(read));
            }""",
        )
        hashes: list[str] = []
        for value in values or []:
            data_url = str(value or "")
            if "," not in data_url:
                continue
            _header, encoded = data_url.split(",", 1)
            data = None
            try:
                data = base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError):
                data = None
            if data is None:
                continue
            hashes.append(hashlib.sha256(data).hexdigest())
        return hashes

    def _begin_capture(self) -> str:
        """Retain actual browser File objects before a reactive widget detaches.

        FileReader data is never persisted or logged. This is not proof the
        employer server accepted the upload; it proves the browser held bytes.
        """
        probe = secrets.token_hex(12)
        for frame in list(self.page.frames):
            try:
                frame.evaluate(
                    r"""probe => {
                      const store = window.__munshiEphemeralUploadProof
                        || (window.__munshiEphemeralUploadProof = {});
                      const files = [];
                      const onChange = event => {
                        if (event.target && event.target.files) {
                          files.push(...Array.from(event.target.files));
                        }
                      };
                      const onDrop = event => {
                        if (event.dataTransfer && event.dataTransfer.files) {
                          files.push(...Array.from(event.dataTransfer.files));
                        }
                      };
                      document.addEventListener('change', onChange, true);
                      document.addEventListener('drop', onDrop, true);
                      store[probe] = {files, onChange, onDrop};
                    }""",
                    probe,
                )
            except Exception:  # noqa: S112 - cross-origin or detached frame
                continue
        return probe

    def _captured_hashes(self, probe: str) -> set[str]:
        hashes: set[str] = set()
        for frame in list(self.page.frames):
            try:
                values = frame.evaluate(
                    r"""async probe => {
                      const entry = window.__munshiEphemeralUploadProof?.[probe];
                      if (!entry) return [];
                      return Promise.all(entry.files.map(file => new Promise(
                        (resolve, reject) => {
                          const reader = new FileReader();
                          reader.onload = () => resolve(String(reader.result || ''));
                          reader.onerror = () => reject(reader.error);
                          reader.readAsDataURL(file);
                        }
                      )));
                    }""",
                    probe,
                )
                for raw in values or []:
                    encoded = str(raw or "").split(",", 1)
                    if len(encoded) == 2:
                        data = base64.b64decode(encoded[1], validate=True)
                        hashes.add(hashlib.sha256(data).hexdigest())
            except Exception:  # noqa: S112 - do not claim unverifiable bytes
                continue
        return hashes

    def _end_capture(self, probe: str) -> None:
        for frame in list(self.page.frames):
            try:
                frame.evaluate(
                    r"""probe => {
                      const entry = window.__munshiEphemeralUploadProof?.[probe];
                      if (!entry) return;
                      document.removeEventListener('change', entry.onChange, true);
                      document.removeEventListener('drop', entry.onDrop, true);
                      delete window.__munshiEphemeralUploadProof[probe];
                    }""",
                    probe,
                )
            except Exception:  # noqa: S112 - cleanup best effort
                continue

    def _verify_hash_any_native(self, expected_sha256: str) -> bool:
        expected = str(expected_sha256 or "").strip().lower()
        for target in self._native_targets():
            try:
                if expected in self._file_hashes(target["locator"]):
                    return True
            except Exception:  # noqa: S112
                continue
        return False

    def _wait_for_acknowledgement(
        self, spec: DocumentSpec, *, probe: str, ack_preexisting: bool
    ) -> bool:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            # A filename alone is not cryptographic upload proof.
            if self._verify_hash_any_native(spec.sha256):
                return True
            if (
                spec.sha256.lower() in self._captured_hashes(probe)
                and not ack_preexisting
                and self._filename_acknowledged(filename=spec.filename)
            ):
                return True
            self.page.wait_for_timeout(100)
        return False

    def _filename_acknowledged(self, *, filename: str) -> bool:
        wanted = str(filename or "").strip()
        if not wanted:
            return False
        for frame in list(self.page.frames):
            try:
                if frame.evaluate(
                    r"""filename => {
                      const compact = value => String(value || '')
                        .replace(/\s+/g, ' ').trim();
                      const wanted = compact(filename);
                      if (!wanted) return false;
                      const candidates = Array.from(document.querySelectorAll(
                        '[role="status"],[aria-live],li,span,div,p'
                      )).slice(0, 2500);
                      return candidates.some(element => {
                        const text = compact(element.innerText || element.textContent);
                        return text === wanted || text.includes(wanted);
                      });
                    }""",
                    wanted,
                ):
                    return True
            except Exception:  # noqa: S112
                continue
        return False

    def _native_upload(
        self,
        *,
        target: dict[str, Any],
        specs: list[DocumentSpec],
    ) -> dict[str, str]:
        locator = target["locator"]
        payloads = [spec.playwright_payload() for spec in specs]
        acknowledgements_before = {
            spec.role: self._filename_acknowledged(filename=spec.filename)
            for spec in specs
        }
        probe = self._begin_capture()
        try:
            locator.set_input_files(payloads if len(payloads) > 1 else payloads[0])
            verified: dict[str, str] = {}
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                native: set[str] = set()
                try:
                    native.update(self._file_hashes(locator))
                except Exception:  # noqa: S112 - React may detach its file input
                    pass
                captured = self._captured_hashes(probe)
                for spec in specs:
                    expected = spec.sha256.lower()
                    if expected in native or (
                        expected in captured
                        and not acknowledgements_before[spec.role]
                        and self._filename_acknowledged(filename=spec.filename)
                    ):
                        verified[spec.role] = expected
                if len(verified) == len(specs):
                    break
                self.page.wait_for_timeout(100)
            if verified:
                self.on_event(
                    "DOCUMENT_UPLOAD_VERIFIED",
                    {
                        "strategy": "native_file_input",
                        "roles": sorted(verified),
                        "frame_url": target["frame_url"],
                    },
                )
            return verified
        finally:
            self._end_capture(probe)

    def _filechooser_upload(
        self,
        *,
        target: dict[str, Any],
        spec: DocumentSpec,
    ) -> bool:
        ack_preexisting = self._filename_acknowledged(filename=spec.filename)
        probe = self._begin_capture()
        try:
            try:
                with self.page.expect_file_chooser(timeout=1500) as chooser_info:
                    target["locator"].click(timeout=1500)
                chooser_info.value.set_files(spec.playwright_payload())
            except Exception:
                return False
            if not self._wait_for_acknowledgement(
                spec, probe=probe, ack_preexisting=ack_preexisting
            ):
                return False
            self.on_event(
                "DOCUMENT_UPLOAD_VERIFIED",
                {
                    "strategy": "file_chooser",
                    "roles": [spec.role],
                    "frame_url": target["frame_url"],
                },
            )
            return True
        finally:
            self._end_capture(probe)

    def _drop_upload(
        self,
        *,
        target: dict[str, Any],
        spec: DocumentSpec,
    ) -> bool:
        ack_preexisting = self._filename_acknowledged(filename=spec.filename)
        probe = self._begin_capture()
        encoded = base64.b64encode(spec.data).decode("ascii")
        try:
            delivered = target["locator"].evaluate(
                r"""(element, payload) => {
                  const binary = atob(payload.base64);
                  const bytes = new Uint8Array(binary.length);
                  for (let index = 0; index < binary.length; index += 1) {
                    bytes[index] = binary.charCodeAt(index);
                  }
                  const file = new File(
                    [bytes], payload.filename, { type: payload.mimeType }
                  );
                  const transfer = new DataTransfer();
                  transfer.items.add(file);
                  for (const type of ['dragenter', 'dragover', 'drop']) {
                    element.dispatchEvent(new DragEvent(type, {
                      bubbles: true,
                      cancelable: true,
                      dataTransfer: transfer,
                    }));
                  }
                  return true;
                }""",
                {
                    "base64": encoded,
                    "filename": spec.filename,
                    "mimeType": spec.mime_type,
                },
            )
        except Exception:
            self._end_capture(probe)
            return False
        if delivered is not True:
            self._end_capture(probe)
            return False
        if not self._wait_for_acknowledgement(
            spec, probe=probe, ack_preexisting=ack_preexisting
        ):
            self._end_capture(probe)
            return False
        self.on_event(
            "DOCUMENT_UPLOAD_VERIFIED",
            {
                "strategy": "drag_drop",
                "roles": [spec.role],
                "frame_url": target["frame_url"],
            },
        )
        return True

    def upload(
        self,
        *,
        resume: DocumentSpec | None,
        cover_letter: DocumentSpec | None,
    ) -> dict[str, str]:
        verified: dict[str, str] = {}
        resume = resume.validated() if resume is not None else None
        cover_letter = cover_letter.validated() if cover_letter is not None else None

        native = self._native_targets()

        generic_multi = [
            target
            for target in native
            if target["role"] == "generic" and bool(target["meta"].get("multiple"))
        ]
        if (
            resume is not None
            and cover_letter is not None
            and len(native) == 1
            and len(generic_multi) == 1
        ):
            verified.update(
                self._native_upload(
                    target=generic_multi[0],
                    specs=[resume, cover_letter],
                )
            )
            if {"resume", "cover_letter"} <= set(verified):
                return verified

        if resume is not None and "resume" not in verified:
            target = self._candidate_for_role(
                native, role="resume", allow_generic_single=True
            )
            if target is not None:
                verified.update(self._native_upload(target=target, specs=[resume]))

        if cover_letter is not None and "cover_letter" not in verified:
            target = self._candidate_for_role(
                native, role="cover_letter", allow_generic_single=False
            )
            if target is not None:
                verified.update(self._native_upload(target=target, specs=[cover_letter]))

        proxy = self._proxy_targets()

        if resume is not None and "resume" not in verified:
            target = self._candidate_for_role(
                proxy, role="resume", allow_generic_single=True
            )
            if target is not None and (
                self._filechooser_upload(target=target, spec=resume)
                or self._drop_upload(target=target, spec=resume)
            ):
                verified["resume"] = resume.sha256.lower()

        if cover_letter is not None and "cover_letter" not in verified:
            target = self._candidate_for_role(
                proxy, role="cover_letter", allow_generic_single=False
            )
            if target is not None and (
                self._filechooser_upload(target=target, spec=cover_letter)
                or self._drop_upload(target=target, spec=cover_letter)
            ):
                verified["cover_letter"] = cover_letter.sha256.lower()

        for spec in (resume, cover_letter):
            if spec is None or spec.role in verified:
                continue
            available_roles = [target["role"] for target in native + proxy]
            reason = (
                "UPLOAD_CONTROL_NOT_FOUND"
                if not available_roles
                else "UPLOAD_CONTROL_AMBIGUOUS"
                if available_roles.count(spec.role) > 1
                else "UPLOAD_WIDGET_UNVERIFIED"
            )
            self.on_event(
                "DOCUMENT_UPLOAD_UNVERIFIED",
                {
                    "role": spec.role,
                    "reason": reason,
                    "native_input_count": len(native),
                    "proxy_count": len(proxy),
                },
            )
        return verified
