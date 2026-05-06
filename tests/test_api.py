# pyright: reportPrivateUsage=false
from pathlib import Path
from unittest import mock

import pytest

from pystclient.api import PyStclientProcess, run


def test_file_not_found_exception() -> None:
    # Prepare
    config_file = Path("this_file_does_not_exist")
    # Execute and Assert
    with pytest.raises(FileNotFoundError):
        run(config_file)


def test_run() -> None:
    # Prepare
    config_file = Path("test_config_file")
    # Execute
    run(config_file=config_file)
    # Assert
    # (nothin to assert. Assertion is that no exception is thrown.)


def test_run_with_config_file(caplog: pytest.LogCaptureFixture) -> None:
    # Prepare
    config_file = Path("test_config_file.json")
    caplog.clear()
    # Execute
    pystclient_process_mock = mock.MagicMock(PyStclientProcess)
    with mock.patch("pystclient.api.PyStclientProcess", pystclient_process_mock):
        run(config_file)
    # Assert
    assert len(caplog.records) == 0


def test_run_with_config_file_not_existing(caplog: pytest.LogCaptureFixture) -> None:
    # Prepare
    config_file = Path("not_existing_file.json")
    log_level_expected = "ERROR"
    log_message_expected = f"run: File {config_file} not found."

    caplog.clear()
    # Execute
    pystclient_process_mock = mock.MagicMock(PyStclientProcess)
    with mock.patch("pystclient.api.PyStclientProcess", pystclient_process_mock), pytest.raises(FileNotFoundError):
        run(config_file)
    # Assert
    assert len(caplog.records) > 0
    assert caplog.records[0].levelname == log_level_expected
    assert caplog.records[0].message == log_message_expected


def test_run_with_option_login(caplog: pytest.LogCaptureFixture) -> None:
    # Prepare
    log_level_expected = "INFO"
    log_message_expected = (
        "option 'login' is True. "
        "pystclient will login to Veracity Identity to retrieve and store an access token to a local cache."
    )

    caplog.clear()
    # Execute
    pystclient_process_mock = mock.MagicMock(PyStclientProcess)
    with mock.patch("pystclient.api.PyStclientProcess", pystclient_process_mock):
        run(login=True)
    # Assert
    assert len(caplog.records) > 0
    assert caplog.records[0].levelname == log_level_expected
    assert caplog.records[0].message == log_message_expected


def test_run_with_option_delete_token(caplog: pytest.LogCaptureFixture) -> None:
    # Prepare
    log_level_expected = "INFO"
    log_message_expected = (
        "option 'delete_token' is True. pystclient will delete an access token stored in a local cache."
    )
    caplog.clear()
    # Execute
    pystclient_process_mock = mock.MagicMock(PyStclientProcess)
    with mock.patch("pystclient.api.PyStclientProcess", pystclient_process_mock):
        run(delete_token=True)
    # Assert
    assert len(caplog.records) > 0
    assert caplog.records[0].levelname == log_level_expected
    assert caplog.records[0].message == log_message_expected


class TestPyStclientProcess:
    def test_init(self) -> None:
        # Prepare
        config_file = Path("test_config_file.json")
        # Execute
        process = PyStclientProcess(config_file=config_file)
        # Assert
        assert process.config_file is config_file
        assert process.do_login is False
        assert process.delete_token is True

    def test_init_with_empty_config_file(self) -> None:
        # sourcery skip: class-extract-method
        # Prepare
        config_file = Path("test_config_file_empty.json")
        # Execute
        process = PyStclientProcess(config_file=config_file)
        # Assert
        assert process.config_file is config_file
        assert process.do_login is False
        assert process.delete_token is False


# @TODO: To be implemented
@pytest.mark.skip(reason="To be implemented")
def test_example_skip():
    """Example of a test skipped because it is not yet implemented."""
