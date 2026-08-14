# Data classification

| Class        | Examples                                                                | Default handling                                     |
| ------------ | ----------------------------------------------------------------------- | ---------------------------------------------------- |
| Public       | Product documentation, synthetic fixtures, release notes                | May be committed                                     |
| Internal     | Application state, diagnostics without personal values                  | Local only unless sanitized                          |
| Confidential | Résumés, employment evidence, application answers, job ledger           | Local encrypted storage; never fixtures              |
| Restricted   | Credentials, API keys, cookies, sessions, voluntary demographic answers | Credential store or protected vault; always redacted |

## Repository rule

Only public synthetic data belongs in Git. Personal profile exports, real résumés, application snapshots, SQLite files, backups, and generated diagnostics are ignored by default.

## Logging rule

Logs may include identifiers, event types, counts, component fingerprints, and verification outcomes. They must not include raw secrets, password fields, authentication tokens, cookies, or protected demographic values.
