# Hey Emacs, this is -*- coding: utf-8; mode: python -*-

from typing import TypedDict


class Config(TypedDict):
    # When None use project directory name as project_name
    project_name: str | None


config_default: Config = {
    "project_name": None,
}
