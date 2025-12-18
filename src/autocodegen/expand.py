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

    from .config import Config

TEMPLATE_EXT = ".mako"
RENAME_EXT = ".rename"

# ACG_NAME_DEFAULT = "acg"


class ProjectContext(NamedTuple):
    acg_template_path: Path
    config: Config


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
    ctx: ProjectContext,
    orig_path_str: str,
    *,
    delete_origins: bool,
) -> str:
    holder_path_str = orig_path_str[: -len(RENAME_EXT)]

    renamer_path = Path(f"{holder_path_str}.rename.py")
    if renamer_path.is_file():
        renamer_mod = import_module_from_file(renamer_path)

        reaname = cast(
            "Callable[[Config, ModuleType], str]",
            renamer_mod.rename,
        )

        renamed_path = renamer_path.parent / reaname(ctx.config, utils)

        if delete_origins:
            renamer_path.unlink(missing_ok=True)

        return str(renamed_path)

    return holder_path_str


def expand_template(
    in_template_path: Path,
    out_file_path: Path,
    *,
    ctx: ProjectContext,
) -> None:
    template_lookup = TemplateLookup(directories=[in_template_path.parent])

    template = template_lookup.get_template(  # pyright: ignore [reportUnknownMemberType, reportUnknownVariableType]
        in_template_path.name,
    )

    file_out_str = (  # pyright: ignore [reportUnknownVariableType]
        template.render(  # pyright: ignore [reportUnknownMemberType]
            config=ctx.config,
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
    project_root: Path,
    ext: str,
    with_dirs: bool,
    acg_root: Path,
) -> list[Path]:
    result: list[Path] = []

    for root, dir_names, file_names in os.walk(project_root):
        names = file_names
        if with_dirs:
            names += dir_names

        result += [
            Path(root) / file_name
            for file_name in file_names
            if (
                file_name.endswith(ext)
                and not (Path(root) / file_name).is_relative_to(acg_root)
            )
        ]

    return result


def expand_all_project_templates(
    ctx: ProjectContext,
    *,
    delete_templates: bool,
) -> None:
    in_template_files = get_paths_by_ext(
        project_root=ctx.config["project_root"],
        ext=TEMPLATE_EXT,
        with_dirs=False,
        acg_root=ctx.config["acg_templates"],
    )

    if in_template_files:
        print("Expanding from templates:")

    for in_template_file in in_template_files:
        out_file_path_str = str(in_template_file)
        out_file_path_str = out_file_path_str.removesuffix(TEMPLATE_EXT)

        out_file_path = Path(out_file_path_str)

        print(f"  {out_file_path}")
        expand_template(in_template_file, out_file_path, ctx=ctx)
        shutil.copystat(in_template_file, out_file_path)

    if delete_templates:
        for in_template_file in in_template_files:
            in_template_file.unlink()


def process_renames(ctx: ProjectContext, *, delete_origins: bool) -> None:
    orig_paths = get_paths_by_ext(
        project_root=ctx.config["project_root"],
        ext=RENAME_EXT,
        with_dirs=True,
        acg_root=ctx.acg_template_path,
    )

    if delete_origins:
        dirs_to_move: list[tuple[str, str]] = []

        # Move files first
        for orig_path in orig_paths:
            orig_path_str = str(orig_path)

            dest_path_str = get_rename_destination_path(
                ctx,
                orig_path_str,
                delete_origins=delete_origins,
            )

            if not orig_path.is_dir():
                _ = shutil.move(orig_path, dest_path_str)
                # shutil.copy2(orig_path, dest_path_str)
                # orig_path.unlink()
            else:
                dirs_to_move.append((orig_path_str, dest_path_str))

        # Then move directories
        for orig_dir_path_str, dest_dir_path_str in dirs_to_move:
            _ = shutil.move(orig_dir_path_str, dest_dir_path_str)

    else:
        for orig_path in orig_paths:
            orig_path_str = str(orig_path)

            dest_path_str = get_rename_destination_path(
                ctx,
                orig_path_str,
                delete_origins=delete_origins,
            )

            if orig_path.is_dir():
                _ = shutil.copytree(orig_path, dest_path_str)
            else:
                # shutil.copy(orig_path, dest_path_str)
                # shutil.copystat(orig_path, dest_path_str)
                _ = shutil.copy2(orig_path, dest_path_str)


def generate(acg_template_name: str, config: Config) -> None:
    acg_template_path = config["acg_templates"] / acg_template_name
    bootstrap_path = acg_template_path / "bootstrap"

    print(bootstrap_path)

    ctx = ProjectContext(
        acg_template_path,
        config,
    )

    def _ignore_acg_root(_path: str, names: list[str]) -> set[str]:
        result: set[str] = set()

        for name in names:
            target_path = config["project_root"] / name
            if target_path == config["acg_templates"]:
                print(f"Preventing acg root override {target_path!s}")
                result.add(name)

        return result

    if bootstrap_path.exists():
        _ = shutil.copytree(
            bootstrap_path,
            config["project_root"],
            dirs_exist_ok=True,
            ignore=_ignore_acg_root,
        )

        expand_all_project_templates(ctx, delete_templates=True)
        process_renames(ctx, delete_origins=True)

        # Wipe python cache directories
        pyc_paths = get_paths_by_ext(
            project_root=config["project_root"],
            ext="__pycache__",
            with_dirs=True,
            acg_root=config["acg_templates"],
        )
        pyc_path_strs = [str(p) for p in pyc_paths]

        _ = subprocess.Popen(
            (
                'python -c "'
                "import shutil;"
                f'[shutil.rmtree(pyc, ignore_errors=True) for pyc in {pyc_path_strs}];"'
            ),
            shell=True,
        )


# def expand_and_implode(
#     acg_path: str | Path,
#     config: dict[str, Any] | None = None,
# ) -> None:
#     acg_path = Path(acg_path)
#     config_user = cast("Config | None", config)
#     ctx = create_project_context(
#         path=Path(acg_path).parent,
#         config=(
#             config_default
#             if config_user is None
#             else config_default | config_user
#         ),
#     )

#     process_expand(delete_origins=True, ctx=ctx)

#     boom = "💥" if (platform.system() != "Windows") else "*Boom!*"
#     print(f"\nImploding... {boom}")

#     # Wipe python cache directories
#     pyc_paths = get_paths_by_ext(ctx["path"], "__pycache__", with_dirs=True)
#     pyc_path_strs = [str(p) for p in pyc_paths]

#     subprocess.Popen(
#         'python -c "'
#         "import shutil;"
#         f'[shutil.rmtree(pyc, ignore_errors=True) for pyc in {pyc_path_strs}];"',
#         shell=True,
#     )

#     if platform.system() == "Windows":
#         os.chdir(ctx["path"])
#         sd_path = Path(__file__).parent
#         os.startfile(  # noqa: S606 # type: ignore[reportGeneralTypeIssues]
#             str(sd_path / "ms-implode.bat"),
#         )
#     else:
#         rh_template_dir_path = ctx["path"] / "rh_template"
#         subprocess.Popen(
#             'python -c "'
#             "import shutil;"
#             f"shutil.rmtree('{rh_template_dir_path}', ignore_errors=True);"
#             f"shutil.os.remove('{implode_script_path_str}');\"",
#             shell=True,
#         )

#     input("\nPress Enter to exit...")
