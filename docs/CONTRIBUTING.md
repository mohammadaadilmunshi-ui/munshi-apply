# Contributing

## Change discipline

Keep changes bounded to one milestone. Add or update tests for every contract, scanner, state, migration, and security-policy change. New permissions require a written justification in `docs/SECURITY.md` and an ADR.

## Local gate

```bash
npm run check
python -m ruff check apps/native-host
python -m pytest apps/native-host
```

## Data safety

Use only synthetic job, résumé, profile, and application data in tests. Never commit personal facts, real application URLs containing tokens, cookies, credentials, API keys, résumés, database files, or diagnostic captures from real employer sites.

## Contracts

Schema changes require backward-compatibility analysis. SQLite changes require a new numbered migration; never edit a migration that has already shipped.
