#  Copyright (c) 2026 DNV AS.
#
#  SPDX-License-Identifier: MPL-2.0
#
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Utility functions for pystclient."""

import json
import logging
import random
import string
import uuid
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from typing import Any

from edn_format import Keyword
from requests import Response

from pystclient.exception import APIResponseError, PyStclientError, UnknownError

logger = logging.getLogger(__name__)


@contextmanager
def handle_exception() -> Generator[None, Any, Any]:
    """Context manager to handle exceptions and convert unknown exceptions to PyStclientError."""
    try:
        yield
    except PyStclientError:
        raise
    except Exception as e:
        raise UnknownError("Unknown error Occurred") from e


def without_none_values(m: dict[Any, Any]) -> dict[Any, Any]:
    """Traverse a dictionary tree recursively and remove all keys whose values are None.

    Args:
        m: A dictionary to traverse.

    Returns:
        A new dictionary without None values.
    """
    return {k: without_none_values(v) if isinstance(v, dict) else v for k, v in m.items() if v is not None and v != {}}


def stringify_keys(m: dict[Any, Any] | Mapping[Any, Any]) -> dict[str, Any]:
    """Traverse a dictionary or Mapping tree recursively and convert `Keyword` keys to strings.

    Returns a new dict that contains the converted keys.

    Args:
        m: An input Mapping or dict to traverse.

    Returns:
        A new dictionary with all Keywords converted to strings.
    """
    return {
        k.name if isinstance(k, Keyword) else str(k): (  # pyright: ignore [reportUnknownMemberType]
            stringify_keys(v) if isinstance(v, (dict, Mapping)) else v
        )
        for k, v in m.items()
    }


def raise_if_not_ok(resp: Response) -> Response:
    """Raise APIResponseError if response is not OK.

    Args:
        resp: HTTP response to check.

    Returns:
        The original response if OK.

    Raises:
        APIResponseError: If response is not OK.
    """
    if not resp.ok:
        raise APIResponseError(resp)
    return resp


def raise_if_not_json_ok(resp: Response) -> Response:
    """Raise APIResponseError if response is not JSON and OK.

    Args:
        resp: HTTP response to check.

    Returns:
        The original response if OK and JSON.

    Raises:
        APIResponseError: If response is not JSON and OK.
    """
    if not ("application/json" in resp.headers.get("Content-Type", "") and resp.ok):
        raise APIResponseError(resp)
    return resp


def random_string(length: int = 8) -> str:
    """Generate a random string of ASCII letters.

    Args:
        length: Length of the random string. Defaults to 8.

    Returns:
        Random string of ASCII letters.
    """
    return "".join(random.choice(string.ascii_letters) for _ in range(length))


def pprint_map(m: dict[Any, Any]) -> None:
    """Pretty print a dictionary as JSON.

    Args:
        m: Dictionary to print.
    """
    logger.info(json.dumps(m, indent=2))


def to_uuid(uuid_: str | uuid.UUID) -> uuid.UUID:
    """Convert string to UUID or return UUID as-is.

    Args:
        uuid_: UUID as string or UUID object.

    Returns:
        UUID object.
    """
    return uuid.UUID(uuid_) if isinstance(uuid_, str) else uuid_


def merge_dicts(dict1: dict[Any, Any], dict2: dict[Any, Any]) -> dict[Any, Any]:
    """Recursively merge dict2 into dict1.

    Args:
        dict1: Base dictionary to merge into.
        dict2: Dictionary to merge from.

    Returns:
        Merged dictionary.
    """
    for k, v2 in dict2.items():
        if k in dict1:
            v1 = dict1[k]
            if isinstance(v1, dict) and isinstance(v2, dict):
                _ = merge_dicts(v1, v2)
            else:
                dict1[k] = v2
        else:
            dict1[k] = v2
    return dict1
