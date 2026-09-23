# Repository maintenance contract

This file governs work on this repository. It does not duplicate the production method.

- The canonical execution entry is `skills/newsletter-production/SKILL.md`; its directly linked references own the detailed method and Gate contract.
- `README.md` and `docs/` are reader-facing guides. Keep them consistent with the canonical files, but do not create a second set of mutable rules in them.
- Keep the repository source-agnostic. Examples must be fictional and must not depend on a private platform, account, author, or unpublished source.
- Keep credentials in environment variables. Never commit keys, tokens, cookies, private source data, drafts, receipts, or local run state.
- After changing contracts or scripts, run `python -m unittest discover -s tests -v`, validate `examples/starter/`, and dry-run the affected JEV payloads.
- A local test, dry-run, or Gate pass does not prove author approval, publication, delivery, or production behavior.
