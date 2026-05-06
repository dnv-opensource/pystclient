#  Copyright (c) 2026 DNV AS.
#
#  SPDX-License-Identifier: MPL-2.0
#
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""pystclient package."""

import warnings

# Filter the internal authlib deprecation warning triggered by authlib's own imports
# (authlib._joserfc_helpers imports from authlib.jose which emits this warning)
from authlib.deprecate import AuthlibDeprecationWarning

warnings.filterwarnings("ignore", message="authlib.jose module is deprecated", category=AuthlibDeprecationWarning)
