# Review provenance

What the corpus and its fixes are based on, so a reviewer can retrace them.

| Item | Value |
|---|---|
| Source PDF | bilingual Egyptian Civil Code (Arabic / English columns), 170 pages |
| Source SHA-256 | `2d6419fb262dab712f7bf5f6e31834bea74fbcf03b78ae081dd35d156915eebf` |
| Articles / chunks | 1149 / 1150 (56 repealed) — `data/serving/MANIFEST.json` |
| Serving bundle | `data/serving/chunks.json`; its SHA-256 is recorded in the manifest and checked by `/ready` |
| Applied source corrections | `data/interim/source_corrections_applied.json` (Articles 1021/1022) |
| Items needing a person | `docs/corpus-review-checklist.md` (random sample, regenerate with `scripts/data/make_review_checklist.py`) |

## Rules

- `source_page` / `page_number` is the physical page of the supplied PDF. The stable citation for users is the article number.
- Every automatic fix is listed in `docs/data-quality.md`; a fix that changes legal text placement (1021/1022) is flagged `needs_review` and must be confirmed by a lawyer against an official Arabic edition.
- Nothing in the checklist is pre-approved. Approve a corpus version only after the human checks, and record its `chunks_sha256`.
