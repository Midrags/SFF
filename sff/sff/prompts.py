# SteaMidra - Steam game setup and manifest tool (SFF)
# Copyright (c) 2025-2026 Midrag (https://github.com/Midrags)
#
# This file is part of SteaMidra.
#
# SteaMidra is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SteaMidra is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SteaMidra.  If not, see <https://www.gnu.org/licenses/>.


import gc
from enum import Enum
from pathlib import Path


_gui_backend = None


def set_gui_backend(backend):
    global _gui_backend
    _gui_backend = backend


def convert_to_path(x):
    return Path(x.strip("\"' "))


def _clean_prompt(prompt):
    """Dark voodoo I cooked that actually works??? `prompt_select` leaks way less now"""
    from InquirerPy.base import BaseComplexPrompt, BaseListPrompt
    from InquirerPy.prompts.input import InputPrompt

    if isinstance(prompt, BaseComplexPrompt):
        prompt.application.reset()  # pyright: ignore[reportUnknownMemberType]
        prompt.application = None  # type: ignore
    if isinstance(prompt, BaseListPrompt):
        prompt.content_control.reset()
        prompt.content_control = None  # type: ignore
    del prompt
    gc.collect()


def prompt_select(
    msg: str,
    choices,
    default = None,
    fuzzy = False,
    cancellable = False,
    exclude = None,
    **kwargs,
):
    if _gui_backend:
        return _gui_backend.prompt_select(
            msg, choices, default=default, fuzzy=fuzzy,
            cancellable=cancellable, exclude=exclude, **kwargs,
        )
    from InquirerPy import inquirer
    from InquirerPy.base.control import Choice

    new_choices = []
    for c in choices:
        if isinstance(c, Enum):
            if exclude and c in exclude:
                continue
            new_choices.append(Choice(value=c, name=c.value))
        elif isinstance(c, Choice):
            new_choices.append(c)
        elif isinstance(c, tuple):
            if len(c) == 2:  # type: ignore
                new_choices.append(Choice(value=c[1], name=c[0]))  # type: ignore
        else:
            new_choices.append(Choice(value=c, name=str(c)))
    if cancellable:
        new_choices.append(Choice(value=None, name="[Back]"))
    cmd = inquirer.fuzzy if fuzzy else inquirer.select  # type: ignore
    obj = cmd(
        message=msg,
        choices=new_choices,
        default=default,
        vi_mode=False if fuzzy else True,
        **kwargs,
    )
    result = obj.execute()
    _clean_prompt(obj)
    return result


def prompt_dir(
    msg: str,
    custom_check = None,
    custom_msg = None,
):
    if _gui_backend:
        return _gui_backend.prompt_dir(msg, custom_check=custom_check, custom_msg=custom_msg)
    def validator(raw_input):
        path = convert_to_path(raw_input)
        if not (path.exists() and path.is_dir()):
            return False
        if custom_check and not custom_check(path):
            return False
        return True
    return prompt_text(
        msg,
        validator=validator,
        invalid_msg=custom_msg if custom_msg else "Doesn't exist or not a folder.",
        filter=convert_to_path,
    )


def prompt_file(msg, allow_blank = False):
    if _gui_backend:
        return _gui_backend.prompt_file(msg, allow_blank=allow_blank)
    is_file = lambda x: (
        convert_to_path(x).exists() and convert_to_path(x).is_file()
    ) or (True if allow_blank and x == "" else False)
    return prompt_text(
        msg,
        validator=is_file,
        invalid_msg="Doesn't exist or not a file.",
        filter=convert_to_path,
    )


def prompt_text(
    msg: str,
    validator = None,
    invalid_msg = "Invalid input",
    instruction = "",
    long_instruction = "",
    filter = None,
):
    if _gui_backend:
        return _gui_backend.prompt_text(
            msg, validator=validator, invalid_msg=invalid_msg,
            instruction=instruction, long_instruction=long_instruction,
            filter=filter,
        )
    from InquirerPy import inquirer

    obj = inquirer.text(
        msg,
        validate=validator,
        invalid_message=invalid_msg,
        instruction=instruction,
        long_instruction=long_instruction,
        filter=filter,
    )
    res = obj.execute()
    _clean_prompt(obj)
    return res


def prompt_secret(
    msg: str,
    validator = None,
    invalid_msg = "Invalid input",
    instruction = "",
    long_instruction = "",
):
    if _gui_backend:
        return _gui_backend.prompt_secret(
            msg, validator=validator, invalid_msg=invalid_msg,
            instruction=instruction, long_instruction=long_instruction,
        )
    from InquirerPy import inquirer

    obj = inquirer.secret(
        message=msg,
        transformer=lambda _: "[hidden]",
        validate=validator,
        invalid_message=invalid_msg,
        instruction=instruction,
        long_instruction=long_instruction,
    )
    res = obj.execute()
    _clean_prompt(obj)
    return res


def prompt_confirm(
    msg: str,
    true_msg = None,
    false_msg = None,
    default = True,
):
    if _gui_backend:
        return _gui_backend.prompt_confirm(
            msg, true_msg=true_msg, false_msg=false_msg, default=default,
        )
    # inquirer.confirm exists but I prefer this
    return prompt_select(
        msg,
        [
            (true_msg if true_msg else "Yes", True),
            (false_msg if false_msg else "No", False),
        ],
        default=default
    )
