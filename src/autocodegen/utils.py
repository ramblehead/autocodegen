# Hey Emacs, this is -*- coding: utf-8; mode: python -*-

import re
from typing import cast


def make_words(*human_names: str) -> list[str]:
    result: list[str] = []
    for human_name in human_names:
        result += [word.lower() for word in cast(str, re.split(r" |-|_", human_name))]
    return result


def kebab_case(*human_names: str) -> str:
    return "-".join(make_words(*human_names))


def snake_case(*human_names: str) -> str:
    return "_".join(make_words(*human_names))


def upcase_initial(s: str) -> str:
    return s[:1].upper() + s[1:]


def all_caps_case(*human_names: str) -> str:
    result = ""
    words = make_words(*human_names)

    for word in words:
        result += word.upper()

    return result


def camel_case(*human_names: str) -> str:
    result = ""
    words = make_words(*human_names)

    if words:
        result += words[0]

    for word in words[1:]:
        result += word[:1].upper() + word[1:]

    return result


def pascal_case(*human_names: str) -> str:
    return upcase_initial(camel_case(*human_names))
