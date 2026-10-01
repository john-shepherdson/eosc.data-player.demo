#!/usr/bin/env python3
"""Submit an example RO-Crate to the EOSC Data Player (Dispatcher).

Downloads the chosen fixture's files from EOSC-Data-Commons/vre_rocrate, zips them flat,
POSTs the zip, polls until the request finishes, and prints the URL of the
created environment (a Binder-launched Jupyter notebook).

Authentication
--------------
The Dispatcher enables unauthenticated /anon_requests/* endpoints by default,
so try --anon first; it needs no token.

For the authenticated endpoints you need the Player's own session token, NOT
the EGI access token returned by /oauth2/token (the server rejects that one
with "The specified alg value is not allowed"):
  1. Open https://dev1.player.eosc-data-commons.eu/ in a browser and log in via
     EGI Check-in.
  2. In the browser dev tools, open Application/Storage > Cookies for that host
     and copy the value of the cookie named "Authorization" (looks like
     "Bearer eyJ..."; the "Bearer " prefix is optional here).
  3. export PLAYER_TOKEN=<value>   (or pass --token)

Usage
-----
  python run_example.py                       # simple-binder, dev instance, needs token
  python run_example.py alphafind-notebook --anon
  python run_example.py --anon                # no token
  python run_example.py --base https://player.eosc-data-commons.eu
Requires: pip install requests
"""
import argparse
import io
import json
import os
import sys
import time
import webbrowser
import zipfile
from typing import Dict, List, Optional
from urllib.parse import unquote

import requests

FIXTURE_BASE = (
    "https://raw.githubusercontent.com/EOSC-Data-Commons/vre_rocrate/"
    "master/tests/fixtures/"
)

# repo2docker (used by BinderHub) fails with "No environment specification found"
# unless the repo has a config file. simple-binder ships none and only needs the
# standard library, so we add a comment-only requirements.txt. alphafind-notebook
# ships and declares its own requirements.txt.
ENV_FILE = "requirements.txt"
ENV_FILE_CONTENT = b"# notebook.ipynb only uses the standard library\n"

# name -> files to download (ro-crate-metadata.json must be included) and whether
# the script must add the environment file itself. Each is zipped flat.
FIXTURES = {
    "simple-binder": {
        "files": ["ro-crate-metadata.json", "notebook.ipynb"],
        "add_env_file": True,
    },
    "alphafind-notebook": {
        "files": ["ro-crate-metadata.json", "multi-domain-search.ipynb", "requirements.txt"],
        "add_env_file": False,
        # The fixture's unpinned nglview installs 4.0, but the JupyterLab front end on
        # mybinder.org only registers nglview-js-widgets 3.1.5 ("Failed to load model
        # class 'ColormakerRegistryModel'"). Stay on 3.x so the versions match.
        "requirements_pins": {"nglview": "nglview<4"},
        # nglview 3.x imports the deprecated pkg_resources, which warns on setuptools>=81.
        "requirements_extra": ["setuptools<81"],
    },
}


def patch_metadata(metadata: bytes, binder_url: Optional[str], add_env_file: bool) -> bytes:
    """Adjust the fixture's RO-Crate metadata so it runs on a public BinderHub.

    - runtimePlatform: the fixture targets https://replay.notebooks.egi.eu/v2,
      which requires an EGI account with access. If binder_url is given it
      replaces that (the Dispatcher then builds <binder_url>/v2/git/...).
    - requirements.txt (if add_env_file): the Dispatcher only copies files listed in the root
      dataset's hasPart into the repo it builds, so the environment file must
      be declared there as well as being present in the zip.
    """
    doc = json.loads(metadata)
    graph = doc.get("@graph", [])
    for node in graph:
        if binder_url and "runtimePlatform" in node:
            node["runtimePlatform"] = binder_url
        if add_env_file and node.get("@id") == "./":
            node.setdefault("hasPart", []).append({"@id": ENV_FILE})
    if add_env_file:
        graph.append({"@id": ENV_FILE, "@type": "File", "name": "Python environment"})
    return json.dumps(doc, indent=4).encode()


