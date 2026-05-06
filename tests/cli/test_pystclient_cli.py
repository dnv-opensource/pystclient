# pyright: reportPrivateUsage=false
import sys
from argparse import ArgumentError
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from pystclient.cli import __main__
from pystclient.cli.__main__ import _argparser, _get_version, main

# *****Test commandline interface (CLI)************************************************************


@dataclass()
class CliArgs:
    # Expected default values for the CLI arguments when pystclient gets called via the commandline
    quiet: bool = False
    verbose: bool = False
    log: str | None = None
    log_level: str = field(default_factory=lambda: "WARNING")
    # config_file: str | None = field(default_factory=lambda: "test_config_file")
    config: str | None = None
    login: bool = False
    delete_token: bool = False


@pytest.mark.parametrize(
    "inputs, expected",
    [
        ([], ArgumentError),
        (["--login"], CliArgs(login=True)),
        (["-l"], ArgumentError),
        (["--delete-token"], CliArgs(delete_token=True)),
        (["-d"], ArgumentError),
        (["--login", "--delete-token"], ArgumentError),
        (["--config", "test_config_file"], ArgumentError),
        (["--config", "test_config_file", "--login"], CliArgs(config="test_config_file", login=True)),
        (
            ["--config", "test_config_file", "--delete-token"],
            CliArgs(config="test_config_file", delete_token=True),
        ),
        (["-c", "test_config_file"], ArgumentError),
        (["-c", "test_config_file", "--login"], CliArgs(config="test_config_file", login=True)),
        (
            ["-c", "test_config_file", "--delete-token"],
            CliArgs(config="test_config_file", delete_token=True),
        ),
        (["test_config_file"], ArgumentError),
        (["--login", "-q"], CliArgs(login=True, quiet=True)),
        (["--login", "--quiet"], CliArgs(login=True, quiet=True)),
        (["--login", "-v"], CliArgs(login=True, verbose=True)),
        (["--login", "--verbose"], CliArgs(login=True, verbose=True)),
        (["--login", "-qv"], ArgumentError),
        (["--login", "--log", "logFile"], CliArgs(login=True, log="logFile")),
        (["--login", "--log"], ArgumentError),
        (["--login", "--log-level", "INFO"], CliArgs(login=True, log_level="INFO")),
        (["--login", "--log-level"], ArgumentError),
    ],
)
def test_cli(
    inputs: list[str],
    expected: CliArgs | type,
    monkeypatch: pytest.MonkeyPatch,
):
    # sourcery skip: no-conditionals-in-tests
    # sourcery skip: no-loop-in-tests
    # Prepare
    monkeypatch.setattr(sys, "argv", ["pystclient", *inputs])
    parser = _argparser()
    # Execute
    if isinstance(expected, CliArgs):
        args_expected: CliArgs = expected
        args = parser.parse_args()
        # Assert args
        for key in args_expected.__dataclass_fields__:
            assert args.__getattribute__(key) == args_expected.__getattribute__(key)
    elif issubclass(expected, Exception):
        exception: type = expected
        # Assert that expected exception is raised
        with pytest.raises((exception, SystemExit)):
            _ = parser.parse_args()
    else:
        raise TypeError


