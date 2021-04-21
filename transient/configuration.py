"""Supports the creation and validation of Transient-run configurations
"""

import logging
import os
import toml

from marshmallow import Schema, fields, post_load, pre_load, ValidationError
from typing import Any, Dict, List, MutableMapping, Optional

from . import qemu


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
            invalid_option = invalid_option.replace("_", "-")
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


class Config(Dict[Any, Any]):
    """Creates an argument dictionary that allows dot notation to access values

    Example:

        >>> args = Config({'arg1': 1, 'arg2': 2})
        >>> args['arg1'] == args.arg1

    """

    def __getattr__(self, attr: Any) -> Any:
        return self.get(attr)

    def __setattr__(self, key: Any, value: Any) -> None:
        self.__setitem__(key, value)

    def __delattr__(self, item: Any) -> None:
        self.__delitem__(item)


class _TransientConfigSchema(Schema):
    """Defines a common schema for the Transient configurations and validates
       the fields during deserialization
    """

    # marshmallow's decorator pre_load() is untyped, forcing
    # remove_unset_options() to be untyped. Therefore, we ignore it to
    # silence the type checker
    @pre_load  # type: ignore
    def remove_unset_options(
        self, config: Dict[Any, Any], **kwargs: Dict[Any, Any]
    ) -> Dict[Any, Any]:
        """Removes any option that was not set in the command line
        """
        config_without_unset_options = {}
        for option, value in config.items():
            if _option_was_set_in_cli(config[option]):
                config_without_unset_options[option] = value

        return config_without_unset_options

    # marshmallow's decorator post_load() is untyped, forcing create_args()
    # to be untyped. Therefore, we ignore it to silence the type checker
    @post_load  # type: ignore
    def create_config(self, data: Dict[Any, Any], **kwargs: Dict[Any, Any]) -> Config:
        """Returns the Config dictionary after a schema is loaded and validated
        """
        return Config(**data)


class _TransientBuildConfigSchema(_TransientConfigSchema):
    """Defines the schema for the Transient-build configuration and validates
       the fields during deserialization
    """

    image_backend = fields.Str(allow_none=True)
    name = fields.Str(allow_none=True)
    qmp_timeout = fields.Int(missing=qemu.QMP_DEFAULT_TIMEOUT, allow_none=True)
    ssh_timeout = fields.Int(missing=90, allow_none=True)
    local = fields.Bool(missing=False)
    file = fields.Str(allow_none=True)
    build_dir = fields.Str(allow_none=False)


class _TransientSshConfigSchema(_TransientConfigSchema):
    """Defines the schema for the Transient-ssh configuration and validates
       the fields during deserialization

       Note that this class is a wrapper to maintain symmetry with the other
       schemas.
    """

    name = fields.Str(allow_none=False)
    wait = fields.Bool(missing=False)
    ssh_command = fields.Str(allow_none=True)
    ssh_bin_name = fields.Str(missing="ssh", allow_none=True)
    ssh_timeout = fields.Int(missing=90, allow_none=True)
    ssh_user = fields.Str(missing="vagrant", allow_none=True)


class _TransientListImageConfigSchema(_TransientConfigSchema):
    """Defines the schema for the Transient-list-image configuration and
       validates the fields during deserialization

       Note that this class is a wrapper to maintain symmetry with the other
       schemas.
    """

    image = fields.List(fields.Str(), missing=[])
    image_frontend = fields.Str(allow_none=True)
    image_backend = fields.Str(allow_none=True)
    name = fields.Str(allow_none=True)


class _TransientListVmConfigSchema(_TransientConfigSchema):
    """Defines the schema for the Transient-list-vm configuration and
       validates the fields during deserialization

       Note that this class is a wrapper to maintain symmetry with the other
       schemas.
    """

    name = fields.Str(allow_none=True)
    with_ssh = fields.Bool(missing=False)


class _TransientDeleteConfigSchema(_TransientListImageConfigSchema):
    """Defines the schema for the Transient-delete configuration and validates
       the fields during deserialization
    """

    force = fields.Bool(missing=False)


class _TransientRunConfigSchema(_TransientConfigSchema):
    """Defines the schema for the Transient-run configuration and validates the
       fields during deserialization
    """

    image = fields.List(fields.Str(), missing=[])
    image_frontend = fields.Str(allow_none=True)
    image_backend = fields.Str(allow_none=True)
    name = fields.Str(allow_none=True)
    config = fields.Str(allow_none=True)
    copy_in_before = fields.List(fields.Str(), missing=[])
    copy_out_after = fields.List(fields.Str(), missing=[])
    copy_timeout = fields.Int(allow_none=True)
    prepare_only = fields.Bool(missing=False)
    qemu_bin_name = fields.Str(allow_none=True)
    qemu_args = fields.List(fields.Str(), missing=[])
    qmp_timeout = fields.Int(missing=qemu.QMP_DEFAULT_TIMEOUT, allow_none=True)
    shutdown_timeout = fields.Int(missing=20)
    ssh_net_driver = fields.Str(missing="virtio-net-pci")
    ssh_command = fields.Str(allow_none=True)
    ssh_bin_name = fields.Str(missing="ssh", allow_none=True)
    ssh_port = fields.Int(allow_none=True)
    ssh_timeout = fields.Int(missing=90, allow_none=True)
    ssh_user = fields.Str(missing="vagrant", allow_none=True)
    ssh_console = fields.Bool(missing=False)
    ssh_with_serial = fields.Bool(missing=False)
    ssh_option = fields.List(fields.Str(), missing=[])
    shared_folder = fields.List(fields.Str(), missing=[])
    sftp_bin_name = fields.Str(missing="sftp-server", allow_none=True)
    no_virtio_scsi = fields.Bool(missing=False)


