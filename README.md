# EOSC Data Player Demo

A small Python demo of the [EOSC Data Player](https://www.eosc-data-commons.eu/service/eosc-data-player), the entry point of the EOSC Data Commons architecture. The Player (implemented by the [Dispatcher](https://github.com/EOSC-Data-Commons/Dispatcher)) takes an [RO-Crate](https://www.researchobject.org/ro-crate/) that references a workflow and its inputs, and sets up an environment where the workflow can be started.

## What it does

[`src/run_example.py`](src/run_example.py) submits an example RO-Crate from the [vre_rocrate fixtures](https://github.com/EOSC-Data-Commons/vre_rocrate/tree/master/tests/fixtures) to the Player. Two examples are supported:

| Example | Description |
| --- | --- |
| `simple-binder` (default) | A trivial Jupyter notebook that prints Pi. |
| `alphafind-notebook` | A realistic notebook (`multi-domain-search.ipynb`) that searches for similar AlphaFold protein structures. Installs `pandas`, `mdtraj`, `nglview` and others, so the first build is slower. The script pins `nglview<4` (and adds `setuptools<81` to silence a `pkg_resources` deprecation warning): the unpinned `nglview` 4.0 doesn't match the widget extension on mybinder.org and fails with "Failed to load model class 'ColormakerRegistryModel'". |

For the chosen example the script:

1. Downloads its files from the fixtures and zips them flat.
2. Patches the crate so it runs on a public BinderHub (mybinder.org instead of the fixture's EGI-only Replay Notebooks). For `simple-binder` it also adds a minimal `requirements.txt`, which repo2docker needs to build an image; `alphafind-notebook` already has one.
3. POSTs the zip to `/requests/zip_rocrate/` (multipart field `zipfile`).
4. Polls `/requests/{task_id}` until the status is `SUCCESS`, then prints the URL of the created Binder environment and opens it in a new browser tab. Then run the notebook from the JupyterLab file browser.

## Prerequisites

- Python 3.8 or greater
- The `requests` library (installed in a virtual environment, see Quick Start)
- Either use `--anon` (no login), or a Player session token (see below)

### Getting a session token

The authenticated endpoints need the Player's own session token, which is stored in the `Authorization` cookie after you log in. Do **not** use the token returned by `/oauth2/token`: that is the raw EGI access token, and the server rejects it with `The specified alg value is not allowed`.

1. Log in via EGI Check-in at <https://dev1.player.eosc-data-commons.eu> in a browser.
2. In the browser dev tools, open Application/Storage > Cookies for that host and copy the value of the cookie named `Authorization` (the `Bearer ` prefix is optional).
3. Export it: `export PLAYER_TOKEN=<value>`

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install requests
python3 src/run_example.py --anon                      # simple-binder, no login needed
python3 src/run_example.py alphafind-notebook --anon   # the AlphaFind example
# or, with a session token (see above):
export PLAYER_TOKEN=<value>
python3 src/run_example.py
```

A virtual environment is recommended on macOS: recent Homebrew and system Pythons are "externally managed" (PEP 668) and refuse a plain `pip install`. In each new terminal, re-run `source .venv/bin/activate` before running the script.

Options:

| Option | Description |
| --- | --- |
| `example` | Positional: `simple-binder` (default) or `alphafind-notebook`. |
| `--base URL` | Player instance to use. Default: `https://dev1.player.eosc-data-commons.eu` (dev). Use `https://player.eosc-data-commons.eu` for production, with a token from that host. |
| `--token TOKEN` | Player session token (the `Authorization` cookie value); alternative to `PLAYER_TOKEN`. |
| `--anon` | Use the unauthenticated `/anon_requests` endpoints, if the instance exposes them. |
| `--binder-url URL` | BinderHub that runs the notebook. Default: `https://mybinder.org` (public, no login). The fixture itself targets `https://replay.notebooks.egi.eu/v2`, which needs an EGI account with access; pass `--binder-url ''` to keep that. |
| `--no-browser` | Only print the environment URL; don't open it in a new browser tab (the default is to open it). |
| `--timeout SECONDS` | How long to wait for the request to finish. Default: 600. |

Note: the cookie-token and `--anon` paths follow the Dispatcher source and have not been verified against a live instance.

## Project Structure

```
<ROOT>
└── src
    └── run_example.py   # Submits an example RO-Crate to the Player.
```

## Contributing

Please read [CONTRIBUTING](CONTRIBUTING.md) for details on our code of conduct, and the process for submitting pull requests to us.

## Versioning

See [Semantic Versioning](https://semver.org/) for guidance.

## Contributors

You can find the list of contributors in the [CONTRIBUTORS](CONTRIBUTORS.md) file.

## License

See the [LICENSE](LICENSE.txt) file.

## CITING

See the [CITATION](CITATION.cff) file.
