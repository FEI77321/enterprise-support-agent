# Enterprise Support Agent Synthetic Corpus v1

## Purpose

This corpus is deliberately fictional. It exists to test document ingestion, structure-aware chunking, version handling, source traceability, table extraction, and OCR fallback without using confidential or copyrighted enterprise material.

Do not describe these files as real enterprise documents in a resume, README, demo, or interview. Use the wording: "a synthetic enterprise-document corpus designed for controlled RAG evaluation."

## Scope and isolation

- The corpus is **not** under `backend/data/docs/` and is therefore not loaded by the current production-like retrieval path.
- The four documents in `backend/data/docs/` remain the regression baseline for the existing 31-case golden set.
- Every file in this directory has `source_type: synthetic` in `manifest.json`.

## Contents

| Kind | Count | Files | Intended test |
| --- | ---: | --- | --- |
| Structured Markdown | 5 | `markdown/` | heading paths, parent context, policy conflicts |
| Text PDFs | 3 | `pdf/remote_access_security_policy_v*.pdf`, `pdf/incident_response_handbook.pdf` | text extraction, page source links, version updates |
| Table PDFs | 2 | `pdf/expense_approval_matrix.pdf`, `pdf/network_change_window_calendar.pdf` | table rows, thresholds, filters |
| Image-only scan PDF | 1 | `pdf/visitor_access_registration_scan.pdf` | OCR fallback and parser warning paths |

## Reproduction

Run the PDF builder from the project root:

```powershell
.\backend\.venv\Scripts\python.exe .\eval\fixtures\synthetic_corpus_v1\build_pdfs.py
```

The builder is deterministic in content. The manifest hashes must be refreshed only after deliberate corpus edits.

## Pre-ingestion golden suite

`synthetic_golden_cases_v1.json` contains 18 cases that intentionally do **not** reuse the current `eval/rag_eval_cases.json` contract. They refer to document IDs, document versions, source hashes, pages, expected facts, and an expected action (`answer`, `refuse`, or `needs_ocr`) rather than invented chunk IDs.

Validate its relationship to the corpus before a parser/indexer exists:

```powershell
.\backend\.venv\Scripts\python.exe .\eval\fixtures\synthetic_corpus_v1\validate_synthetic_golden_cases.py
```

After Day 4 introduces `Document`, `ParsedDocument`, and `Chunk` contracts, a converter may add parser-produced `chunk_id` and `heading_path` assertions. Only then should these cases participate in Recall, MRR, nDCG, FPR, latency, and answer-quality metrics.
