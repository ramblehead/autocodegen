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

from autocodegen import ProjectConfig, generate


def find_topmost_acg(start_path: Path | None = None) -> Path | None:
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

    current: Path = start_path.resolve(strict=True)

    # Collect matches from parents (deepest to shallowest)
    matches = [p / "acg" for p in current.parents if (p / "acg").is_dir()]

    # Check filesystem root separately
    root = Path(current.root)
    if (root / "acg").is_dir():
        matches.append(root / "acg")

    # Return the topmost (first in the list, since we went bottom-up)
    return matches[-1] if matches else None


def main() -> int:
    """Run main function."""
    acg_dir = find_topmost_acg()

    if acg_dir is None:
        print(
            (
                "fatal: not a autocodegen repository "
                "(or any of the parent directories): acg"
            ),
            file=sys.stderr,
        )
        return 1

    with Path.open(acg_dir / "config.toml", "rb") as f:
        project_config = ProjectConfig.load(tomllib.load(f), acg_dir=acg_dir)
        print(
            json.dumps(
                project_config.model_dump(mode="json"),
                indent=2,
                ensure_ascii=False,
            ),
        )

    # print(f"project_name = {project_config.autocodegen.project_name}")
    # print(f"project_root = {project_config.autocodegen.project_root}")
    # print(f"templates_root = {project_config.autocodegen.templates_root}")

    for [name, config] in project_config.templates.items():
        generate(
            project_name=project_config.autocodegen.project_name,
            template_name=name,
            target_root=project_config.autocodegen.project_root
            / config.target_root,
            templates_root=acg_dir,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
