from pathlib import Path

from ethovx.corpus_manager import build_corpus


def test_build_corpus_only_from_approved_paths(tmp_path):
    approved_dir = tmp_path / "approved"
    approved_dir.mkdir()
    (approved_dir / "doc1.txt").write_text("תוכן מסמך ראשון", encoding="utf-8")
    (approved_dir / "doc2.md").write_text("תוכן מסמך שני", encoding="utf-8")

    unapproved_dir = tmp_path / "not_approved"
    unapproved_dir.mkdir()
    (unapproved_dir / "secret.txt").write_text("לא אמור להיכלל", encoding="utf-8")

    snapshot = build_corpus([str(approved_dir)])

    assert len(snapshot.files) == 2
    assert all("not_approved" not in f for f in snapshot.files)
    assert len(snapshot.corpus_hash) == 64  # sha256 hex digest


def test_corpus_hash_is_deterministic(tmp_path):
    d = tmp_path / "c"
    d.mkdir()
    (d / "a.txt").write_text("same content", encoding="utf-8")

    snap1 = build_corpus([str(d)])
    snap2 = build_corpus([str(d)])

    assert snap1.corpus_hash == snap2.corpus_hash
