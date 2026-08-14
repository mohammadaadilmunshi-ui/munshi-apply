from pathlib import Path

path = Path("apps/extension/src/sidepanel/App.tsx")
text = path.read_text(encoding="utf-8")

import_line = 'import { resolveProfileAnswer } from "@munshi-apply/application-model";\n'
if import_line not in text:
    anchor = '} from "@munshi-apply/contracts";\n'
    index = text.find(anchor)
    if index == -1:
        raise SystemExit("contracts import anchor not found")
    insert_at = index + len(anchor)
    text = text[:insert_at] + import_line + text[insert_at:]

start = text.find('const semanticFactKey: Readonly<Record<string, string>> = {')
if start != -1:
    end_marker = '\n\nconst defaultAISettings: AISettings = {'
    end = text.find(end_marker, start)
    if end == -1:
        raise SystemExit("semanticFactKey end marker not found")
    text = text[:start] + text[end + 2 :]

old = '''      const approved = review?.answers.find((answer) => answer.questionId === question.questionId);
      const factKey = semanticFactKey[question.semanticType];
      const fact = factKey ? profile.facts.find((candidate) => candidate.key === factKey) : undefined;
      const suggested = fact && fact.trustLevel !== "UNKNOWN" && factKey ? valueOf(profile, factKey) : "";
      return [question.questionId, approved ?? { value: suggested, approved: Boolean(suggested) && !question.sensitive, sensitive: question.sensitive }];
'''
new = '''      const approved = review?.answers.find((answer) => answer.questionId === question.questionId);
      const resolution = resolveProfileAnswer(question, profile);
      const suggested = resolution.value ?? "";
      return [
        question.questionId,
        approved ?? {
          value: suggested,
          approved: resolution.state === "READY",
          sensitive: resolution.sensitive,
        },
      ];
'''
if old in text:
    text = text.replace(old, new, 1)
elif 'const resolution = resolveProfileAnswer(question, profile);' not in text:
    raise SystemExit("answer suggestion block not found")

path.write_text(text, encoding="utf-8")
