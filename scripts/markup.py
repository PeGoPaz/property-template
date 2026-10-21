"""HTML helpers shared by build.py and reviews.py."""

import html


class BuildError(Exception):
    pass


class Markup(str):
    """HTML that is already safe, inserted by render() without escaping."""


def attr(value: str) -> str:
    return html.escape(value, quote=True)


def indent(text: str, spaces: int) -> str:
    pad = ' ' * spaces
    return '\n'.join(pad + line if line else line for line in text.split('\n'))
