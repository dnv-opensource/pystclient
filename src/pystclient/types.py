#  Copyright (c) 2026 DNV AS.
#
#  SPDX-License-Identifier: MPL-2.0
#
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Type definitions for pystclient."""

import logging
import uuid
from enum import Enum
from typing import TypeAlias, TypeVar

from authlib.oauth2.rfc6749 import OAuth2Token
from pydantic import BaseModel

logger = logging.getLogger(__name__)

TokenType: TypeAlias = dict[str, str] | OAuth2Token

STCModel = TypeVar("STCModel", bound=BaseModel)

FmuVariableType: TypeAlias = int | float | bool | str

ProjectID: TypeAlias = str | uuid.UUID
ProjectVersionID: TypeAlias = str | uuid.UUID


class FmuVariableTypeEnum(Enum):
    """Enumeration of FMU variable types."""

    INT = "Integer"
    REAL = "Real"
    BOOL = "Bool"  # Deprecated
    STR = "String"
    BOOLEAN = "Boolean"  # STC sometimes returns "Boolean" instead of "Bool"


class SimulationType(Enum):
    """Enumeration of simulation types."""

    DISTRIBUTED = "distributed"
    CENTRALIZED = "centralized"


def from_string_value(value: str, t: FmuVariableTypeEnum) -> FmuVariableType:
    """Convert string value to an FMU variable type."""
    try:
        if t == FmuVariableTypeEnum.INT:
            return int(value)
        if t == FmuVariableTypeEnum.REAL:
            return float(value)
        if t in [FmuVariableTypeEnum.BOOL, FmuVariableTypeEnum.BOOLEAN]:
            return bool(value)
    except ValueError:
        logger.warning("Could not convert value %s to type %s. Returning the value as it is.", value, t)

    return value


class FmuCausalityType(Enum):
    """Enumeration of FMU causality types."""

    INPUT = "input"
    OUTPUT = "output"
    PARAMETER = "parameter"


class TimeUnit(Enum):
    """Enumeration of time units."""

    MILLISECONDS = "ms"
    MICROSECONDS = "us"
    SECONDS = "s"
