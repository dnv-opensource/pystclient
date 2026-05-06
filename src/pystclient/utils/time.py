#  Copyright (c) 2026 DNV AS.
#
#  SPDX-License-Identifier: MPL-2.0
#
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Time-related utility functions for pystclient."""

import datetime
from datetime import UTC
from datetime import datetime as dt

_DATE_FORMAT_1 = "%Y-%m-%dT%H:%M:%S.%fZ"
_DATE_FORMAT_2 = "%Y-%m-%dT%H:%M:%SZ"


def to_millis(t: datetime.timedelta) -> int:
    """Convert timedelta to milliseconds.

    Args:
        t: Time duration to convert.

    Returns:
        Time duration in milliseconds.
    """
    return t.seconds * 1000


def _parse_datetime(date_str: str) -> dt:
    try:
        return dt.strptime(date_str, _DATE_FORMAT_1).replace(tzinfo=UTC)
    except ValueError:
        return dt.strptime(date_str, _DATE_FORMAT_2).replace(tzinfo=UTC)


def convert_to_timestamp(date_str: list[str]) -> list[float]:
    """Convert list of date strings to timestamps.

    Args:
        date_str: List of date strings in ISO format.

    Returns:
        List of Unix timestamps.
    """
    return [_parse_datetime(x).timestamp() for x in date_str]
