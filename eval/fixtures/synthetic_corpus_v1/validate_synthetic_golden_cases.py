"""Validate the pre-ingestion golden-case contract against the synthetic corpus manifest."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "manifest.json"
CASES_PATH = ROOT / "synthetic_golden_cases_v1.json"
ANSWER_ACTION = "answer"
VALID_ACTIONS = {ANSWER_ACTION, "refuse", "needs_ocr"}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    manifest = load_json(MANIFEST_PATH)
    suite = load_json(CASES_PATH)
    documents = {
        document["document_id"]: document
        for document in manifest["documents"]
    }
    superseded_ids = {
        document["supersedes"]
        for document in documents.values()
        if document.get("supersedes")
    }
    cases = suite["cases"]

    if suite["corpus_id"] != manifest["corpus_id"]:
        raise ValueError("golden suite and manifest corpus_id do not match")
    if suite["source_type"] != manifest["source_type"]:
        raise ValueError("golden suite and manifest source_type do not match")

    case_ids = [case["id"] for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("duplicate case ids")

    for case in cases:
        action = case["expected_action"]
        if action not in VALID_ACTIONS:
            raise ValueError(f"{case['id']}: unsupported expected_action={action}")

        scope = case["index_scope"]
        unknown_ids = set(scope) - set(documents)
        if unknown_ids:
            raise ValueError(f"{case['id']}: unknown document ids {sorted(unknown_ids)}")

        document_id = case["expected_document_id"]
        if action == ANSWER_ACTION:
            if not document_id or document_id not in scope:
                raise ValueError(f"{case['id']}: answer case needs an in-scope expected document")
            if not case["expected_answer_contains"]:
                raise ValueError(f"{case['id']}: answer case needs expected answer facts")
        elif action == "refuse":
            if document_id is not None:
                raise ValueError(f"{case['id']}: refuse case must not name a source document")
        else:
            if not document_id or documents[document_id]["format"] != "pdf_image_only":
                raise ValueError(f"{case['id']}: needs_ocr case must target an image-only PDF")

        if document_id:
            document = documents[document_id]
            if case["expected_document_version"] != document["version"]:
                raise ValueError(f"{case['id']}: document version does not match manifest")
            actual_hash = hashlib.sha256((ROOT / document["path"]).read_bytes()).hexdigest()
            if actual_hash != document["sha256"]:
                raise ValueError(f"{case['id']}: manifest hash mismatch for {document_id}")
            if case["latest_version_only"] and document_id in superseded_ids:
                raise ValueError(f"{case['id']}: latest-version case points to a superseded document")

    actions = {case["expected_action"] for case in cases}
    if not {"answer", "refuse", "needs_ocr"}.issubset(actions):
        raise ValueError("suite must cover answer, refuse, and needs_ocr actions")

    print(f"Synthetic golden contract: Passed {len(cases)}/{len(cases)}")
    print("Status: pre-ingestion contract only; no retrieval metric was calculated.")


if __name__ == "__main__":
    main()
