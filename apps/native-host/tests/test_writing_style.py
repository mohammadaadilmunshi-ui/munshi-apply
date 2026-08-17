from munshi_apply_native.writing_style import WritingStyleStore


def test_style_learning_only_uses_approved_owner_edit(tmp_path):
    store = WritingStyleStore(tmp_path)
    unchanged = store.learn_from_approved_edit("Generated answer", "Generated answer")
    assert unchanged.samples == 0
    learned = store.learn_from_approved_edit(
        "I am extremely excited to leverage my extensive background in this wonderful opportunity.",
        "I’m interested because the role connects recruiting operations with analytics, "
        "which matches my experience.",
    )
    assert learned.samples == 1
    assert "learned style" in learned.instructions().lower()
