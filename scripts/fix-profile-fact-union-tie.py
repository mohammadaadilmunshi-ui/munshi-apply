from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text()
    if old not in text:
        raise SystemExit(f"tie-break anchor missing in {path}")
    file.write_text(text.replace(old, new, 1))


replace_once(
    "apps/extension/src/storage/profile-sync.ts",
    '''    const choice = protectedFact\n      ? chooseProtectedFact(baseFact, localFact, remoteFact)\n      : (laterFact(localFact, remoteFact) ?? baseFact);''',
    '''    const ordinaryChoice =\n      !localFact\n        ? (remoteFact ?? baseFact)\n        : !remoteFact\n          ? localFact\n          : localFact.updatedAt > remoteFact.updatedAt\n            ? localFact\n            : remoteFact.updatedAt > localFact.updatedAt\n              ? remoteFact\n              : (baseFact ?? localFact);\n    const choice = protectedFact\n      ? chooseProtectedFact(baseFact, localFact, remoteFact)\n      : ordinaryChoice;''',
)

replace_once(
    "apps/owner-workspace/app/vault-client.ts",
    '''    if (!protectedFact) {\n      const choice = laterFact(localFact, remoteFact) ?? baseFact;\n      if (choice) selected.set(key, choice);\n      continue;\n    }''',
    '''    if (!protectedFact) {\n      const choice =\n        !localFact\n          ? (remoteFact ?? baseFact)\n          : !remoteFact\n            ? localFact\n            : localFact.updatedAt > remoteFact.updatedAt\n              ? localFact\n              : remoteFact.updatedAt > localFact.updatedAt\n                ? remoteFact\n                : (baseFact ?? localFact);\n      if (choice) selected.set(key, choice);\n      continue;\n    }''',
)
