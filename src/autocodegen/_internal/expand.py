# Hey Emacs, this is -*- coding: utf-8 -*-

import importlib.util
import os
import shutil
import subprocess
from enum import StrEnum
from inspect import isfunction
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple, Self, cast

from mako.lookup import (  # pyright: ignore [reportMissingTypeStubs]
    TemplateLookup,
)

from . import utils

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType

    from .config import ProjectConfig, ProjectConfigTemplate

TEMPLATE_MAKO_EXT = ".mako"


class AcgExt(StrEnum):
    GEN = ".gen.py"  # Renewable generator
    GEN_ONCE = ".gen1.py"  # Once only generator (e.g. initial)

    REN = ".rename"  # File to rename
    RENR = ".rename.py"  # Renamer - new name producer

    REN_ONCE = ".ren1"  # File to rename
    RENR_ONCE = ".ren1.py"  # Renamer - new name producer

    FRA = ".fra.py"  # Fragment


class GenExt(StrEnum):
    GEN = AcgExt.GEN
    GEN_ONCE = AcgExt.GEN_ONCE


class RenExt(StrEnum):
    REN = AcgExt.REN
    REN_ONCE = AcgExt.REN_ONCE


class Context(NamedTuple):
    template_name: str
    template_config: ProjectConfigTemplate
    project_config: ProjectConfig
    workspace_configs: list[ProjectConfig]
    target_root: Path


type GenerateFunc = Callable[[Context], str]
type RenameFunc = Callable[[Context], str]


class InvalidGeneratorError(Exception):
    """Raised when gen module does not provide a valid interface functions."""


class ModuleDynamicImportError(ModuleNotFoundError):
    """Raised when gen module file cannot be loaded."""

    def __init__(self: Self, module_path: Path) -> None:
        super().__init__(
            f"Failed to import gen module: '{module_path}'",
        )


def import_module_from_file(
    mod_path: Path,
    *,
    mod_name: str | None = None,
) -> ModuleType:
    """Import a module from a file path."""
    if not mod_path.is_file():
        raise ModuleDynamicImportError(mod_path)

    mod_name = mod_name or mod_path.stem
    spec = importlib.util.spec_from_file_location(mod_name, mod_path)

    if spec is None or spec.loader is None:
        raise ModuleDynamicImportError(mod_path)

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise ModuleDynamicImportError(mod_path) from exc

    return module


def import_generate_func(gen_mod_path: Path) -> GenerateFunc:
    gen_mod = import_module_from_file(gen_mod_path)

    generate_func = getattr(gen_mod, "generate", None)
    if not isfunction(generate_func):
        msg = f"Module '{gen_mod_path}' does not define a 'generate' function."
        raise InvalidGeneratorError(msg)

    if generate_func.__code__.co_argcount != 1:
        msg = (
            f"The 'generate' function in '{gen_mod_path}' "
            "must take exactly one parameter (ctx) "
            f"but it has {generate_func.__code__.co_argcount}."
        )
        raise InvalidGeneratorError(msg)

    return cast("Callable[[Context], str]", generate_func)


def get_rename_destination_path(
    ctx: Context,
    orig_path_str: str,
    *,
    delete_renamer: bool,
) -> str:
    dest_path_str = orig_path_str[: -len(AcgExt.REN)]

    renamer_path = Path(f"{dest_path_str}{AcgExt.RENR}")
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

    return dest_path_str


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


