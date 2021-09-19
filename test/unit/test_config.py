import pytest
import tempfile

import transient.configuration as configuration
import transient.args as args
import transient.cli as cli

from typing import Dict, Any


def create_test_run_config(contents: Dict[Any, Any]) -> configuration.RunConfig:
    return configuration.RunConfig(
        configuration._Config(configuration.RunSchema(), contents)
    )


def create_test_start_config(contents: Dict[Any, Any]) -> configuration.StartConfig:
    return configuration.StartConfig(
        configuration._Config(configuration.StartSchema(), contents)
    )


def create_test_create_config(contents: Dict[Any, Any]) -> configuration.CreateConfig:
    return configuration.CreateConfig(
        configuration._Config(configuration.CreateSchema(), contents)
    )


def id_func(val):
    if not isinstance(val, str) or "\n" in val:
        return ""
    else:
        return val


TEMP_CONFIG_FILE = tempfile.NamedTemporaryFile()


@pytest.mark.parametrize(
    ("description", "config", "transient_args", "qemu_args", "expected"),
    (
        (
            "Basic config with no commandline",
            """
            ssh-console=true
            """,
            ["run", "example-image", "--config", TEMP_CONFIG_FILE.name],
            [],
            create_test_run_config(
                {"image": "example-image", "qemu_args": [], "ssh_console": True}
            ),
        ),
        (
            "Config with QEMU args",
            """
            qemu_args = ["-smp", "2"]
            """,
            ["run", "example-image", "--config", TEMP_CONFIG_FILE.name],
            ["-m", "1G"],
            create_test_run_config(
                {"image": "example-image", "qemu_args": ["-smp", "2", "-m", "1G"]}
            ),
        ),
        (
            "Config with overriden args",
            """
            ssh-command="config command"
            """,
            [
                "run",
                "example-image",
                "--config",
                TEMP_CONFIG_FILE.name,
                "--ssh-command",
                "final",
            ],
            [],
            create_test_run_config(
                {"image": "example-image", "ssh_command": "final", "qemu_args": []}
            ),
        ),
        (
            "Config using underscore names",
            """
            qemu_bin_name="foo"
            """,
            ["run", "example-image", "--config", TEMP_CONFIG_FILE.name],
            [],
            create_test_run_config(
                {"image": "example-image", "qemu_bin_name": "foo", "qemu_args": []}
            ),
        ),
    ),
    ids=id_func,
)
def test_config_flag(description, config, transient_args, qemu_args, expected):
    TEMP_CONFIG_FILE.seek(0)
    TEMP_CONFIG_FILE.write(config.encode("utf-8"))
    TEMP_CONFIG_FILE.flush()

    parsed = args.TransientArgs(transient_args, qemu_args, cli.CLI_COMMAND_MAPPINGS)
    generated = configuration.create_transient_run_config(parsed)
    assert generated == expected


@pytest.mark.parametrize(
    ("description", "create_config", "start_config", "expected"),
    (
        (
            "Basic create config with empty start config",
            create_test_create_config({"image": "example-image", "qemu_args": []}),
            create_test_start_config({"qemu_args": []}),
            create_test_run_config({"image": "example-image", "qemu_args": []}),
        ),
        (
            "Basic create config with basic start config",
            create_test_create_config({"image": "example-image", "qemu_args": []}),
            create_test_start_config({"qemu_args": [], "ssh_console": True}),
            create_test_run_config(
                {"image": "example-image", "qemu_args": [], "ssh_console": True}
            ),
        ),
        (
            "Start config with additional QEMU arguments",
            create_test_create_config(
                {"image": "example-image", "qemu_args": ["-smp", "2"]}
            ),
            create_test_start_config({"qemu_args": ["-m", "1G"],}),
            create_test_run_config(
                {"image": "example-image", "qemu_args": ["-smp", "2", "-m", "1G"],}
            ),
        ),
        (
            "Start config with overriding arguments",
            create_test_create_config(
                {"image": "example-image", "qemu_args": [], "ssh_console": False}
            ),
            create_test_start_config({"qemu_args": [], "ssh_console": True}),
            create_test_run_config(
                {"image": "example-image", "qemu_args": [], "ssh_console": True}
            ),
        ),
    ),
    ids=id_func,
)
def test_run_config_from_create_and_start(
    description, create_config, start_config, expected
):
    generated = configuration.run_config_from_create_and_start(
        create_config, start_config
    )

    assert generated == expected
