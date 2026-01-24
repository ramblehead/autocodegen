#!/usr/bin/env python
# Hey Emacs, this is -*- coding: utf-8 -*-

# /// script
# requires-python = "==3.14.*"
#
# dependencies = ["autocodegen"]
#
# [tool.uv.sources]
# autocodegen = { path = "../../../acg-templates-hop/hop/autocodegen", editable = true }
#
# [dependency-groups]
# dev = [
#   "black~=25.11.0",
#   "basedpyright~=1.34.0",
#   "ruff~=0.14.7",
#   "ruff-lsp~=0.0.62",
# ]
# ///

# import json
import sys
import tomllib
from pathlib import Path
from typing import Any

from autocodegen._internal.config import ProjectConfig, ProjectConfigWorkspace
from autocodegen._internal.expand import generate


class AcgDirectoryNotFoundError(RuntimeError):
    """Raised when a required 'acg' directory is missing."""


def find_top_project_root(start_path: Path | None = None) -> Path | None:
    """Find the topmost directory containing a subdirectory named 'acg'.

    Traverses upward from the starting path (default: current working directory)
    and returns the highest-level (closest to root) directory that has an 'acg'
    subdirectory.

    Args:
        start_path: The directory to start searching from. Defaults to cwd().

    Returns:
        Path to the topmost directory containing 'acg', or None if not found.

    """
    current: Path = Path.cwd() if start_path is None else start_path

    parents = (
        current.parents
        if current.name == "acg"
        else (current, *current.parents)
    )

    # Collect matches from parents (deepest to shallowest)
    matches = [p for p in parents if (p / "acg").is_dir()]

    # Check filesystem root separately
    root = Path(current.root)
    if (root / "acg").is_dir():
        matches.append(root)

    # Return the topmost (first in the list, since we went bottom-up)
    return matches[-1] if matches else None


def find_workspace_acg_dirs(
    acg_project_root: Path,
    acg_config_workspace: ProjectConfigWorkspace | None,
) -> list[Path]:
    """Return a list of all 'acg' directories in the autocodegen workspace.

    This function locates:
    - The top-level 'acg' directory directly under ``acg_project_root``
    - An 'acg' directory inside each workspace member defined in
      ``acg_config_workspace.members``

    The search is performed relative to the provided paths without resolving
    symlinks, preserving the logical structure.

    Args:
        acg_project_root: The root directory of the autocodegen project.
        acg_config_workspace: Configuration object containing the list of
            workspace members (relative paths) or None (same as empty list).

    Returns:
        List of ``Path`` objects pointing to all discovered 'acg' directories,
        ordered top-down (top-level 'acg' first, followed by member 'acg'
        directories in the order of ``members``).

    Raises:
        AcgDirectoryNotFoundError: If the top-level 'acg' directory or any
            member's 'acg' directory does not exist or is not a directory.

    """
    acg_dir_top = acg_project_root / "acg"
    if not acg_dir_top.is_dir():
        msg = f'Missing top-level "acg" directory in project root: {acg_project_root}'
        raise AcgDirectoryNotFoundError(msg)

    acg_dirs: list[Path] = [acg_dir_top]

    members = acg_config_workspace.members if acg_config_workspace else []

    for member in members:
        acg_dir = acg_project_root / member / "acg"
        if not acg_dir.is_dir():
            msg = f'Missing "acg" directory in workspace member: {member}'
            raise AcgDirectoryNotFoundError(msg)
        acg_dirs.append(acg_dir)

    return acg_dirs


def load_acg_config(
    acg_config_path: Path,
) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny]
    """Load the ACG configuration from a TOML file.

    If the file exists, it is parsed using :func:`tomllib.load` and the
    resulting dictionary is returned. If the file does not exist or is not a
    regular file, an empty dictionary is returned.

    This behaviour allows callers to treat the configuration as optional without
    needing separate existence checks.

    Args:
        acg_config_path: Path to the ``acg/config.toml`` configuration file.

    Returns:
        The parsed configuration as a dictionary. Keys are strings; values may
        be of any type supported by TOML. Returns an empty dict if the file is
        missing.

    Note:
        The function opens the file in binary mode (``"rb"``) as required by
        :mod:`tomllib`.

    """
    if (acg_config_path).is_file():
        with Path.open(acg_config_path, "rb") as f:
            return tomllib.load(f)
    else:
        return {}


def is_project_root_empty_or_only_has_templates(
    project_root: Path,
    templates_root: Path,
) -> bool:
    """Check if project_root is either empty or contains only templates_root.

    Returns True if project_root contains:
      - no entries at all, or
      - exactly one entry and that entry is templates_root
        (compared by resolved path)

    Hidden files, regular files, subdirectories — all are considered.
    Exceptions (permission denied, not a directory, etc.) are not caught.

    Args:
        project_root: Path to the project root directory.
        templates_root: Path to the templates root directory.

    Returns:
        True if empty or contains exactly one item matching templates_root.
        False otherwise.

    """
    # Will raise FileNotFoundError / NotADirectoryError / PermissionError etc.
    children = list(project_root.iterdir())

    match len(children):
        case 0:
            return True
        case 1:
            item = children[0].resolve(strict=True)
            templates = templates_root.resolve(strict=True)
            return item == templates
        case _:
            return False


def main() -> int:
    """Run main function."""
    top_project_root = find_top_project_root()

    if top_project_root is None:
        print(
            (
                "fatal: not a autocodegen repository "
                "(or any of the parent directories): acg"
            ),
            file=sys.stderr,
        )
        return 1

    top_templates_root = top_project_root / "acg"
    top_project_config = ProjectConfig.load(
        load_acg_config(top_templates_root / "config.toml"),
        templates_root=top_templates_root,
    )

    is_top_project_root_empty = is_project_root_empty_or_only_has_templates(
        top_project_root,
        top_templates_root,
    )

    top_workspace_init = (
        top_project_config.workspace.init
        if top_project_config.workspace
        else False
    )

    try:
        acg_dirs = find_workspace_acg_dirs(
            top_project_root,
            top_project_config.workspace,
        )

    except AcgDirectoryNotFoundError as exc:
        print(f"fatal: {exc}", file=sys.stderr)
        return 1

    # print(
    #     "+++",
    #     json.dumps(
    #         project_config.model_dump(mode="json"),
    #         indent=2,
    #         ensure_ascii=False,
    #     ),
    # )

    workspace_project_configs = [
        ProjectConfig.load(
            load_acg_config(acg_dir / "config.toml"),
            templates_root=acg_dir,
            project_name_default=top_project_config.autocodegen.project_name,
        )
        for acg_dir in acg_dirs[1:]
    ]

    for workspace_project_config in workspace_project_configs:
        if workspace_project_config.workspace is not None:
            print(
                (
                    "fatal: workspace project may not contain "
                    "nested workspaces: "
                    f"{workspace_project_config.autocodegen.project_root}"
                ),
                file=sys.stderr,
            )
            return 1

    workspace_configs = [top_project_config]
    workspace_configs.extend(workspace_project_configs)

    for top_project_config in workspace_configs:
        # print(
        #     "***",
        #     json.dumps(
        #         project_config.model_dump(mode="json"),
        #         indent=2,
        #         ensure_ascii=False,
        #     ),
        # )

        for [name, config] in top_project_config.templates.items():
            init = (
                is_top_project_root_empty
                or top_workspace_init
                or config.bootstrap.init
            )

            generate(
                name,
                config,
                top_project_config,
                workspace_configs,
                init=init,
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
