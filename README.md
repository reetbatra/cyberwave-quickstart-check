# cyberwave-quickstart-check

[![cyberwave docs](https://github.com/reetbatra/cyberwave-quickstart-check/actions/workflows/docs-check.yml/badge.svg)](https://github.com/reetbatra/cyberwave-quickstart-check/actions/workflows/docs-check.yml)
[![tests](https://github.com/reetbatra/cyberwave-quickstart-check/actions/workflows/tests.yml/badge.svg)](https://github.com/reetbatra/cyberwave-quickstart-check/actions/workflows/tests.yml)

I installed the [Cyberwave](https://cyberwave.com) Python SDK to try it for the first time, and the first code example on the [Quickstart](https://docs.cyberwave.com) crashed on its first twin call:

```
>>> cw.twins("unitree/go2")
TypeError: 'TwinManager' object is not callable
```

So I wrote a script that checks every Python example in the docs against the SDK you actually get from `pip install cyberwave`. It runs every Monday. The badge above goes green when the docs and the SDK agree.

## What it found (cyberwave 0.7.2, 24 Sep 2026)

151 SDK calls across 5 docs pages. 12 of them don't exist in the SDK:

| Docs show | What happens | Fix |
|---|---|---|
| `cw.twins("unitree/go2")` (5 places) | `TypeError`: `cw.twins` is a `TwinManager`, not a function | `cw.twin("unitree/go2")` |
| `arm.set_joint("1", 30)` | No Twin class has `set_joint` | `arm.joints.set("1", 30, degrees=True)` |
| `robot.use_controller("keyboard")` (6 places) | No Twin class has `use_controller` | Depends on intent, see below |

A detail about `set_joint`: `joints.set()` takes radians by default, so fixing only the method name would send 30 radians (about 1,719°). The fixed example needs `degrees=True`.

The only `use_controller` in the SDK is `robot.navigation.use_controller(policy_uuid)`, which takes a policy UUID rather than `"keyboard"`. Whether the docs or the SDK should change there is Cyberwave's call, so I asked instead of guessing.

**Upstream:**
- PR [cyberwave-os/docs-mintlify#105](https://github.com/cyberwave-os/docs-mintlify/pull/105) fixes the `twins` and `set_joint` calls. With it applied, only the two `use_controller` lines in the Quickstart still fail, and #104 covers those.
- Issue [cyberwave-os/docs-mintlify#104](https://github.com/cyberwave-os/docs-mintlify/issues/104) asks about `use_controller`.

## Run it

You don't need a Cyberwave account or API key. The client can be constructed offline, and everything else is checked against the SDK's own classes.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python check.py     # exits 1 if any docs call is broken
.venv/bin/pytest -q           # 9 offline tests
```

Output looks like:

```
BROKEN  overview/index:38  drone = cw.twins("dji/dji-mini-4-pro")  <- cw.twins is a TwinManager, not callable
OK      overview/index:39  drone.takeoff()
...
151 calls checked, 12 broken
```

Line numbers refer to the page's markdown at `docs.cyberwave.com/<page>.md`.

## How it works

1. Fetch each page's markdown and pull out the ` ```python ` blocks.
2. Parse each block with Python's `ast` and track two kinds of variables: clients (`cw = Cyberwave()`) and twins (`arm = cw.twin(...)`). Names carry across blocks on the same page, because the docs usually define `cw` once and reuse it.
3. Check every attribute used on those variables:
   - **Client calls** run against a real `Cyberwave` instance, so `cw.twins` gets caught for being called even though it exists.
   - **Twin calls** are checked against all 26 Twin classes the SDK exports, including attributes set in `__init__` and sensor families like `twin.camera` that the SDK adds in `__getattr__`.

## Limits

- **Lenient twin check.** Which Twin class a catalog asset turns into is only known at runtime with an API key. So a method counts as OK if *any* Twin class has it. This can miss a method that exists on the wrong class, but it never flags one that exists.
- **Names only.** It checks that a method exists, not its arguments or behaviour.
- **Only calls on `Cyberwave()` clients and their twins.** Everything else in a code block is ignored.
