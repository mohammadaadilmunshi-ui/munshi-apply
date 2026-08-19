# Generic Choice-Shell Repair Regression Boundary

Physical testing exposed an ATS dropdown whose visible `Select an option` shell was not represented by a native `<select>` or supported ARIA combobox. The scanner therefore omitted `Years of Experience` from Teach MUNSHI.

The repair extends discovery only when a generic focusable/structurally-select-like shell has strong choice-control evidence. Unrelated focusable containers remain excluded. Teach coverage verifies a `Years of Experience` shell with a portaled option can be captured without retaining the demonstrated answer value.

This note intentionally changes no runtime behavior; it exists to trigger and document the ordinary read-only verification boundary after the guarded repair commit.
