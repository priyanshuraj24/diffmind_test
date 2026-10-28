from diffmind.code import chunk_file, eligible, lexical, parse_diff
from diffmind.models import Finding
from diffmind.reviewer import validate_findings


def test_file_policy():
    assert eligible("src/Payment.tsx")
    assert eligible("src/Payment.jsx")
    for path in (".env", ".env.production", "foo.pem", "src/secrets.json", "node_modules/a.ts", "../x.py"):
        assert not eligible(path)


def test_symbol_chunks_keep_real_lines():
    text = "import os\n\ndef refund(amount):\n    return amount + 1\n\nclass Ledger:\n    pass\n"
    chunks = chunk_file("ledger.py", text)
    assert any(c.symbol == "refund" for c in chunks)
    for c in chunks:
        assert c.text == "\n".join(text.splitlines()[c.start-1:c.end])


def test_tsx_parser():
    chunks = chunk_file("app.tsx", "export function App() {\n  return <h1>Hello</h1>;\n}\n")
    assert any(c.symbol == "App" for c in chunks)


def test_identifiers_preserved_and_split():
    value = lexical("checkPayment_owner")
    assert "checkPayment_owner" in value and "check Payment owner" in value


def test_comment_locations_multihunk_deletion_and_addition():
    patch = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -4,2 +4,2 @@
 keep
-old
+new
@@ -20 +20 @@
-bad
+good
diff --git a/deleted.py b/deleted.py
--- a/deleted.py
+++ /dev/null
@@ -1 +0,0 @@
-gone
"""
    positions = parse_diff(patch)
    assert positions["a.py"]["RIGHT"] == {4, 5, 20}
    assert positions["a.py"]["changed"] == {5, 20}
    assert positions["deleted.py"]["LEFT"] == {1}
    assert positions["deleted.py"]["RIGHT"] == set()


def test_reject_invented_location_and_evidence():
    valid = Finding(title="Bad refund", body="Exceeds balance", category="correctness", severity="high",
                    path="a.py", line=5, evidence_ids=["E1"], scenario="Refund exceeds captured amount")
    evidence = [{"evidence_id": "E1", "path": "a.py"}]
    locations = {"a.py": {"RIGHT": {5}, "LEFT": set()}}
    accepted, _ = validate_findings([valid], locations, evidence)
    assert accepted == [valid]
    accepted, rejected = validate_findings([valid.model_copy(update={"line": 999}),
                                           valid.model_copy(update={"evidence_ids": ["invented"]})], locations, evidence)
    assert not accepted
    assert {r["reason"] for r in rejected} == {"not_commentable", "invalid_evidence"}
