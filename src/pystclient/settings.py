#  Copyright (c) 2026 DNV AS.
#
#  SPDX-License-Identifier: MPL-2.0
#
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Configuration settings for pystclient."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

STC_HOME = Path.home() / ".stc"
STC_CLIENT_HOME = Path.home() / ".stc" / "client"

# First read the settings file to set the environment variables
settings_file_path: Path = Path(
    os.environ.get(
        "PYSTCLIENT_SETTINGS_FILE",
        default=str((STC_CLIENT_HOME / "settings").absolute()),
    )
)
if settings_file_path.exists():
    with settings_file_path.open(encoding="utf-8") as f:
        conf = json.load(f)
        for k, v in conf.get("env", {}).items():
            if k not in os.environ:
                os.environ[k] = str(v)

# Override with local .env file
_ = load_dotenv(override=True)

# Setting configurations based on the environment variables and settings file
CLIENT_ID: str = os.getenv(
    key="PYSTCLIENT_CLIENT_ID",
    default="746115ed-daea-45c8-955a-9b32842d0cec",
)

API_ID: str = os.getenv(
    key="PYSTCLIENT_STC_API_ID",
    default="0ae571f9-d70b-4e82-9f50-656b6c5bc602",
)

DISCOVERY_ENDPOINT: str = (
    "https://login.veracity.com/a68572e3-63ce-4bc1-acdc-b64943502e9d/v2.0/.well-known/"
    "openid-configuration?p=B2C_1A_SignInWithADFSIdp"
)

AUTHORIZATION_ENDPOINT: str = (
    "https://login.veracity.com/a68572e3-63ce-4bc1-acdc-b64943502e9d/oauth2/v2.0/authorize?p=b2c_1a_signinwithadfsidp"
)

JWKS_URI: str = (
    "https://login.veracity.com/a68572e3-63ce-4bc1-acdc-b64943502e9d/discovery/v2.0/keys?p=b2c_1a_signinwithadfsidp"
)

API_ENDPOINT: str = os.getenv(
    key="PYSTCLIENT_STC_API_ENDPOINT",
    default="https://api.stc.dnv.com",
)

REPLY_URL: str = os.getenv(
    key="PYSTCLIENT_OIDC_REPLY_URL",
    default="http://localhost:9090",
)