def pin_requirements(content: bytes, pins: Dict[str, str], extra: List[str]) -> bytes:
    """Replace unpinned requirement lines (e.g. 'nglview') with pinned ones and append extras."""
    lines = [pins.get(line.strip(), line) for line in content.decode().splitlines()]
    return ("\n".join(lines + extra) + "\n").encode()


def build_zip(fixture: str, binder_url: Optional[str]) -> bytes:
    spec = FIXTURES[fixture]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in spec["files"]:
            r = requests.get(f"{FIXTURE_BASE}{fixture}/{name}", timeout=30)
            r.raise_for_status()
            content = r.content
            if name == "ro-crate-metadata.json":
                content = patch_metadata(content, binder_url, spec["add_env_file"])
            elif name == ENV_FILE:
                content = pin_requirements(
                    content, spec.get("requirements_pins", {}), spec.get("requirements_extra", [])
                )
            z.writestr(name, content)  # flat: no sub-directories
        if spec["add_env_file"]:
            z.writestr(ENV_FILE, ENV_FILE_CONTENT)
    return buf.getvalue()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument(
        "example",
        nargs="?",
        default="simple-binder",
        choices=sorted(FIXTURES),
        help="which example RO-Crate to submit (default: simple-binder)",
    )
    p.add_argument("--base", default="https://dev1.player.eosc-data-commons.eu")
    p.add_argument("--token", default=os.environ.get("PLAYER_TOKEN"))
    p.add_argument("--anon", action="store_true", help="use /anon_requests (no auth)")
    p.add_argument(
        "--binder-url",
        default="https://mybinder.org",
        help="BinderHub to run the notebook on (default: public mybinder.org, no login).\n"
        "Pass '' to keep the fixture's own target, https://replay.notebooks.egi.eu/v2 (needs EGI access).",
    )
    p.add_argument("--no-browser", action="store_true", help="print the environment URL without opening a browser tab")
    p.add_argument("--timeout", type=int, default=600, help="seconds to wait for result")
    args = p.parse_args()

    prefix = "anon_requests" if args.anon else "requests"
    headers = {}
    if not args.anon:
        if not args.token:
            sys.exit("No token. Set PLAYER_TOKEN or pass --token (see script docstring), or use --anon.")
        # Accept the raw cookie value: may be quoted, URL-encoded, with/without "Bearer ".
        token = unquote(args.token).strip().strip('"')
        if token.lower().startswith("bearer"):
            token = token[len("bearer"):].strip()
        headers["Authorization"] = f"Bearer {token}"

    base = args.base.rstrip("/")
    print(f"Building {args.example} zip (BinderHub: {args.binder_url or 'fixture default'})...")
    payload = build_zip(args.example, args.binder_url)

    # The endpoint reads an UploadFile, so it must be multipart with field "zipfile".
    r = requests.post(
        f"{base}/{prefix}/zip_rocrate/",
        headers=headers,
        files={"zipfile": (f"{args.example}.zip", payload, "application/zip")},
        timeout=60,
    )
    if not r.ok:
        sys.exit(f"Submit failed: HTTP {r.status_code}\n{r.text}")
    task_id = r.json()["task_id"]
    print(f"Submitted. task_id = {task_id}")

    deadline = time.time() + args.timeout
    last = None
    while time.time() < deadline:
        s = requests.get(f"{base}/{prefix}/{task_id}", headers=headers, timeout=30)
        if not s.ok:
            sys.exit(f"Status check failed: HTTP {s.status_code}\n{s.text}")
        body = s.json()
        if body["status"] != last:
            print(f"status: {body['status']}")
            last = body["status"]
        if body["status"] == "SUCCESS":
            print("Environment ready:")
            print(body["result"])
            url = body["result"]
            if not args.no_browser and isinstance(url, str) and url.startswith(("http://", "https://")):
                webbrowser.open_new_tab(url)
            return 0
        if body["status"] in ("FAILURE", "REVOKED"):
            print(f"Failed: {body['result']}")
            return 1
        time.sleep(3)

    print("Timed out waiting for the request to finish.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
