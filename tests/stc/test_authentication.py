# pyright: reportUnknownMemberType=false
import os

import pytest
from authlib.oauth2.rfc6749 import OAuth2Token

from pystclient.clients import PyStclient

from .conftest import TestOptions, authenticate

pytestmark = pytest.mark.skipif(os.environ.get("CI") is not None, reason="Skip on CI test")


def test_authentication(test_options: TestOptions):
    client = PyStclient()
    authenticate(client, test_options)
    if isinstance(client._token, OAuth2Token):  # pyright: ignore [reportPrivateUsage]
        assert not client._token.is_expired()  # pyright: ignore [reportPrivateUsage]
    else:
        assert not OAuth2Token(client._token).is_expired()  # pyright: ignore [reportPrivateUsage]