@pytest.mark.parametrize("flag", ["-V", "--version"])
def test_cli_version(
    flag: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    # Prepare
    monkeypatch.setattr(sys, "argv", ["pystclient", flag])
    parser = _argparser()
    # Execute & Assert
    with pytest.raises(SystemExit) as exc_info:
        _ = parser.parse_args()
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert _get_version() in captured.out


# *****Ensure the CLI correctly configures logging*************************************************


@dataclass()
class ConfigureLoggingArgs:
    # Values that main() is expected to pass to ConfigureLogging() by default when configuring the logging
    log_level_console: str = field(default_factory=lambda: "WARNING")
    log_file: Path | None = None
    log_level_file: str = field(default_factory=lambda: "WARNING")


@pytest.mark.parametrize(
    "inputs, expected",
    [
        ([], ArgumentError),
        (["--login"], ConfigureLoggingArgs()),
        (["--login", "-q"], ConfigureLoggingArgs(log_level_console="ERROR")),
        (["--login", "--quiet"], ConfigureLoggingArgs(log_level_console="ERROR")),
        (["--login", "-v"], ConfigureLoggingArgs(log_level_console="INFO")),
        (
            ["--login", "--verbose"],
            ConfigureLoggingArgs(log_level_console="INFO"),
        ),
        (["--login", "-qv"], ArgumentError),
        (
            ["--login", "--log", "logFile"],
            ConfigureLoggingArgs(log_file=Path("logFile")),
        ),
        (["--login", "--log"], ArgumentError),
        (
            ["--login", "--log-level", "INFO"],
            ConfigureLoggingArgs(log_level_file="INFO"),
        ),
        (["--login", "--log-level"], ArgumentError),
    ],
)
def test_logging_configuration(
    inputs: list[str],
    expected: ConfigureLoggingArgs | type,
    monkeypatch: pytest.MonkeyPatch,
):
    # sourcery skip: no-conditionals-in-tests
    # sourcery skip: no-loop-in-tests
    # Prepare
    monkeypatch.setattr(sys, "argv", ["pystclient", *inputs])
    args: ConfigureLoggingArgs = ConfigureLoggingArgs()

    def fake_configure_logging(
        log_level_console: str,
        log_file: Path | None,
        log_level_file: str,
    ):
        args.log_level_console = log_level_console
        args.log_file = log_file
        args.log_level_file = log_level_file

    def fake_run(
        config_file: Path | None = None,
        *,
        login: bool,
        delete_token: bool,
    ):
        pass

    monkeypatch.setattr(__main__, "configure_logging", fake_configure_logging)
    monkeypatch.setattr(__main__, "run", fake_run)
    # Execute
    if isinstance(expected, ConfigureLoggingArgs):
        args_expected: ConfigureLoggingArgs = expected
        main()
        # Assert args
        for key in args_expected.__dataclass_fields__:
            assert args.__getattribute__(key) == args_expected.__getattribute__(key)
    elif issubclass(expected, Exception):
        exception: type = expected
        # Assert that expected exception is raised
        with pytest.raises((exception, SystemExit)):
            main()
    else:
        raise TypeError


# *****Ensure the CLI correctly invokes the API****************************************************


@dataclass()
class ApiArgs:
    # Values that main() is expected to pass to run() by default when invoking the API
    # config_file: Path = field(default_factory=lambda: Path("test_config_file"))
    config_file: Path | None = None
    login: bool = False
    delete_token: bool = False


@pytest.mark.parametrize(
    "inputs, expected",
    [
        ([], ArgumentError),
        (["--login"], ApiArgs(login=True)),
        (["-l"], ArgumentError),
        (["--delete-token"], ApiArgs(delete_token=True)),
        (["-d"], ArgumentError),
        (["--login", "--delete-token"], ArgumentError),
        (["--config", "test_config_file"], ArgumentError),
        (["--config", "test_config_file", "--login"], ApiArgs(config_file=Path("test_config_file"), login=True)),
        (
            ["--config", "test_config_file", "--delete-token"],
            ApiArgs(config_file=Path("test_config_file"), delete_token=True),
        ),
        (["-c", "test_config_file"], ArgumentError),
        (["-c", "test_config_file", "--login"], ApiArgs(config_file=Path("test_config_file"), login=True)),
        (
            ["-c", "test_config_file", "--delete-token"],
            ApiArgs(config_file=Path("test_config_file"), delete_token=True),
        ),
        (["test_config_file"], ArgumentError),
    ],
)
def test_api_invokation(
    inputs: list[str],
    expected: ApiArgs | type,
    monkeypatch: pytest.MonkeyPatch,
):
    # sourcery skip: no-conditionals-in-tests
    # sourcery skip: no-loop-in-tests
    # Prepare
    monkeypatch.setattr(sys, "argv", ["pystclient", *inputs])
    args: ApiArgs = ApiArgs()

    def fake_run(
        config_file: Path,
        *,
        login: bool = False,
        delete_token: bool = False,
    ):
        args.config_file = config_file
        args.login = login
        args.delete_token = delete_token

    monkeypatch.setattr(__main__, "run", fake_run)
    # Execute
    if isinstance(expected, ApiArgs):
        args_expected: ApiArgs = expected
        main()
        # Assert args
        for key in args_expected.__dataclass_fields__:
            assert args.__getattribute__(key) == args_expected.__getattribute__(key)
    elif issubclass(expected, Exception):
        exception: type = expected
        # Assert that expected exception is raised
        with pytest.raises((exception, SystemExit)):
            main()
    else:
        raise TypeError
