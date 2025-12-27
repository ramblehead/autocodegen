# Hey Emacs, this is -*- coding: utf-8; mode: python -*-

import importlib.util
import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple, Self, cast

from mako.lookup import (  # pyright: ignore [reportMissingTypeStubs]
    TemplateLookup,
)

from . import utils

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType

    from .config import ProjectConfig

TEMPLATE_MAKO_EXT = ".mako"

# Renewable: Re-run on change (may overwrite target)
TEMPLATE_GEN_EXT = ".gen.py"

# Initial only: Run only if target doesn't exist (safe first-time setup)
TEMPLATE_GEN_ONCE_EXT = ".gen1.py"

# Fragment generation template
FRAGMENT_GEN_EXT = ".fra.py"

RENAME_EXT = ".rename"


class Context(NamedTuple):
    template_name: str
    target_root: Path
    project_config: ProjectConfig
    project_configs: list[ProjectConfig]


class ImportFromFileError(ModuleNotFoundError):
    def __init__(self: Self, module_path: Path) -> None:
        super().__init__(f"Module '{module_path}' not found.")


def import_module_from_file(
    module_path: Path,
    *,
    module_name: str | None = None,
) -> ModuleType:
    module_name = module_name or module_path.stem
    spec = importlib.util.spec_from_file_location(module_name, module_path)

    if spec is None or spec.loader is None:
        raise ImportFromFileError(module_path)

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def get_rename_destination_path(
    ctx: Context,
    orig_path_str: str,
    *,
    delete_renamer: bool,
) -> str:
    holder_path_str = orig_path_str[: -len(RENAME_EXT)]

    renamer_path = Path(f"{holder_path_str}{RENAME_EXT}.py")
    if renamer_path.is_file():
        renamer_mod = import_module_from_file(renamer_path)
        reaname = cast("Callable[[Context], str]", renamer_mod.rename)

        try:
            new_name = reaname(ctx)
        except Exception as exc:
            exc.add_note(f"Failed executing reaname() from {renamer_path}")
            raise

        renamed_path = renamer_path.parent / new_name

        if delete_renamer:
            renamer_path.unlink(missing_ok=True)

        return str(renamed_path)

    return holder_path_str


def expand_template(
    in_template_path: Path,
    out_file_path: Path,
    *,
    ctx: Context,
) -> None:
    template_lookup = TemplateLookup(directories=[in_template_path.parent])

    template = template_lookup.get_template(  # pyright: ignore [reportUnknownMemberType, reportUnknownVariableType]
        in_template_path.name,
    )

    file_out_str = (  # pyright: ignore [reportUnknownVariableType]
        template.render(  # pyright: ignore [reportUnknownMemberType]
            config={
                "project_name": ctx.project_config.autocodegen.project_name,
            },
            utils=utils,
        )
    )

    try:
        with Path.open(out_file_path, "w") as file:
            _ = file.write(
                file_out_str,  # pyright: ignore [reportArgumentType]
            )
    except OSError as cause:
        print(f"Error writing to file: {cause}")


def get_paths_by_ext(
    *,
    target_root: Path,
    ext: str,
    with_dirs: bool,
    templates_root: Path,
) -> list[Path]:
    result: list[Path] = []

    for root, dir_names, file_names in os.walk(target_root):
        names = file_names
        if with_dirs:
            names += dir_names

        result += [
            Path(root) / file_name
            for file_name in file_names
            if (
                file_name.endswith(ext)
                and not (Path(root) / file_name).is_relative_to(templates_root)
            )
        ]

    return result


def expand_all_project_templates(ctx: Context) -> None:
    in_template_files = get_paths_by_ext(
        target_root=ctx.target_root,
        ext=TEMPLATE_MAKO_EXT,
        with_dirs=False,
        templates_root=ctx.project_config.autocodegen.templates_root,
    )

    if in_template_files:
        print("Expanding from templates:")

    for in_template_file in in_template_files:
        out_file_path_str = str(in_template_file)
        out_file_path_str = out_file_path_str.removesuffix(TEMPLATE_MAKO_EXT)

        out_file_path = Path(out_file_path_str)

        print(f"  {out_file_path}")
        expand_template(in_template_file, out_file_path, ctx=ctx)
        shutil.copystat(in_template_file, out_file_path)

    for in_template_file in in_template_files:
        in_template_file.unlink()


def process_renames(ctx: Context) -> None:
    templates_root = (
        ctx.project_config.autocodegen.templates_root / ctx.template_name
    )

    orig_paths = get_paths_by_ext(
        target_root=ctx.target_root,
        ext=RENAME_EXT,
        with_dirs=True,
        templates_root=templates_root,
    )

    if orig_paths:
        print("Renaming:")

    dirs_to_move: list[tuple[str, str]] = []

    # Move files first
    for orig_path in orig_paths:
        orig_path_str = str(orig_path)

        dest_path_str = get_rename_destination_path(
            ctx,
            orig_path_str,
            delete_renamer=True,
        )

        if not orig_path.is_dir():
            print(f"  {orig_path} -> {dest_path_str}")
            _ = shutil.move(orig_path, dest_path_str)
            # shutil.copy2(orig_path, dest_path_str)
            # orig_path.unlink()
        else:
            dirs_to_move.append((orig_path_str, dest_path_str))

    # Then move directories
    for orig_dir_path_str, dest_dir_path_str in dirs_to_move:
        print(f"  {orig_dir_path_str}/ -> {dest_dir_path_str}/")
        _ = shutil.copytree(
            orig_dir_path_str,
            dest_dir_path_str,
            symlinks=True,
            dirs_exist_ok=True,
            ignore_dangling_symlinks=True,
        )
        shutil.rmtree(orig_dir_path_str)


def generate(
    template_name: str,
    target_root: Path,
    project_config: ProjectConfig,
    project_configs: list[ProjectConfig],
) -> None:
    templates_root = project_config.autocodegen.templates_root
    template_path = templates_root / template_name
    bootstrap_path = template_path / "bootstrap"

    print(bootstrap_path)

    ctx = Context(
        template_name,
        target_root,
        project_config,
        project_configs,
    )

    def _ignore_acg_root(_path: str, names: list[str]) -> set[str]:
        result: set[str] = set()

        for name in names:
            target_path = target_root / name
            if target_path == templates_root:
                print(f"Preventing acg root override {target_path!s}")
                result.add(name)

        return result

    if bootstrap_path.exists():
        _ = shutil.copytree(
            bootstrap_path,
            target_root,
            symlinks=True,
            dirs_exist_ok=True,
            ignore_dangling_symlinks=True,
            ignore=_ignore_acg_root,
        )

        expand_all_project_templates(ctx)
        process_renames(ctx)

        # Wipe python cache directories
        pyc_paths = get_paths_by_ext(
            target_root=target_root,
            ext="__pycache__",
            with_dirs=True,
            templates_root=templates_root,
        )

        pyc_path_strs = [str(p) for p in pyc_paths]

        # Remove python cache files
        _ = subprocess.Popen(
            (
                'python -c "'
                "import shutil;"
                f'[shutil.rmtree(pyc, ignore_errors=True) for pyc in {pyc_path_strs}];"'
            ),
            shell=True,
        )

    print()
