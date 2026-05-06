#!/usr/bin/env python

#  Copyright (c) 2026 DNV AS.
#
#  SPDX-License-Identifier: MPL-2.0
#
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""pystclient command line interface."""

import argparse
import logging
import pprint
from importlib import metadata
from pathlib import Path

from pystclient.api import run
from pystclient.utils.logging import configure_logging

logger = logging.getLogger(__name__)


def _get_version() -> str:
    """Return the installed package version, or a safe fallback if unavailable."""
    try:
        return metadata.version("pystclient")
    except metadata.PackageNotFoundError:
        # Fallback when package metadata is not available (e.g. running from source)
        return "pystclient (version unknown)"


def _argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pystclient",
        usage="%(prog)s [options [args]]",
        epilog="_________________pystclient___________________",
        prefix_chars="-",
        add_help=True,
        description="pystclient [options]",
    )

    _ = parser.add_argument(
        "-c",
        "--config",
        metavar="config_file",
        type=str,
        help="name of the file containing the pystclient configuration.",
        required=False,
    )

    login_logout = parser.add_mutually_exclusive_group(required=True)

    _ = login_logout.add_argument(
        "--login",
        action="store_true",
        help="login to Veracity Identity to retrieve and store an access token to a local cache",
        default=False,
        required=False,
    )

    _ = login_logout.add_argument(
        "--delete-token",
        action="store_true",
        help="delete an access token stored in a local cache",
        default=False,
        required=False,
    )

    console_verbosity = parser.add_mutually_exclusive_group(required=False)

    _ = console_verbosity.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help=("console output will be quiet."),
        default=False,
    )

    _ = console_verbosity.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help=("console output will be verbose."),
        default=False,
    )

    _ = parser.add_argument(
        "--log",
        action="store",
        type=str,
        help="name of log file. If specified, this will activate logging to file.",
        default=None,
        required=False,
    )

    _ = parser.add_argument(
        "--log-level",
        action="store",
        type=str,
        help="log level applied to logging to file.",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="WARNING",
        required=False,
    )

    _ = parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=_get_version(),
    )

    return parser


def main() -> None:
    """Entry point for console script as configured in pyproject.toml.

    Runs the command line interface and parses arguments and options entered on the console.
    """
    parser = _argparser()
    args = parser.parse_args()

    # Configure Logging
    # ..to console
    log_level_console: str = "WARNING"
    if any([args.quiet, args.verbose]):
        log_level_console = "ERROR" if args.quiet else log_level_console
        log_level_console = "INFO" if args.verbose else log_level_console
    # ..to file
    log_file: Path | None = Path(args.log) if args.log else None
    log_level_file: str = args.log_level
    configure_logging(log_level_console, log_file, log_level_file)

    config_file: Path | None = None
    if args.config:
        config_file = Path(args.config)

        # Check whether pystclient config file exists
        if not config_file.is_file():
            logger.error(f"pystclient.py: File {config_file} not found.")
            return

    login: bool = args.login
    delete_token: bool = args.delete_token

    # Print the parsed commandline arguments for documentation and debugging purposes.
    # The arguments will be split into one argument per line, if possible.
    # If extracting a mapping from `args` fails, fall back to its string representation.
    _indent: str = " " * 13
    try:
        _arg_mapping = vars(args)
    except TypeError:
        _arg_mapping = {"args": str(args)}
    _formatted_args = pprint.pformat(_arg_mapping, sort_dicts=True)
    _indented_args = "\n".join(f"{_indent}{line}" for line in _formatted_args.splitlines())
    logger.info(
        "Start pystclient with following arguments:\n%s\n",
        _indented_args,
    )

    # Invoke API
    run(
        config_file=config_file,
        login=login,
        delete_token=delete_token,
    )


if __name__ == "__main__":
    main()
