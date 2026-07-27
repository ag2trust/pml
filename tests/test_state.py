from pathlib import Path

import json
from jsonschema import Draft202012Validator
import yaml

from pml.obligations import Obligation, enumerate_obligations
from pml.project_state import canonical_hash, input_fingerprint, validate_product_state
from pml.status import derive_obligation_status
from pml.validator import load_document


ROOT = Path(__file__).resolve().parents[1]


def test_obligations_have_stable_ids() -> None:
    document, diagnostics = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert diagnostics == []
    assert document is not None
    obligations = list(enumerate_obligations(document))
    assert [item.id for item in obligations] == [
        "domains.notes.features.creation.rules.preserve_content",
        "domains.notes.features.creation.use_cases.create_note",
    ]


def test_product_state_detects_changed_bound_input(tmp_path: Path) -> None:
    document, diagnostics = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert diagnostics == []
    assert document is not None
    node_id = "domains.notes.features.creation"
    node = document["domains"]["notes"]["features"]["creation"]

    source = tmp_path / "src" / "notes.py"
    source.parent.mkdir()
    source.write_text("VERSION = 1\n")
    metadata = tmp_path / ".pml"
    state_dir = metadata / "state" / "domains" / "notes" / "features"
    state_dir.mkdir(parents=True)
    (metadata / "pml.lock").write_text(
        "pml_lock: '0.1'\ndefinition:\n"
        "  source: https://example.invalid/product-pml.git\n"
        "  revision: approved-revision\n"
        f"  digest: {canonical_hash(document)}\n"
    )
    (metadata / "bindings.yaml").write_text(
        "pml_bindings: '0.1'\nbindings:\n"
        f"  {node_id}:\n"
        "    paths: [src/notes.py]\n"
        "    verification:\n"
        f"      {node_id}.rules.preserve_content:\n"
        "        probes: {preserve_content: 1.0}\n"
        f"      {node_id}.use_cases.create_note:\n"
        "        agent_judgment: 1.0\n"
    )
    obligations = {}
    for obligation in enumerate_obligations(document, node_id):
        obligations[obligation.id] = {"implemented": "unknown", "evidence": {}}
    state = {
        "pml_state": "0.1",
        "node": node_id,
        "definition_hash": canonical_hash(node),
        "input_fingerprint": input_fingerprint(tmp_path, ["src/notes.py"]),
        "obligations": obligations,
    }
    state_path = state_dir / "creation.state.yaml"
    state_path.write_text(yaml.safe_dump(state, sort_keys=False))

    assert validate_product_state(tmp_path, document) == []
    source.write_text("VERSION = 2\n")
    changed = validate_product_state(tmp_path, document)
    assert any(item.code == "sync-required" for item in changed)


def test_state_schema_rejects_authored_scores_and_freshness() -> None:
    schema = json.loads((ROOT / "schema" / "pml-state.schema.json").read_text())
    state = yaml.safe_load((ROOT / "examples" / "invalid-state.yaml").read_text())
    errors = list(Draft202012Validator(schema).iter_errors(state))
    messages = "\n".join(error.message for error in errors)
    assert "verification_score" in messages
    assert "freshness" in messages


def test_rejects_unknown_related_node(tmp_path: Path) -> None:
    source = (ROOT / "examples" / "minimal.pml.yaml").read_text().replace(
        "        rules:\n",
        "        related_to: [domains.missing.features.unknown]\n        rules:\n",
        1,
    )
    manifest = tmp_path / "dependency.yaml"
    manifest.write_text(source)
    from pml.validator import validate_file

    assert any(item.code == "undefined-reference" and "unknown node" in item.message for item in validate_file(manifest))


def test_coverage_moves_from_stale_to_partial_to_verified() -> None:
    obligation = Obligation(
        id="domains.core.features.sample.rules.behavior",
        node_id="domains.core.features.sample",
        section="rules",
        local_id="behavior",
        definition={"statement": "THE SYSTEM MUST behave."},
    )
    current = f"sha256:{'a' * 64}"
    old = f"sha256:{'b' * 64}"
    common = {
        "result": "passed",
        "recorded": "2026-07-22T10:00:00Z",
        "observation": "Observed.",
    }
    state = {
        "evidence": {
            "deterministic_probe": {"probe": {**common, "input_fingerprint": old}},
            "agent_judgment": {**common, "input_fingerprint": old},
        }
    }
    plan = {"probes": {"probe": 0.5}, "agent_judgment": 0.5}
    stale = derive_obligation_status(obligation, state, current, True, plan)
    assert (stale.signal, stale.verified_coverage) == ("STALE", 0)

    state["evidence"]["deterministic_probe"]["probe"]["input_fingerprint"] = current
    partial = derive_obligation_status(obligation, state, current, True, plan)
    assert (partial.signal, partial.verified_coverage) == ("PARTIAL", 0.5)

    state["evidence"]["agent_judgment"]["input_fingerprint"] = current
    verified = derive_obligation_status(obligation, state, current, True, plan)
    assert (verified.signal, verified.verified_coverage) == ("VERIFIED", 1.0)


def test_binding_coverage_must_total_one(tmp_path: Path) -> None:
    document, _ = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert document is not None
    node_id = "domains.notes.features.creation"
    metadata = tmp_path / ".pml"
    metadata.mkdir()
    (metadata / "pml.lock").write_text(
        "pml_lock: '0.1'\ndefinition:\n"
        "  source: https://example.invalid/product-pml.git\n"
        "  revision: approved\n"
        f"  digest: {canonical_hash(document)}\n"
    )
    (metadata / "bindings.yaml").write_text(
        "pml_bindings: '0.1'\nbindings:\n"
        f"  {node_id}:\n"
        "    paths: [src]\n"
        "    verification:\n"
        f"      {node_id}.rules.preserve_content:\n"
        "        probes: {preserve: 0.5}\n"
        "        agent_judgment: 0.4\n"
        f"      {node_id}.use_cases.create_note:\n"
        "        agent_judgment: 1.0\n"
    )
    diagnostics = validate_product_state(tmp_path, document)
    assert any(item.code == "coverage-total" for item in diagnostics)


def test_project_and_domain_rules_are_obligations() -> None:
    document, _ = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert document is not None
    document["rules"] = {
        "global": {"statement": "THE SYSTEM MUST preserve product truth."}
    }
    document["domains"]["notes"]["rules"] = {
        "domain": {"statement": "Notes MUST remain durable."}
    }
    ids = {item.id for item in enumerate_obligations(document)}
    assert "project.rules.global" in ids
    assert "domains.notes.rules.domain" in ids
