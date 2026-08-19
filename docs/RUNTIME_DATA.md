# Private runtime data

Source code and private runtime data are separate trust zones. On macOS the default runtime root is:

```text
~/Library/Application Support/MUNSHI Apply/
```

```text
MUNSHI Apply/
├── database/
├── resumes/
│   ├── master/
│   ├── tailored/
│   └── submitted/
├── evidence/
├── embeddings/
├── learning/
├── exports/
├── logs/
├── diagnostics/
├── backups/
├── secrets/
├── settings/
└── releases/
```

SQLite in `database/munshi-apply.sqlite` is authoritative. IndexedDB is a browser cache for active sessions, page snapshots, temporary state, and responsive UI rendering.

Operational commands:

```bash
./scripts/install.sh --extension-id <EDGE_EXTENSION_ID>
./scripts/verify.sh --extension-id <EDGE_EXTENSION_ID>
./scripts/backup.sh
./scripts/update.sh --extension-id <EDGE_EXTENSION_ID>
./scripts/rollback.sh <version> --extension-id <EDGE_EXTENSION_ID>
```

Backups use SQLite's online backup API and include metadata/settings JSON or TOML plus a manifest and SHA-256 checksums. Rollback activates a versioned code copy and preserves the current database and application history; it does not perform destructive down-migrations.

`MUNSHI_RUNTIME_ROOT` can relocate the entire private runtime. `MUNSHI_DATABASE_PATH` can relocate only the database. Neither should point inside the Git worktree.
