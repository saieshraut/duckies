import json
import os

import frappe

no_cache = 1


def get_context(context):
    context.csrf_token = frappe.session.csrf_token
    context.script_tag, context.style_tags = _asset_tags()
    return context


def _asset_tags():
    """Read Vite's manifest.json (written into public/cafe/.vite) and return
    the correct hashed <script>/<link> tags. Falls back to non-hashed names."""
    base = "/assets/duckies/cafe"
    app_path = frappe.get_app_path("duckies")
    manifest_path = os.path.join(
        app_path, "public", "cafe", ".vite", "manifest.json")
    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
        entry = manifest.get("src/main.js") or next(iter(manifest.values()))
        script = f'{base}/{entry["file"]}'
        styles = [f"{base}/{c}" for c in entry.get("css", [])]
        return script, styles
    except Exception:
        return f"{base}/main.js", []
