"""Reads config.toml and provides global constants."""

import tomllib as tl

conf: dict
with open("qcedule/config.toml", "rb") as file:
    conf = tl.load(file)

CONSTANTS = conf["const"]
FILES = conf["files"]
BACKEND = conf["backend"]
