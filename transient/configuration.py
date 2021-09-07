import toml

import argparse
import marshmallow
from marshmallow import Schema, fields, ValidationError
from typing import (
    Any,
    Optional,
    Union,
    cast,
    Dict,
    Type,
    Mapping,
    NewType,
)

from . import args


class ConfigFileParsingError(Exception):
    """Raised when a parsing error is encountered while loading the
       configuration file
    """

    inner: toml.TomlDecodeError
    path: str

    def __init__(self, error: toml.TomlDecodeError, path: str) -> None:
        self.inner = error
        self.path = path

    def __str__(self) -> str:
        return f"Invalid configuration file '{self.path}'\n  {self.inner}"


class ConfigFileOptionError(Exception):
    """Raised when an invalid configuration option value is encountered in the
       configuration file
    """

    inner: ValidationError
    path: str

    def __init__(self, error: ValidationError, path: str) -> None:
        self.inner = error
        self.path = path

    def _line_number_of_option_in_config_file(self, option: str) -> Optional[int]:
        """Returns the line number where the option is found in the config file
        """
        with open(self.path) as config_file:
            for line_number, line in enumerate(config_file, start=1):
                if option in line:
                    return line_number

        return None

    def __str__(self) -> str:
        msg = f"Invalid configuration file '{self.path}'"
        for invalid_option, errors in self.inner.normalized_messages().items():  # type: ignore
            # Revert the option to its preformatted state
            line_number = self._line_number_of_option_in_config_file(invalid_option)

            formatted_errors = " ".join(errors)
            formatted_line_number = str(line_number) if line_number is not None else ""
            msg += f"\n  [line {formatted_line_number}]: {invalid_option}: {formatted_errors}"
        return msg


class CLIArgumentError(Exception):
    """Raised when an invalid command line argument is encountered
    """

    inner: ValidationError

    def __init__(self, error: ValidationError) -> None:
        self.inner = error

    def __str__(self) -> str:
        msg = "Invalid command line:"
        for arg, errors in self.inner.normalized_messages().items():  # type: ignore
            errors = " ".join(errors)
            msg += f"\n  {arg}: {errors}"
        return msg


def schema_from_argument_parser(parser: argparse.ArgumentParser) -> Type[Schema]:
    def arg_to_field(arg: argparse.Action) -> fields.Field:
        TYPE_TO_FIELD = {
            int: fields.Int,
            str: fields.Str,
            bool: fields.Bool,
            float: fields.Float,
        }

        # If no type is specified, use the type of default
        if arg.type is not None:
            assert isinstance(arg.type, type)
            field = TYPE_TO_FIELD[arg.type]
        else:
            if arg.default is not None:
                field = TYPE_TO_FIELD[type(arg.default)]
            elif arg.const is not None:
                field = TYPE_TO_FIELD[type(arg.const)]
            else:
                raise RuntimeError(f"No type, const, or default: {arg}")

        # If this is an append action, we really want a list of these fields
        if isinstance(arg, argparse._AppendAction) or arg.nargs in ("*", "+"):
            return fields.List(field, missing=arg.default, allow_none=True)

        return cast(fields.Field, field(missing=arg.default, allow_none=True))

    class_name = "".join([word.capitalize() for word in parser.prog.split()]) + "Schema"
    return cast(
        Type[Schema],
        type(
            class_name,
            (Schema,),
            {
                arg.dest: arg_to_field(arg)
                for arg in parser._actions
                if arg.dest not in ("help", "verbose")
            },
        ),
    )


CreateSchema = schema_from_argument_parser(args.CREATE_PARSER)
StartSchema = schema_from_argument_parser(args.START_PARSER)
RunSchema = schema_from_argument_parser(args.RUN_PARSER)
ImageBuildSchema = schema_from_argument_parser(args.IMAGE_BUILD_PARSER)


class _Config(Dict[str, Any]):
    """Creates an argument dictionary that allows dot notation to access values

    Example:

        >>> args = Config({'arg1': 1, 'arg2': 2})
        >>> args['arg1'] == args.arg1

    """

    _schema: Schema

    def __init__(self, schema: Schema, data: Mapping[str, Any], **kwargs: Any):
        self._schema = schema
        validated = schema.load(data, **kwargs)

        dict.__init__(self, validated)

        # Remove the setter after we init
        setattr(self, "__setattr__", None)

    def __getattr__(self, attr: Any) -> Any:
        return self[attr]


CreateConfig = NewType("CreateConfig", _Config)
RunConfig = NewType("RunConfig", _Config)
StartConfig = NewType("StartConfig", _Config)
BuildConfig = NewType("BuildConfig", _Config)


def load_config_file(path: str) -> CreateConfig:
    """Parses the given config file and returns the contents as a dictionary
    """
    contents = open(path, "r").read()

    try:
        parsed_config_file = toml.loads(contents)
    except toml.TomlDecodeError as error:
        raise ConfigFileParsingError(error, path)

    try:
        create_config = CreateConfig(
            _Config(schema=CreateSchema(), data=parsed_config_file,)
        )
    except ValidationError as error:
        raise ConfigFileOptionError(error, path)

    return create_config


def create_transient_run_config(cli_args: Dict[Any, Any]) -> RunConfig:
    return RunConfig(_Config(schema=RunSchema(), data=cli_args))


def create_transient_start_config(cli_args: Dict[Any, Any]) -> StartConfig:
    return StartConfig(_Config(schema=StartSchema(), data=cli_args))


def create_transient_create_config(cli_args: Dict[Any, Any]) -> CreateConfig:
    return CreateConfig(_Config(schema=CreateSchema(), data=cli_args))


def create_transient_build_config(cli_args: Dict[Any, Any]) -> BuildConfig:
    return BuildConfig(_Config(schema=ImageBuildSchema(), data=cli_args))


def run_config_from_create_and_start(
    create: CreateConfig, start: StartConfig
) -> RunConfig:
    new_config = dict(create)

    for key, value in start.items():
        if isinstance(value, list) and key in create:
            # Lists are always additive
            new_config[key] = create[key] + value
        elif value is not None:
            # StartConfig's have no defaults, so any value we get that is not
            # None, must have been user specified (and therefore should be
            # what we use in the resulting RunConfig)
            new_config[key] = value

    return RunConfig(_Config(schema=RunSchema(), data=new_config))


def create_config_from_run(run: RunConfig, name: Optional[str] = None) -> CreateConfig:
    new_cfg = dict(run)
    if name is not None:
        new_cfg["name"] = name
    return CreateConfig(
        _Config(schema=CreateSchema(), data=new_cfg, unknown=marshmallow.EXCLUDE)
    )


def config_requires_state(config: RunConfig) -> bool:
    return (
        len(config.copy_in_before) > 0
        or len(config.copy_out_after) > 0
        or config.name is not None
    )


def config_requires_ssh(config: Union[RunConfig, CreateConfig]) -> bool:
    return config_requires_ssh_console(config) or len(config.shared_folder) > 0


def config_requires_ssh_console(config: Union[RunConfig, CreateConfig]) -> bool:
    return (
        config.ssh_console is True
        or config.ssh_command is not None
        or config.ssh_with_serial is True
    )
