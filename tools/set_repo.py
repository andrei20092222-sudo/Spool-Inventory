#!/usr/bin/env python3
"""One-time setup after creating the GitHub repository.

Usage: python3 tools/set_repo.py GITHUB_USER REPO_NAME "Your Name"

Fills in LICENSE, the manifest (documentation, issue_tracker, codeowners) and the README links.
"""

import json
from pathlib import Path
import re
import sys

if len(sys.argv) != 4:
    sys.exit(__doc__)
user, repo, name = sys.argv[1:]
root = Path(__file__).resolve().parent.parent
url = f"https://github.com/{user}/{repo}"

lic = root / "LICENSE"
lic.write_text(lic.read_text().replace("[YOUR NAME]", name))

manifest = root / "custom_components" / "spool_inventory" / "manifest.json"
data = json.loads(manifest.read_text())
data["documentation"] = url
data["issue_tracker"] = f"{url}/issues"
data["codeowners"] = [f"@{user}"]
order = ["domain", "name", "codeowners", "config_flow", "dependencies", "documentation", "integration_type",
         "iot_class", "issue_tracker", "requirements", "single_config_entry", "version"]
manifest.write_text(json.dumps({k: data[k] for k in order if k in data}, indent=2) + "\n")

readme = root / "README.md"
text = readme.read_text()
if url not in text:
    text = re.sub(r"(\n### HACS \(custom repository\)\n\n)", rf"\1Repository: {url}\n\n", text, count=1)
    text = text.replace("Add this repository's URL, category", f"Add `{url}`, category")
readme.write_text(text)
print(f"Done: {url}")
