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

                sensitivity = str(
                    question.get("sensitivityClass")
                    or question.get("sensitivity_class")
                    or ("PROTECTED" if question.get("sensitive") else "NORMAL")
                ).upper()
                protected_lane = bool(question.get("sensitive")) or sensitivity in {
                    "PROTECTED",
                    "SELF_ID",
                }

                if protected_lane:
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
