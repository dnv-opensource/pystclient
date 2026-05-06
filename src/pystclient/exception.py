#  Copyright (c) 2026 DNV AS.
#
#  SPDX-License-Identifier: MPL-2.0
#
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Custom exceptions for pystclient."""

from typing import Any

from requests import Response


class PyStclientError(Exception):
    """Base exception class for pystclient errors."""

    def __init__(
        self,
        *args: Any,  # noqa: ANN401
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        super().__init__(*args, **kwargs)


class APIResponseError(PyStclientError):
    """Exception raised for API response errors.

    Attributes:
        status_code: HTTP status code from the response.
        code: Error code from the response.
        message: Error message from the response.
        text: Raw response text.
    """

    status_code: int
    code: str
    message: str
    text: str

    def __init__(self, resp: Response) -> None:
        self.status_code = resp.status_code
        self.text = resp.text

        if "application/json" in resp.headers.get("Content-Type", ""):
            resp_json = resp.json()
            self.code = resp_json.get("code", "Unknown code")
            self.message = resp_json.get("message", "Unknown message")

        super().__init__(
            f"Unexpected error occurred while communicating with the server: {resp.status_code} - {resp.text}"
        )


class UnexpectedResponseDataError(PyStclientError):
    """Exception raised when response data is in an unexpected format."""


class FmuModelNotFoundError(PyStclientError):
    """Exception raised when an FMU model is not found."""


class UnknownError(PyStclientError):
    """Exception raised for unknown errors."""


class ConfigurationNotFoundError(PyStclientError):
    """Exception raised when a configuration is not found."""


class MalformedConnectionsError(PyStclientError):
    """Exception raised when connections data is malformed."""


class MissingVariablesError(PyStclientError):
    """Exception raised when required variables are missing."""
