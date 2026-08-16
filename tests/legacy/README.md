# Legacy tests and diagnostics

Files in this directory are preserved history material. They record the
development process, earlier measurements, and diagnostic approaches, but are
not the updated source of final thesis results.

Files are moved here without changing their contents. Some historical runners
or hard-coded output paths may no longer execute from their new location; this
directory is an archive rather than the active evaluation interface.

The `features/` archive contains the former separate camera, bokeh, anisotropy,
Burley-angle, clearcoat/sheen, transparent-shadow-depth, and glazing scripts.
Their section 5.4 responsibilities are now covered by the single canonical
runner in `tests/evaluation/features/`.
