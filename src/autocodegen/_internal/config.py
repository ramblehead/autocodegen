# Hey Emacs, this is -*- coding: utf-8 -*-

import copy
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict


class BaseModelNoExtra(BaseModel):
    model_config = (  # pyright: ignore[reportUnannotatedClassAttribute]
        ConfigDict(extra="forbid")
    )


class ProjectConfigAutocodegen(BaseModelNoExtra):
    # "project_name": project-root.stem if not in config
    project_name: str

    # "project_root": "acg_dir/.."
    project_root: Path

    # "templates_root": "acg_dir"
    templates_root: Path


class ProjectConfigWorkspace(BaseModelNoExtra):
    members: list[Path] = []


class ProjectConfigTemplate(BaseModelNoExtra):
    # "target_dir": project_root if not in config
    # otherwise target_dir path is relative to project_root
    target_dir: Path = Path()

    # init is True causes .gen1.py and .ren1 to expand
    # Project-level init overrides corresponding templates-level init
    init: bool = True

    # Defend dirs and files located in target_dir from changes
    # during templates expansions
    self_defence: bool = True


type TemplateName = str


class ProjectConfig(BaseModelNoExtra):
    autocodegen: ProjectConfigAutocodegen
    workspace: ProjectConfigWorkspace | None = None
    templates: dict[TemplateName, ProjectConfigTemplate]

    @classmethod
    def load(
        cls,
        data: dict[str, Any],  # pyright: ignore[reportExplicitAny]
        *,
        acg_dir: Path,
        project_name_default: str | None = None,
    ) -> Self:
        data_processed = copy.deepcopy(data)

        autocodegen: dict[str, Any] = (  # pyright: ignore[reportAny, reportExplicitAny]
            data_processed.pop("autocodegen", {})
        )  # fmt: skip

        autocodegen["templates_root"] = acg_dir
        autocodegen["project_root"] = acg_dir.parent

        if "project_name" not in autocodegen:
            autocodegen["project_name"] = (
                project_name_default
                if project_name_default is not None
                else autocodegen["project_root"].stem
            )

        data_processed["autocodegen"] = autocodegen

        if "templates" not in data_processed:
            data_processed["templates"] = {}

        templates_from_dirs = {
            item.name: {"target_dir": "."}
            for item in sorted(acg_dir.iterdir())
            if item.is_dir() and item.name not in data_processed["templates"]
        }

        _ = data_processed["templates"].update(  # pyright: ignore[reportUnknownMemberType]
            templates_from_dirs,
        )  # fmt: skip

        return cls.model_validate(data_processed)
