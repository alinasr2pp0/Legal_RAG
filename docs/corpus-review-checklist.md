# Corpus Visual Review Checklist

Status: **pending human review.** The table is a reproducible random sample (seed `20261018`) of
20 non-repealed articles. Nothing is pre-approved: compare the Arabic and English text against
the indicated PDF pages (including continuation pages).

Source PDF SHA-256: `2d6419fb262dab712f7bf5f6e31834bea74fbcf03b78ae081dd35d156915eebf`.
Regenerate: `python scripts/data/make_review_checklist.py`.

| Article | PDF page | Text and boundaries | Hierarchy / citation | Reviewer notes |
|---|---|---|---|---|
| 128 | 14 | [ ] | [ ] | |
| 142 | 16 | [ ] | [ ] | |
| 158 | 18 | [ ] | [ ] | |
| 183 | 22 | [ ] | [ ] | |
| 255 | 32 | [ ] | [ ] | |
| 264 | 34 | [ ] | [ ] | |
| 286 | 37 | [ ] | [ ] | |
| 437 | 56 | [ ] | [ ] | |
| 468 | 61 | [ ] | [ ] | |
| 491 | 63 | [ ] | [ ] | |
| 509 | 66 | [ ] | [ ] | |
| 512 | 67 | [ ] | [ ] | |
| 547 | 73 | [ ] | [ ] | |
| 581 | 78 | [ ] | [ ] | |
| 615 | 83 | [ ] | [ ] | |
| 731 | 103 | [ ] | [ ] | |
| 993 | 143 | [ ] | [ ] | |
| 1083 | 158 | [ ] | [ ] | |
| 1085 | 158 | [ ] | [ ] | |
| 1097 | 161 | [ ] | [ ] | |

## Additional checks

- [ ] Articles flagged `text_missing`: none are refused by the service; confirm against the PDF.
- [ ] Articles flagged `text_incomplete`: [1022]; fill the missing Arabic paragraph from an
      official edition. Do not move adjacent text without legal review (see `docs/data-quality.md`).
- [ ] Article 1021/1022 relocation (`data/interim/source_corrections_applied.json`) confirmed by a lawyer.
- [ ] Spot-check restored Arabic numerals and lam-alef words (for example "إسلام") against the PDF.
- [ ] Repealed ranges match the PDF's explicit repeal notes.
- [ ] Approve a corpus version (record the `chunks_sha256` from `data/serving/MANIFEST.json`) before indexing.

Reviewer: ______  Date: ______  Decision: ______
