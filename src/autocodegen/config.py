# Hey Emacs, this is -*- coding: utf-8; mode: python -*-

from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from pathlib import Path


class Config(NamedTuple):
    project_name: str
    project_root: Path
    acg_root: Path
