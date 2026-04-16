import os
import sqlite3
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def test_v100_release_notes_complete():
    f = os.path.join(REPO, "docs/release_notes_v1.0.0.md")
    assert os.path.exists(f)
    with open(f) as doc: content = doc.read()
    assert "63.47" in content   # v1.2 accuracy
    assert "18" in content      # boot time
    assert "185" in content     # test count

def test_beta_feedback_form_exists():
    assert os.path.exists(os.path.join(
        REPO, "docs/beta-feedback-form.md"))

def test_month10_benchmarks_exist():
    assert os.path.exists(os.path.join(
        REPO, "results/month10_benchmarks.txt"))

def test_demo_video_result_exists():
    assert os.path.exists(os.path.join(
        REPO, "results/demo_v090.mp4")) or \
    os.path.exists(os.path.join(
        REPO, "results/demo_v100.mp4"))

def test_v12_model_active_in_brain():
    db = os.path.join(REPO, ".gemini/antigravity/brain/26c00955-554c-4fec-8c29-af755b84cdc8/eonix_project_brain.db")
    if not os.path.exists(db):
        pytest.skip("Brain DB not present")
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT version FROM model_versions WHERE active=1").fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "v1.2"
