# Hey Emacs, this is -*- coding: utf-8; mode: python -*-

import copy
from pathlib import Path
from typing import Any, Self, cast

from pydantic import BaseModel, ConfigDict


class BaseModelNoExtra(BaseModel):
    model_config = (  # pyright: ignore[reportUnannotatedClassAttribute]
        ConfigDict(extra="forbid")
    )


class ProjectConfigAutocodegen(BaseModelNoExtra):
    # "project_name": project-root.stem if not in config
    project_name: str

    # "project_root": "acg_dir/.." if not in config
    project_root: Path

    # "templates_root": "acg_dir" if not in config
    templates_root: Path


class ProjectConfigWorkspace(BaseModelNoExtra):
    members: list[Path] = []


class ProjectConfigTemplate(BaseModelNoExtra):
    # "target_root": project_root if not in config
    # otherwise target_root path is relative to project_root
    target_root: Path = Path()


type TemplateName = str


class ProjectConfig(BaseModelNoExtra):
    autocodegen: ProjectConfigAutocodegen
    workspace: ProjectConfigWorkspace = ProjectConfigWorkspace()
    templates: dict[TemplateName, ProjectConfigTemplate]

    @classmethod
    def load(
        cls,
        data: dict[str, Any],  # pyright: ignore[reportExplicitAny]
        *,
        acg_dir: Path,
    ) -> Self:
        data_processed = copy.deepcopy(data)

        autocodegen: dict[str, Any] = (  # pyright: ignore[reportAny, reportExplicitAny]
            data_processed.pop("autocodegen", {})
        )  # fmt: skip

        if "templates_root" not in autocodegen:
            autocodegen["templates_root"] = acg_dir.resolve(strict=True)

        if "project_root" not in autocodegen:
            project_root = acg_dir.parent
        else:
            project_root = Path(cast("str", autocodegen["project_root"]))

            if project_root.is_absolute():
                project_root = project_root.resolve(strict=True)
            else:
                project_root = (acg_dir / project_root).resolve(strict=True)

        autocodegen["project_root"] = project_root

        if "project_name" not in autocodegen:
            autocodegen["project_name"] = autocodegen["project_root"].stem

        data_processed["autocodegen"] = autocodegen

        if "templates" not in data_processed:
            data_processed["templates"] = {}

        templates_from_dirs = {
            item.name: {"target_root": Path()}
            for item in sorted(acg_dir.iterdir())
            if item.is_dir() and item.name not in data_processed["templates"]
        }

        _ = data_processed["templates"].update(  # pyright: ignore[reportUnknownMemberType]
            templates_from_dirs,
        )  # fmt: skip

        return cls.model_validate(data_processed)
