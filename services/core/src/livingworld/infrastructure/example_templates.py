"""Original bundled content; never downloads or executes community scripts."""

import json
from importlib.resources import files


def campus_template() -> dict:
    return json.loads(
        files("livingworld").joinpath("infrastructure/examples/campus.json").read_text("utf-8")
    )