def _option_was_set_in_cli(option: Any) -> bool:
    """Returns True if an option was set in the command line
    """
    if option is None or option == () or option is False:
        return False

    return True


def _parse_config_file(config_file_path: str) -> MutableMapping[str, Any]:
    """Parses the given config file and returns the contents as a dictionary
    """
    with open(config_file_path) as file:
        config_file = file.read()

    try:
        parsed_config_file = toml.loads(config_file)
    except toml.TomlDecodeError as error:
        raise ConfigFileParsingError(error, config_file_path)

    return parsed_config_file


def _replace_hyphens_with_underscores_in_dict_keys(
    dictionary: Dict[str, Any]
) -> Dict[str, Any]:
    """Replaces hyphens in the dictionary keys with underscores

       This is the expected key format for _TransientConfigSchema
    """
    final_dict = {}
    for k, v in dictionary.items():
        # Perform this method recursively for sub-directories
        if isinstance(dictionary[k], dict):
            new_v = _replace_hyphens_with_underscores_in_dict_keys(v)
            final_dict[k.replace("-", "_")] = new_v
        else:
            final_dict[k.replace("-", "_")] = v

    return final_dict


def _expand_environment_variables_in_dict_values(
    dictionary: Dict[str, Any]
) -> Dict[str, Any]:
    """Expands environment variables in the strings
    """
    final_dict = {}  # type: Dict[str, Any]
    for k, v in dictionary.items():
        # Perform this method recursively for sub-directories
        if isinstance(v, dict):
            final_dict[k] = _expand_environment_variables_in_dict_values(v)
        elif isinstance(v, str):
            final_dict[k] = os.path.expandvars(v)
        else:
            final_dict[k] = v

    return final_dict


def _reformat_dict(dictionary: Dict[str, Any]) -> Dict[str, Any]:
    """Reformats the dictionary using a formatting-pipeline
    """
    return _replace_hyphens_with_underscores_in_dict_keys(
        _expand_environment_variables_in_dict_values(dictionary)
    )


def _load_config_file(config_file_path: str) -> Config:
    """Reformats and validates the config file
    """
    parsed_config = _parse_config_file(config_file_path)

    reformatted_config = _reformat_dict(parsed_config["transient"])
    reformatted_config["qemu_args"] = parsed_config["qemu"]["qemu-args"]

    transient_config_schema = _TransientRunConfigSchema()

    try:
        config: Config = transient_config_schema.load(reformatted_config)
    except ValidationError as error:
        raise ConfigFileOptionError(error, config_file_path)

    return config


def _consolidate_cli_args_and_config_file(cli_args: Dict[Any, Any]) -> Dict[Any, Any]:
    """Consolidates and returns the CLI arguments and the configuration file

       Note that the CLI arguments take precedence over the configuration file
    """
    config = _load_config_file(cli_args["config"])

    for option, value in config.items():
        if (
            option == "qemu_args" and cli_args[option] == ()
        ) or not _option_was_set_in_cli(cli_args[option]):
            cli_args[option] = value

    return cli_args


def _create_transient_config_with_schema(
    config: Dict[Any, Any], schema: _TransientConfigSchema
) -> Config:
    """Creates and validates the Config to be used by Transient given the
       CLI arguments and schema
    """
    try:
        validated_config: Config = schema.load(config)
    except ValidationError as error:
        raise CLIArgumentError(error)

    return validated_config


def create_transient_build_config(cli_args: Dict[Any, Any]) -> Config:
    """Creates and validates the Config to be used by Transient-build given the
       CLI arguments
    """
    schema = _TransientBuildConfigSchema()

    return _create_transient_config_with_schema(cli_args, schema)


def create_transient_ssh_config(cli_args: Dict[Any, Any]) -> Config:
    """Creates and validates the Config to be used by Transient-ssh given the
       CLI arguments
    """
    schema = _TransientSshConfigSchema()

    return _create_transient_config_with_schema(cli_args, schema)


def create_transient_list_image_config(cli_args: Dict[Any, Any]) -> Config:
    """Creates and validates the Config to be used by Transient-list-image given
       the CLI arguments
    """
    schema = _TransientListImageConfigSchema()

    return _create_transient_config_with_schema(cli_args, schema)


def create_transient_list_vm_config(cli_args: Dict[Any, Any]) -> Config:
    """Creates and validates the Config to be used by Transient-list-vm given
       the CLI arguments
    """
    schema = _TransientListVmConfigSchema()

    return _create_transient_config_with_schema(cli_args, schema)


def create_transient_delete_config(cli_args: Dict[Any, Any]) -> Config:
    """Creates and validates the Config to be used by Transient-delete given
       the CLI arguments
    """
    schema = _TransientDeleteConfigSchema()

    return _create_transient_config_with_schema(cli_args, schema)


def create_transient_run_config(cli_args: Dict[Any, Any]) -> Config:
    """Creates and validates the Config to be used by Transient-run
       given the CLI arguments and, if specified, a config file

       Note that the CLI arguments take precedence over the config file
    """
    if cli_args["config"]:
        config = _consolidate_cli_args_and_config_file(cli_args)
    else:
        config = cli_args

    schema = _TransientRunConfigSchema()

    return _create_transient_config_with_schema(config, schema)