def expand_mako(
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


def expand_mako_all(ctx: Context) -> None:
    in_template_files = get_paths_by_ext(
        target_root=ctx.target_root,
        ext=TEMPLATE_MAKO_EXT,
        with_dirs=False,
        templates_root=ctx.project_config.autocodegen.templates_root,
    )

    if in_template_files:
        print("Expanding from mako templates:")

    for in_template_file in in_template_files:
        out_file_path_str = str(in_template_file)
        out_file_path_str = out_file_path_str.removesuffix(TEMPLATE_MAKO_EXT)

        out_file_path = Path(out_file_path_str)

        print(f"  {out_file_path}")
        expand_mako(in_template_file, out_file_path, ctx=ctx)
        shutil.copystat(in_template_file, out_file_path)

    for in_template_file in in_template_files:
        in_template_file.unlink()


def expand_gen(
    ctx: Context,
    gen_mod_path: Path,
    target_file_path: Path,
) -> None:
    generate = import_generate_func(gen_mod_path)

    try:
        target_str = generate(ctx)
    except Exception as exc:
        exc.add_note(f"Failed executing generate(ctx) from {gen_mod_path}")
        raise

    try:
        with Path.open(target_file_path, "w") as file:
            _ = file.write(target_str)
    except Exception as exc:
        exc.add_note(f"Failed writing to target file: {target_file_path}")
        raise


def is_file_in_directory(file_path: Path, dir_path: Path) -> bool:
    """Return True if the file is inside the dir (including subdirectories)."""
    try:
        return file_path.is_relative_to(dir_path)
    except ValueError:  # Rare case, e.g., invalid path on some systems
        return False


def is_project_self_defence(
    project_config: ProjectConfig,
    target_path: Path,
) -> bool:
    if target_path == project_config.autocodegen.templates_root:
        return False

    print("aaa", target_path)
    print("ooo", project_config.autocodegen.templates_root)

    if is_file_in_directory(
        target_path,
        project_config.autocodegen.templates_root,
    ):
        for [
            template_name,
            template_config,
        ] in project_config.templates.items():
            template_path = (
                project_config.autocodegen.templates_root / template_name
            )

            if is_file_in_directory(target_path, template_path):
                return template_config.self_defence

        return True

    return False


def is_workspace_self_defence(ctx: Context, target_path: Path) -> bool:
    for project_config in ctx.workspace_configs:
        if is_project_self_defence(project_config, target_path):
            return True

    return False


def compute_dst_path(src_path: Path, src_root: Path, dst_root: Path) -> Path:
    src_path_abs = src_path.resolve(strict=True)
    src_root_abs = src_root.resolve(strict=True)
    dst_root_abs = dst_root.resolve(strict=True)

    origin_rel = src_path_abs.relative_to(src_root_abs)

    return dst_root_abs / origin_rel


def expand_gen_all(ctx: Context, gen_ext: GenExt) -> None:
    gen_mod_paths = get_paths_by_ext(
        target_root=ctx.target_root,
        ext=gen_ext,
        with_dirs=False,
        templates_root=ctx.project_config.autocodegen.templates_root,
    )

    if gen_mod_paths:
        print(f"Expanding from '{gen_ext}' templates:")

    for gen_mod_path in gen_mod_paths:
        target_file_path_str = str(gen_mod_path).removesuffix(gen_ext)
        target_file_path = Path(target_file_path_str)

        print(f"  {target_file_path}")
        expand_gen(ctx, gen_mod_path, target_file_path)
        shutil.copystat(gen_mod_path, target_file_path)

    for gen_mod_path in gen_mod_paths:
        gen_mod_path.unlink()


def process_renames(ctx: Context, ren_ext: RenExt) -> None:
    templates_root = (
        ctx.project_config.autocodegen.templates_root / ctx.template_name
    )

    orig_paths = get_paths_by_ext(
        target_root=ctx.target_root,
        ext=ren_ext,
        with_dirs=True,
        templates_root=templates_root,
    )

    if orig_paths:
        print(f"Renaming '{ren_ext}':")

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
    template_config: ProjectConfigTemplate,
    project_config: ProjectConfig,
    workspace_configs: list[ProjectConfig],
) -> None:
    templates_root = project_config.autocodegen.templates_root
    template_path = templates_root / template_name
    bootstrap_path = template_path / "bootstrap"

    target_root = (
        project_config.autocodegen.project_root / template_config.target_dir
    )

    print(bootstrap_path)

    ctx = Context(
        template_name,
        template_config,
        project_config,
        workspace_configs,
        target_root,
    )

    def _template_files_to_ignore(path: str, names: list[str]) -> set[str]:
        result: set[str] = set()

        for name in names:
            print("%%%", name)

            src_path = Path(path) / name

            dst_path = compute_dst_path(
                src_path,
                bootstrap_path,
                target_root,
            )

            print(f"*** {src_path} -> {dst_path}")

            if is_workspace_self_defence(ctx, dst_path):
                print(f"Preventing acg templates override {dst_path!s}")
                result.add(name)

            elif not template_config.init:
                if name.endswith((AcgExt.REN_ONCE, AcgExt.RENR_ONCE)):
                    print(
                        (
                            f"Preventing '{AcgExt.REN_ONCE}' or "
                            f"'{AcgExt.RENR_ONCE}' "
                            f"re-init: {src_path!s}"
                        ),
                    )
                    result.add(name)

                if not src_path.is_dir() and name.endswith(AcgExt.GEN_ONCE):
                    print(
                        (
                            f"Preventing '{AcgExt.GEN_ONCE}' "
                            f"re-init: {src_path!s}"
                        ),
                    )
                    result.add(name)

        return result

    if bootstrap_path.exists():
        _ = shutil.copytree(
            bootstrap_path,
            target_root,
            symlinks=True,
            dirs_exist_ok=True,
            ignore_dangling_symlinks=True,
            ignore=_template_files_to_ignore,
        )

        expand_mako_all(ctx)

        if template_config.init:
            expand_gen_all(ctx, GenExt.GEN_ONCE)
            process_renames(ctx, RenExt.REN_ONCE)

        expand_gen_all(ctx, GenExt.GEN)
        process_renames(ctx, RenExt.REN)

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
