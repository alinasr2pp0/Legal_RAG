# Data quality: what was wrong with the PDF and how it is handled

Everything below was found by inspecting the real extraction, not assumed.

| Defect | Effect | Handling |
|---|---|---|
| Parser v1 keyed on the English "Article N" heading; on some pages that heading precedes the Arabic text | ~65 of 1,143 articles had wrong / split / truncated text (e.g. text of 203 stored under 204); 6 articles missing; 13 empty | **Parser v2** segments by the monotone chain of Arabic "مادة N" markers (digits are extracted reversed: "٠٢١" = 120) |
| Lam-alef ligature extracted as "ال" | "الالتزام" → "االلتزام"; the negation "لا" → "ال" ("ال يجوز") | `rag/ingestion/pdf_repair.py` (rules + small verified dictionary) and a lam-alef fold in the BM25 key |
| Multi-digit numbers extracted reversed | "المادة 362" is really 263; "سنة 3881" = 1883 | `pdf_repair.fix_reversed_numbers` (with a guard for impossible article numbers) |
| Chapter titles glued to the previous article | titles polluted article text | removed from the text, kept as `chapter` metadata and prefixed to the chunk as a contextual header |
| Repealed ranges | would be silently lost | flagged `is_repealed=true`, never deleted; announcement text kept |
| Article 1022 | Arabic paragraph (1) is absent from the source PDF | see the data audit below (relocation from 1021, `text_incomplete`); needs an official Arabic edition |

Known leftovers: rare words with "لا/ال" in the middle of the word may stay damaged in the displayed text
(BM25 is immune through the fold; the audit found and fixed "إسلام"), and a stray "ا" ends paragraph (1) of
Article 1. No automatic scan can prove the text is free of such artifacts.

Regenerate: `dvc repro && python scripts/data/export_serving_data.py`.

## Data audit (2026-10) — defects found and how they are guarded

| Defect | Fix | Guard |
|---|---|---|
| English page-break continuation parsed as the next article (651/652/1091/1092) | `_merge_page_continuations` | `test_page_continuations_652_651` |
| 13 articles lost the Arabic "مادة N" marker (e.g. "ما دة 652") | tolerant marker regex + per-run digit reversal (601) | `test_no_marker_fragments_or_stray_latin` |
| Date reversed in Article 54 | `_flip_date` | `test_article_54_date_not_reversed` |
| Stray English tail inside the Arabic text (854, 913) | moved to the English side | same test |
| Paragraph numbers garbled by bidi (`)1 (`, `(1 (`) | `normalizer._PARA_NUMBER_RE` | `test_paragraph_numbers_normalised` |
| "العقار" extracted as "العاقر" in Articles 1021-1065 | `pdf_repair._fix_aqar` | `test_aqar_font_swap_repaired` |
| Article 1021/1022 blocks swapped, 1022 Arabic paragraph (1) absent from PDF | `source_corrections.py` (provenance JSON) + `text_incomplete` flag → chunk marker, API field, answer caveat | `test_1021_1022_relocation_and_incomplete_flag` |

`data/serving/MANIFEST.json` records the sha256 of the served corpus and the source PDF; the index
manifest (`data/processed/index_manifest.json`) ties the vector index to that hash + embedding model,
and `/ready` fails when they disagree. **Legal correctness of any article still needs a lawyer's
check against the official gazette** (`data/interim/needs_manual_review.txt`).
