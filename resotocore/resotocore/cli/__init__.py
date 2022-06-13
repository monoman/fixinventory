from argparse import ArgumentParser
from typing import TypeVar, Union, Any, Callable, AsyncIterator, NoReturn, Optional, Awaitable

from aiostream.core import Stream
from parsy import Parser, regex

from resotolib.parse_util import (
    make_parser,
    literal_dp,
    equals_dp,
    json_value_dp,
    space_dp,
    double_quote_dp,
    double_quoted_string_part_or_esc_dp,
    single_quoted_string_part_or_esc_dp,
    single_quote_dp,
    any_non_white_space_string,
    comma_p,
)
from resotocore.model.graph_access import Section
from resotocore.types import JsonElement

T = TypeVar("T")
# Allow the function to return either a coroutine or the result directly
Result = Union[T, Awaitable[T]]
JsGen = Union[Stream, AsyncIterator[JsonElement]]
# A sink function takes a stream and creates a result
Sink = Callable[[JsGen], Awaitable[T]]


@make_parser
def key_value_parser() -> Parser:
    key = yield literal_dp
    yield equals_dp
    value = yield json_value_dp
    return key, value


# name=value test=true -> {name: value, test: true}
key_values_parser: Parser = key_value_parser.sep_by(comma_p | space_dp).map(dict)
# anything that is not: | " ' ; \
cmd_token = regex("[^|\"';\\\\]+")
# single and double-quoted string are maintained with quotes: "foo"->"foo", 'foo'->'foo'
# all characters inside the quoted string are not parsed
double_quoted_string = double_quote_dp + double_quoted_string_part_or_esc_dp + double_quote_dp
single_quoted_string = single_quote_dp + single_quoted_string_part_or_esc_dp + single_quote_dp
# same as above, but the surrounding quotes are not preserved: "foo"->foo, 'foo'->foo
double_quoted_raw_string = double_quote_dp >> double_quoted_string_part_or_esc_dp << double_quote_dp
single_quoted_raw_string = single_quote_dp >> single_quoted_string_part_or_esc_dp << single_quote_dp
# parse \| \" \' \; and unescape it \| -> |
escaped_token = regex("\\\\[|\"';]").map(lambda x: x[1])
# a command are tokens until EOF or pipe (all characters will be preserved)
cmd_with_args_parser = (escaped_token | double_quoted_string | single_quoted_string | cmd_token).at_least(1).concat()

# argument parser which will read the argument list while removing single and double quotes
# command line arguments: foo "bla: 'foo = bla' -> [foo, bla, foo = bla]
args_parts_unquoted_parser = (
    escaped_token | double_quoted_raw_string | single_quoted_raw_string | any_non_white_space_string
).sep_by(space_dp)

# argument parser which will read the argument list while removing single quotes
# Example: "--a \"a or b\" --b 'b or c' --c c d" -> ["--a", "\"a or b\"", "--b", "b or c", "--c", "c", "d"]
args_parts_parser = (
    escaped_token | double_quoted_string | single_quoted_raw_string | any_non_white_space_string
).sep_by(space_dp, min=1)


def strip_quotes(string: str) -> str:
    res = string.strip()
    if res:
        first = res[0]
        if first in "'\"":
            res = res[1 : len(res) - 1] if res.startswith(first) and res.endswith(first) else res  # noqa: E203
    return res


# check if a is a json node element
def is_node(a: Any) -> bool:
    return "id" in a and Section.reported in a if isinstance(a, dict) else False


# check if given object is a json edge element
def is_edge(a: Any) -> bool:
    return "from" in a and "to" in a if isinstance(a, dict) else False


class NoExitArgumentParser(ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise AttributeError(f"Could not parse arguments: {message}")

    def exit(self, status: int = 0, message: Optional[str] = None) -> NoReturn:
        msg = message if message else "unknown"
        raise AttributeError(f"Could not parse arguments: {msg}")
