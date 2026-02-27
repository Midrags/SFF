import gc
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional, Union

from InquirerPy import inquirer
from InquirerPy.base import BaseComplexPrompt, BaseListPrompt
from InquirerPy.base.control import Choice
from InquirerPy.prompts.input import InputPrompt
from InquirerPy.utils import InquirerPyValidate

_gui_backend: Any = None


def set_gui_backend(backend: Any) -> None:
    global _gui_backend
    _gui_backend = backend


def convert_to_path(x: str):
    return Path(x.strip("\"' "))


def _clean_prompt(prompt: Union[BaseComplexPrompt, InputPrompt]):
    """Dark voodoo I cooked that actually works??? `prompt_select` leaks way less now"""
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
    choices: list[Any],
    default: Optional[Any] = None,
    fuzzy: bool = False,
    cancellable: bool = False,
    exclude: Optional[list[Any]] = None,
    **kwargs: Any,
):
    if _gui_backend:
        return _gui_backend.prompt_select(
            msg, choices, default=default, fuzzy=fuzzy,
            cancellable=cancellable, exclude=exclude, **kwargs,
        )
    new_choices: list[Choice] = []
    for c in choices:
        if isinstance(c, Enum):
            if exclude and c in exclude:
                # Skip excluded choice
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
    custom_check: Optional[Callable[[Path], bool]] = None,
    custom_msg: Optional[str] = None,
) -> Path:
    if _gui_backend:
        return _gui_backend.prompt_dir(msg, custom_check=custom_check, custom_msg=custom_msg)
    def validator(raw_input: str) -> bool:
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


def prompt_file(msg: str, allow_blank: bool = False) -> Path:
    if _gui_backend:
        return _gui_backend.prompt_file(msg, allow_blank=allow_blank)
    is_file: Callable[[str], bool] = lambda x: (
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
    validator: Optional[InquirerPyValidate] = None,
    invalid_msg: str = "Invalid input",
    instruction: str = "",
    long_instruction: str = "",
    filter: Optional[Callable[[str], Any]] = None,
):
    if _gui_backend:
        return _gui_backend.prompt_text(
            msg, validator=validator, invalid_msg=invalid_msg,
            instruction=instruction, long_instruction=long_instruction,
            filter=filter,
        )
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
    validator: Optional[InquirerPyValidate] = None,
    invalid_msg: str = "Invalid input",
    instruction: str = "",
    long_instruction: str = "",
):
    if _gui_backend:
        return _gui_backend.prompt_secret(
            msg, validator=validator, invalid_msg=invalid_msg,
            instruction=instruction, long_instruction=long_instruction,
        )
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
    true_msg: Optional[str] = None,
    false_msg: Optional[str] = None,
    default: bool = True,
) -> bool:
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
