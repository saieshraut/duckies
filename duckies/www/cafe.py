import json
import os

import frappe

no_cache = 1


def get_context(context):
    context.csrf_token = frappe.session.csrf_token
    context.script_tag, context.style_tags = _asset_tags()
    return context


def _asset_tags():
    """Read Vite's manifest.json and return the hashed <script>/<link> tags
    for the entry chunk. Falls back to non-hashed names if manifest missing."""
    base = "/assets/duckies/cafe"
    app_path = frappe.get_app_path("duckies")
    manifest_path = os.path.join(
        app_path, "public", "cafe", ".vite", "manifest.json")
    try:
        with open(manifest_path) as f:
            manifest = json.load(f)

        # Find the entry chunk. Vite marks it isEntry=True; its key may be
        # "index.html" or "src/main.js" depending on how the entry is declared.
        entry = None
        for key in ("src/main.js", "index.html"):
            if key in manifest:
                entry = manifest[key]
                break
        if entry is None:
            entry = next((v for v in manifest.values() if v.get("isEntry")),
                         None)
        if entry is None:
            raise ValueError("no entry in manifest")

        script = f'{base}/{entry["file"]}'
        styles = [f"{base}/{c}" for c in entry.get("css", [])]
        return script, styles
    except Exception:
        frappe.log_error(title="Duckies cafe asset manifest not found",
                         message=frappe.get_traceback())
        return f"{base}/main.js", []
