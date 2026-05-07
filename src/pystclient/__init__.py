#  Copyright (c) 2026 DNV AS.
#
#  SPDX-License-Identifier: MPL-2.0
#
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""pystclient - Python client library for STC."""

import warnings
from importlib import metadata

# Filter the internal authlib deprecation warning triggered by authlib's own imports
# (authlib._joserfc_helpers imports from authlib.jose which emits this warning)
from authlib.deprecate import AuthlibDeprecationWarning

warnings.filterwarnings("ignore", message="authlib.jose module is deprecated", category=AuthlibDeprecationWarning)


def _get_package_version() -> str:
    """Dynamically retrieve the version of `pystclient`.

    NOTE: The single authoritative source for the version number of the package
          is the `version` attribute in `pyproject.toml`.

    The function retrieves this version number from the metadata of the (installed) package,
    ensuring that the version number is consistent across the package and its documentation.

    If the package is not installed (e.g. when running from source), fallback to "(version unknown)".

    Returns:
        The version of the package, or "(version unknown)" if the version cannot be determined.
    """
    try:
        version = metadata.version("pystclient")
    except metadata.PackageNotFoundError:
        # Fallback
        version = "(version unknown)"
    return version


__version__: str = _get_package_version()
