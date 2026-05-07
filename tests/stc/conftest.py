import json
import logging
import os
import uuid
from dataclasses import dataclass

import pytest
from joserfc.errors import ExpiredTokenError
from selenium import webdriver
from selenium.webdriver import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC  # noqa: N812
from selenium.webdriver.support.wait import WebDriverWait

from pystclient.clients import PyStclient, TokenType
from pystclient.models import BaseProject, FmuSelect, ProjectInformation
from pystclient.settings import API_ENDPOINT
from pystclient.utils import random_string

logger = logging.getLogger(__name__)

TEST_PROJECT_PREFIX = "STCClient-Test-Project"


@dataclass
class TestOptions:
    __test__ = False
    test_user = os.environ.get("PYSTCLIENT_TEST_USER", "unknown")
    test_user_password = os.environ.get("PYSTCLIENT_TEST_USER_PASSWORD", "unknown")
    headless = json.loads(os.environ.get("PYSTCLIENT_TEST_HEADLESS", "true").lower())
    own_user = json.loads(os.environ.get("PYSTCLIENT_TEST_OWN_USER", "false").lower())


@pytest.fixture(scope="package")
def test_options():
    return TestOptions()


@pytest.fixture(scope="package")
def client(test_options: TestOptions):
    client = PyStclient()
    authenticate(client, test_options)
    return client


@pytest.fixture(scope="package", autouse=True)
def test_project(client: PyStclient) -> ProjectInformation:
    logger.info("Creating a test project")
    r = client.project.info_all()
    for p in r:
        if p.name.startswith(TEST_PROJECT_PREFIX):
            assert client.project.delete(str(p.id))
    project_info = client.project.create(BaseProject(name=f"{TEST_PROJECT_PREFIX}-{random_string()}"))
    return project_info


@pytest.fixture(scope="package", autouse=True)
def test_models_by_filename() -> list[FmuSelect]:
    fmus = [FmuSelect(filename=x) for x in ["Spring.fmu", "Damper.fmu", "Mass.fmu"]]
    return fmus


@pytest.fixture(scope="package", autouse=True)
def test_models_by_version_id() -> list[FmuSelect]:
    fmus = [
        FmuSelect(version=uuid.UUID(x))
        for x in (
            [
                "592B1E80-79B3-4E7C-8304-D360B942176D",  # Spring
                "54B95A5F-0936-4BBD-8011-F3CCF934A2B1",  # Mass
                "373EA52B-3BF1-4190-AEE2-D28EC37871F2",  # Damper
            ]
            if "api.stc.dnv.com" in API_ENDPOINT
            else [
                "21B8F9DF-67F5-4A24-9325-45538E2E6EE0",  # Spring
                "EE1EFF08-8958-495C-ADAF-1156E296524C",  # Mass
                "830B4F41-BC6C-4A5F-B12D-8F81FB449626",  # Damper
            ]
        )
    ]
    return fmus


@pytest.fixture(scope="package", autouse=True)
def test_models_by_model_id() -> list[FmuSelect]:
    fmus = [
        FmuSelect(id=uuid.UUID(x))
        for x in (
            [
                "869699A2-8945-4D48-B135-AB0AEBD292CA",  # Spring
                "9D872C71-9589-4171-B2D0-3374CC947F70",  # Mass
                "617EED59-21BF-438A-8524-0C09C7F8D5FF",  # Damper
            ]
            if "api.stc.dnv.com" in API_ENDPOINT
            else [
                "95BD75BD-26DF-47DD-B353-49A460FCF83F",  # Spring
                "CBEBAEE0-2C4D-4746-B26C-BDAFC6C02247",  # Mass
                "88EAF9B4-BAAB-449C-97A1-FEE85CDFE38C",  # Damper
            ]
        )
    ]
    return fmus


# pyright: reportUnknownMemberType=false


def authenticate(client: PyStclient, test_options: TestOptions):
    token: TokenType | None = None
    if not test_options.own_user:
        try:
            token = client._cached_token()  # pyright: ignore [reportPrivateUsage]
        except ExpiredTokenError:
            logger.info("The token has expired, re-authenticating...")
        except Exception as e:
            logger.exception("Unable to use cached token, re-authenticating...", exc_info=e)

        if token is None:
            uri, state, code_verifier = client._create_session()  # pyright: ignore [reportPrivateUsage]
            options = Options()

            if test_options.headless:
                options.add_argument("--headless=new")
            # options.add_experimental_option("detach", True)

            driver = webdriver.Chrome(options=options)
            driver.get(uri)
            ss = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "username")))
            ss.send_keys(test_options.test_user)
            # time.sleep(2)
            ss.send_keys(Keys.RETURN)
            ss = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "password")))
            ss.send_keys(test_options.test_user_password)
            # time.sleep(2)
            ss.send_keys(Keys.RETURN)
            token = client._retrieve_token(state, code_verifier)  # pyright: ignore [reportPrivateUsage]
            _ = client._session.ensure_active_token(token)  # pyright: ignore [reportPrivateUsage]
            return
    _ = client.authenticate(token)
