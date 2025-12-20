# Hey Emacs, this is -*- coding: utf-8; mode: python -*-

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from pathlib import Path


class TemplateConfig(TypedDict):
    project_name: str
    target_root: Path
    acg_templates: Path
