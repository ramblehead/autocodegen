# Hey Emacs, this is -*- coding: utf-8; mode: python -*-

import importlib.util
import os
import platform
import shutil
import subprocess
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, Self, TypedDict, cast

from mako.lookup import TemplateLookup  # type: ignore reportMissingStubs

from . import utils
from .config import Config, config_default

if TYPE_CHECKING:
    from collections.abc import Callable

template_ext = ".mako"
rename_ext = ".rename"


class ProjectContext(TypedDict):
    path: Path
    config: Config


def config_ensure_valid(config: Config, project_path: Path) -> Config:
    if "project_name" not in config or config["project_name"] is None:
        config["project_name"] = project_path.name

    return config


def create_project_context(*, path: Path, config: Config) -> ProjectContext:
    return {
        "path": path,
        "config": config_ensure_valid(config, path),
    }


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


def expand_template(
    in_template_path: Path,
    out_file_path: Path,
    *,
    ctx: ProjectContext,
) -> None:
    template_lookup = TemplateLookup(directories=[in_template_path.parent])

    template = template_lookup.get_template(  # type: ignore unknownMemberType
        in_template_path.name,
    )

    file_out_str: str = template.render(  # type: ignore unknownMemberType
        config=ctx["config"],
        utils=utils,
    )

    try:
        with Path.open(out_file_path, "w") as file:
            file.write(file_out_str)
    except OSError as cause:
        print(f"Error writing to file: {cause}")


def get_paths_by_ext(path: Path, ext: str, *, with_dirs: bool) -> list[Path]:
    result: list[Path] = []

    for root, dir_names, file_names in os.walk(path):
        names = file_names
        if with_dirs:
            names += dir_names

        result += [
            Path(root) / file_name
            for file_name in file_names
            if file_name.endswith(ext)
        ]

    return result


def expand_all_project_templates(
    *,
    delete_templates: bool,
    ctx: ProjectContext,
) -> None:
    in_template_files = get_paths_by_ext(
        ctx["path"],
        template_ext,
        with_dirs=False,
    )

    if in_template_files:
        print("Expanding from templates:")

    for in_template_file in in_template_files:
        out_file_path_str = str(in_template_file)
        if out_file_path_str.endswith(template_ext):
            out_file_path_str = out_file_path_str[: -len(template_ext)]

        out_file_path = Path(out_file_path_str)

        print(f"  {out_file_path}")
        expand_template(in_template_file, out_file_path, ctx=ctx)
        shutil.copystat(in_template_file, out_file_path)

    if delete_templates:
        for in_template_file in in_template_files:
            in_template_file.unlink()


def get_rename_destination_path(
    orig_path_str: str,
    *,
    delete_origins: bool,
    ctx: ProjectContext,
) -> str:
    holder_path_str = orig_path_str[: -len(rename_ext)]

    renamer_path = Path(f"{holder_path_str}.rename.py")
    if renamer_path.is_file():
        reanamer_mod = import_module_from_file(renamer_path)

        # if hasattr(reanamer_mod, "rename"):
        reaname: Callable[[Config, ModuleType], str] = reanamer_mod.rename
        renamed_path = renamer_path.parent / reaname(ctx["config"], utils)

        if delete_origins:
            del reanamer_mod, reaname
            renamer_path.unlink()

        return str(renamed_path)

    return holder_path_str


def process_renames(*, delete_origins: bool, ctx: ProjectContext) -> None:
    orig_paths = get_paths_by_ext(
        ctx["path"],
        rename_ext,
        with_dirs=True,
    )

    if delete_origins:
        dirs_to_move: list[tuple[str, str]] = []

        # Move files first
        for orig_path in orig_paths:
            orig_path_str = str(orig_path)

            dest_path_str = get_rename_destination_path(
                orig_path_str,
                delete_origins=delete_origins,
                ctx=ctx,
            )

            if not orig_path.is_dir():
                shutil.move(orig_path, dest_path_str)
                # shutil.copy2(orig_path, dest_path_str)
                # orig_path.unlink()
            else:
                dirs_to_move.append((orig_path_str, dest_path_str))

        # Then move directories
        for orig_dir_path_str, dest_dir_path_str in dirs_to_move:
            shutil.move(orig_dir_path_str, dest_dir_path_str)

    else:
        for orig_path in orig_paths:
            orig_path_str = str(orig_path)

            dest_path_str = get_rename_destination_path(
                orig_path_str,
                delete_origins=delete_origins,
                ctx=ctx,
            )

            if orig_path.is_dir():
                shutil.copytree(orig_path, dest_path_str)
            else:
                # shutil.copy(orig_path, dest_path_str)
                # shutil.copystat(orig_path, dest_path_str)
                shutil.copy2(orig_path, dest_path_str)


def process_expand(*, delete_origins: bool, ctx: ProjectContext) -> None:
    expand_all_project_templates(delete_templates=delete_origins, ctx=ctx)
    process_renames(delete_origins=delete_origins, ctx=ctx)


def expand(
    implode_script_path_str: str,
    config: dict[str, Any] | None = None,
) -> None:
    config_user = cast(Config | None, config)
    ctx = create_project_context(
        path=Path(implode_script_path_str).parent,
        config=config_default
        if config_user is None
        else {**config_default, **config_user},
    )

    process_expand(delete_origins=True, ctx=ctx)


def expand_and_implode(
    implode_script_path_str: str,
    config: dict[str, Any] | None = None,
) -> None:
    config_user = cast(Config | None, config)
    ctx = create_project_context(
        path=Path(implode_script_path_str).parent,
        config=config_default if config_user is None else config_default | config_user,
    )

    process_expand(delete_origins=True, ctx=ctx)

    boom = "💥" if (platform.system() != "Windows") else "*Boom!*"
    print(f"\nImploding... {boom}")

    # Wipe python cache directories
    pyc_paths = get_paths_by_ext(ctx["path"], "__pycache__", with_dirs=True)
    pyc_path_strs = [str(p) for p in pyc_paths]

    subprocess.Popen(
        'python -c "'
        "import shutil;"
        f'[shutil.rmtree(pyc, ignore_errors=True) for pyc in {pyc_path_strs}];"',
        shell=True,
    )

    if platform.system() == "Windows":
        os.chdir(ctx["path"])
        sd_path = Path(__file__).parent
        os.startfile(  # noqa: S606 # type: ignore[reportGeneralTypeIssues]
            str(sd_path / "ms-implode.bat"),
        )
    else:
        rh_template_dir_path = ctx["path"] / "rh_template"
        subprocess.Popen(
            'python -c "'
            "import shutil;"
            f"shutil.rmtree('{rh_template_dir_path}', ignore_errors=True);"
            f"shutil.os.remove('{implode_script_path_str}');\"",
            shell=True,
        )

    input("\nPress Enter to exit...")
