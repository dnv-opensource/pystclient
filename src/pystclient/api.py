#  Copyright (c) 2026 DNV AS.
#
#  SPDX-License-Identifier: MPL-2.0
#
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""pystclient API."""

import logging
import os
from pathlib import Path

from dictIO import DictReader

__all__ = ["PyStclientProcess", "run"]

from pystclient.clients import PyStclient
from pystclient.settings import STC_CLIENT_HOME

logger = logging.getLogger(__name__)


def run(
    config_file: str | os.PathLike[str] | None = None,
    *,
    login: bool = False,
    delete_token: bool = False,
) -> None:
    """Run the pystclient process.

    Args:
        config_file: File containing the pystclient configuration. Defaults to None.
        login: If True, login to Veracity Identity to retrieve and store an access
            token to a local cache. Defaults to False.
        delete_token: If True, delete an access token stored in a local cache.
            Defaults to False.

    Raises:
        FileNotFoundError: If config_file was specified but does not exist.
    """
    # Make sure config_file argument is of type Path. If not, cast it to Path type.
    _config_file: Path | None = None
    if config_file:
        _config_file = config_file if isinstance(config_file, Path) else Path(config_file)

        # Check whether config file exists
        if not _config_file.exists():
            logger.error(f"run: File {_config_file} not found.")
            raise FileNotFoundError(_config_file)

    if login:
        logger.info(
            msg=(
                "option 'login' is True. "
                "pystclient will login to Veracity Identity to retrieve and store an access token to a local cache."
            ),
        )

    if delete_token:
        logger.info(
            msg="option 'delete_token' is True. pystclient will delete an access token stored in a local cache."
        )

    process = PyStclientProcess(
        config_file=_config_file,
        login=login,
        delete_token=delete_token,
    )
    process.run()

    return


class PyStclientProcess:
    """Top level class encapsulating the pystclient process."""

    _do_login: bool = False
    _delete_token: bool = False

    def __init__(
        self,
        config_file: Path | None = None,
        *,
        login: bool = False,
        delete_token: bool = False,
    ) -> None:
        self._config_file: Path | None = None
        self._do_login: bool = login
        self._delete_token: bool = delete_token
        if config_file:
            self._config_file = config_file
            self._read_config_file(config_file)
        return

    @property
    def config_file(self) -> Path | None:
        """Return the configuration file path."""
        return self._config_file

    @property
    def do_login(self) -> bool:
        """Return the login flag."""
        return self._do_login

    @property
    def delete_token(self) -> bool:
        """Return the delete token flag."""
        return self._delete_token

    def run(self) -> None:
        """Run the pystclient process."""
        client = PyStclient()
        if self._do_login:
            _ = client.authenticate()
            print("Login successful!\n")  # noqa: T201
        elif self._delete_token:
            token_path: Path = STC_CLIENT_HOME / "token"
            if not token_path.exists() or not token_path.is_file():
                logger.debug("No access token found to remove.")
                return
            Path.unlink(token_path, missing_ok=True)
            logger.info("Removed access token!")
        return

    def _read_config_file(self, config_file: Path) -> None:
        """Read the config file."""
        config = DictReader.read(config_file)
        if "login" in config:
            self._do_login = config["login"]
        if "delete-token" in config:
            self._delete_token = config["delete-token"]
        return
