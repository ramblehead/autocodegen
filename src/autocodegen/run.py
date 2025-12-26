#!/usr/bin/env python
# Hey Emacs, this is -*- coding: utf-8; mode: python -*-

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

import json
import sys
import tomllib
from pathlib import Path
from typing import Any

from autocodegen import ProjectConfig, ProjectConfigWorkspace, generate


class AcgDirectoryNotFoundError(RuntimeError):
    """Raised when a required 'acg' directory is missing."""


def find_acg_project_root(start_path: Path | None = None) -> Path | None:
    """Find the topmost directory containing a subdirectory named 'acg'.

    Traverses upward from the starting path (default: current working directory)
    and returns the highest-level (closest to root) directory that has an 'acg'
    subdirectory.

    Args:
        start_path: The directory to start searching from. Defaults to cwd().

    Returns:
        Path to the topmost directory containing 'acg', or None if not found.

    """
    if start_path is None:
        start_path = Path.cwd()

    current: Path = start_path

    # Collect matches from parents (deepest to shallowest)
    matches = [p for p in current.parents if (p / "acg").is_dir()]

    # Check filesystem root separately
    root = Path(current.root)
    if (root / "acg").is_dir():
        matches.append(root)

    # Return the topmost (first in the list, since we went bottom-up)
    return matches[-1] if matches else None


def find_workspace_acg_dirs(
    acg_project_root: Path,
    acg_config_workspace: ProjectConfigWorkspace,
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
            workspace members (relative paths).

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

    for member in acg_config_workspace.members:
        acg_dir = member / "acg"
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


def main() -> int:
    """Run main function."""
    acg_project_root = find_acg_project_root()

    if acg_project_root is None:
        print(
            (
                "fatal: not a autocodegen repository "
                "(or any of the parent directories): acg"
            ),
            file=sys.stderr,
        )
        return 1

    project_acg_dir = acg_project_root / "acg"
    project_config = ProjectConfig.load(
        load_acg_config(project_acg_dir / "config.toml"),
        acg_dir=project_acg_dir,
    )

    try:
        acg_dirs = find_workspace_acg_dirs(
            acg_project_root,
            project_config.workspace,
        )

    except AcgDirectoryNotFoundError as exc:
        print(f"fatal: {exc}", file=sys.stderr)
        return 1

    except Exception:
        raise

    print(
        json.dumps(
            project_config.model_dump(mode="json"),
            indent=2,
            ensure_ascii=False,
        ),
    )

    project_configs = [project_config]
    project_configs.extend(
        ProjectConfig.load(
            load_acg_config(acg_dir / "config.toml"),
            acg_dir=acg_dir,
        )
        for acg_dir in acg_dirs[1:]
    )

    for project_config in project_configs:
        for [name, config] in project_config.templates.items():
            generate(
                project_name=project_config.autocodegen.project_name,
                template_name=name,
                target_root=project_config.autocodegen.project_root
                / config.target_root,
                templates_root=project_acg_dir,
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
