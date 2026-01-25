# Hey Emacs, this is -*- coding: utf-8 -*-

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

    # "project_root": "acg_dir/.."
    project_root: Path

    # "templates_root": "acg_dir"
    templates_root: Path


class ProjectConfigWorkspace(BaseModelNoExtra):
    # Workspace-level init
    init: bool = False

    # Workspace member projects
    members: list[Path] = []


class ProjectConfigTemplateBootstrap(BaseModelNoExtra):
    # "target_dir": project_root if not in config
    # otherwise target_dir path is relative to project_root
    target_dir: Path = Path()

    # init is True causes .gen1.py and .ren1 to expand
    # Project-level init overrides corresponding templates-level init
    init: bool = False

    # Defend dirs and files located in target_dir from changes
    # during templates expansions
    self_defence: bool = True


class ProjectConfigTemplate(BaseModelNoExtra):
    # "ProjectConfigAutocodegen.project_name": if not in config
    project_name: str

    bootstrap: ProjectConfigTemplateBootstrap = (
        ProjectConfigTemplateBootstrap()
    )


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
        templates_root: Path,
        project_name_default: str | None = None,
    ) -> Self:
        data_processed = copy.deepcopy(data)

        autocodegen: dict[str, Any] = (  # pyright: ignore[reportAny, reportExplicitAny]
            data_processed.pop("autocodegen", {})
        )  # fmt: skip

        autocodegen_templates_root = cast(
            "str | None",
            autocodegen.get("templates_root"),
        )

        if autocodegen_templates_root:
            msg = (
                f"acg config field "
                f'autocodegen.templates_root = "{autocodegen_templates_root}" '
                "is ignored, using "
                f"{templates_root} instead"
            )

            print(msg)

        autocodegen["templates_root"] = templates_root

        autocodegen_project_root = cast(
            "str | None",
            autocodegen.get("project_root"),
        )

        if autocodegen_project_root:
            msg = (
                f"acg config field "
                f'autocodegen.root.parent = "{autocodegen_project_root}" '
                "is ignored, using top acg project"
                f"instead: {templates_root.parent}"
            )

            print(msg)

        autocodegen["project_root"] = templates_root.parent

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
            item.name: {"bootstrap": {"target_dir": "."}}
            for item in sorted(templates_root.iterdir())
            if item.is_dir() and item.name not in data_processed["templates"]
        }

        _ = data_processed["templates"].update(  # pyright: ignore[reportUnknownMemberType]
            templates_from_dirs,
        )  # fmt: skip

        for [_, template] in data_processed["templates"].items():  # pyright: ignore[reportUnknownVariableType] # fmt: skip
            if "project_name" not in template:
                pn = cast("str", data_processed["autocodegen"]["project_name"])
                template["project_name"] = pn

        print(data_processed)
        return cls.model_validate(data_processed)
