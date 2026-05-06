#  Copyright (c) 2026 DNV AS.
#
#  SPDX-License-Identifier: MPL-2.0
#
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""STC client module for managing STC API interactions."""

# pyright: reportUnknownMemberType=false
import importlib.resources
import json
import logging
import math
import time
import uuid
import webbrowser
from abc import ABC
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Self
from urllib import parse
from urllib.parse import urlparse

import edn_format
import requests
from authlib.common.security import generate_token
from authlib.integrations.requests_client import OAuth2Session
from authlib.oauth2.rfc6749 import OAuth2Token
from joserfc import jwt
from joserfc.errors import ExpiredTokenError, InvalidClaimError
from joserfc.jwk import KeySet
from joserfc.jwt import JWTClaimsRegistry, Token
from requests import Response
from requests import Session as RequestsSession

from pystclient import models
from pystclient.exception import (
    APIResponseError,
    FmuModelNotFoundError,
    MissingVariablesError,
    PyStclientError,
)
from pystclient.models import (
    UUID,
    FmuConnections,
    FmuModelInformation,
    FmuSelect,
    FmuVariableGroup,
    FmuVariables,
    LoggingConfiguration,
    MeasurementQuery,
    Measurements,
    ProjectInformation,
    QueryResult,
    QueryVariable,
    SimulationConfig,
    SimulationInfo,
    SimulationParameters,
    SimulatorStatus,
    UploadedModelInfo,
)
from pystclient.settings import API_ENDPOINT, API_ID, CLIENT_ID, DISCOVERY_ENDPOINT, REPLY_URL, STC_CLIENT_HOME
from pystclient.types import ProjectID, STCModel, TokenType
from pystclient.utils import (
    merge_dicts,
    raise_if_not_json_ok,
    raise_if_not_ok,
    to_uuid,
)
from pystclient.utils.time import to_millis

oidc_code: dict[str, list[str]] | None = None

logger = logging.getLogger(__name__)
logging.getLogger("edn_format").setLevel("WARNING")

SimulationID = UUID
SimulatorID = UUID


def cache_token(token: TokenType) -> None:
    """Persist an OAuth2 token to disk for reuse across sessions.

    The token is stored as a JSON file in the STC client home directory,
    allowing subsequent client instantiations to skip the interactive
    authentication flow.

    Args:
        token: The OAuth2 token to cache

    """
    logger.info("Caching a token")
    # Ensure the STC client home directory exists before writing
    Path.mkdir(STC_CLIENT_HOME, exist_ok=True, parents=True)
    # Persist the token as JSON for reuse across sessions
    with (STC_CLIENT_HOME / "token").open("w", encoding="utf-8") as f:
        json.dump(token, f)


def read_token() -> dict[str, str] | None:
    """Read a previously cached OAuth2 token from disk.

    Looks for a token file in the STC client home directory. If no token
    file exists, returns ``None`` so the caller can fall back to interactive
    authentication.

    Returns:
        The deserialized token dictionary, or ``None`` if no cached token is available

    """
    logger.debug("Checking a cached token..")
    token_path = STC_CLIENT_HOME / "token"
    # Return None if no cached token file exists on disk
    if not token_path.exists() or not token_path.is_file():
        return None
    # Read and deserialize the cached token from disk
    with (STC_CLIENT_HOME / "token").open(encoding="utf-8") as f:
        return json.load(f)


def validate_token(access_token: str, key: KeySet, nonce: str | None = None) -> Token:
    """Decode and validate a JWT access token against the STC API requirements.

    Verifies that the token's audience and authorized-party claims match the
    configured API and client IDs. Optionally validates a nonce to guard
    against replay attacks.

    Args:
        access_token: The raw JWT access token string
        key: The public key set used to verify the token signature
        nonce: A nonce value to validate against the token's ``nonce`` claim, by default None

    Returns:
        The decoded JWT token with validated claims

    Raises:
        InvalidClaimError: If any required claim fails validation

    """
    logger.info(f"Target API endpoint: {API_ENDPOINT}")
    # Define required claims: audience must match the API ID, authorized party must match the client ID
    claims_options = {
        "aud": {
            "essential": True,
            "value": API_ID,
        },
        "azp": {
            "essential": True,
            "value": CLIENT_ID,
        },
    }
    # Optionally require nonce validation to prevent replay attacks
    if nonce is not None:
        claims_options["nonce"] = {
            "essential": True,
            "values": [nonce],
        }
    # Decode the JWT using the public key set
    token = jwt.decode(access_token, key)
    # Validate the decoded claims; re-raise if any claim is invalid
    try:
        claims_registry = JWTClaimsRegistry(**claims_options)  # type: ignore[arg-type]
        claims_registry.validate(token.claims)
    except InvalidClaimError as e:
        logger.exception("Token validation failed!", exc_info=e)
        raise
    return token


class HandleAuthentication(BaseHTTPRequestHandler):
    """Handle authentication."""

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002,ANN401,D102
        pass

    def do_POST(self) -> None:
        """Handle POST request for authentication."""
        # Read the request body based on Content-Length header
        length = int(self.headers["Content-Length"])
        field_data = self.rfile.read(length)
        # Parse the URL-encoded form data into a dictionary
        query_map = parse.parse_qs(str(field_data, "UTF-8"))
        # Send a 200 OK response with HTML content type
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()

        # Store the OIDC authorization code globally for later retrieval
        global oidc_code
        oidc_code = query_map
        # Serve the "authenticated" HTML page to confirm successful login
        res = importlib.resources.files("pystclient.resources").joinpath("authenticated.html")
        with importlib.resources.as_file(res) as f:
            _ = self.wfile.write(f.read_bytes())


def to_model(
    resp: Response,
    model: type[STCModel],
    mapping: Callable[[dict[Any, Any]], dict[Any, Any]] | None = None,
) -> STCModel:
    """Parse an HTTP response into a single STC model instance.

    Validates that the response has a JSON body with a 2xx status code,
    optionally transforms the raw JSON with a mapping function, then
    constructs and returns the specified model.

    Args:
        resp: The HTTP response to parse
        model: The model class to instantiate from the response data
        mapping: An optional function to transform the raw JSON before model construction

    Returns:
        The constructed model instance

    Raises:
        APIResponseError: If the response status is not OK or is not JSON

    """
    # Ensure the response is JSON and has a 2xx status code
    if raise_if_not_json_ok(resp).ok:
        r = resp.json()
        # Apply an optional transformation to the raw JSON before model construction
        if mapping is not None:
            r = mapping(r)
        return model(**r)

    raise APIResponseError(resp)


def to_models(
    resp: Response,
    model: type[STCModel],
    mapping: Callable[[Any], list[dict[Any, Any]]] | None = None,
) -> list[STCModel]:
    """Parse an HTTP response into a list of STC model instances.

    Validates that the response has a JSON body with a 2xx status code,
    optionally transforms the raw JSON with a mapping function, then
    constructs a model instance for each item in the resulting list.

    Args:
        resp: The HTTP response to parse
        model: The model class to instantiate for each item
        mapping: An optional function to extract a list of dicts from the raw JSON

    Returns:
        A list of constructed model instances

    Raises:
        APIResponseError: If the response status is not OK or is not JSON

    """
    # Ensure the response is JSON and has a 2xx status code
    if raise_if_not_json_ok(resp).ok:
        r = resp.json()
        # Apply an optional transformation to extract a list of dicts from the raw JSON
        if mapping is not None:
            r = mapping(r)
        # Construct a model instance for each item in the list
        return [model(**x) for x in r]

    raise APIResponseError(resp)


class BaseClient(ABC):
    """Base client providing shared session and response-parsing utilities.

    All STC sub-clients inherit from this class to share an authenticated
    :class:`OAuth2Session` and common helper methods for parsing API responses.
    """

    session: RequestsSession

    def __init__(self, session: RequestsSession) -> None:
        self.session = session


class ModelClient(BaseClient):
    """Client for managing FMU models in the STC platform.

    Provides methods to upload, search, retrieve metadata for, and delete
    FMU (Functional Mock-up Unit) models stored on the STC API.
    """

    def retrieve_model_info_by_name(self, fmu_models: list[FmuSelect]) -> list[FmuSelect]:
        """Look up and populate version and ID for FMU models that are missing this information.

        For each model in the list whose ``version`` is ``None``, queries the
        STC API to find a matching model by ID or filename, then fills in the
        ``version`` and ``id`` fields from the remote record.

        Args:
            fmu_models: List of FMU model selectors to resolve

        Returns:
            The same list with ``version`` and ``id`` populated for each entry

        Raises:
            FmuModelNotFoundError: If a model cannot be matched by ID or filename on the server

        """
        for model in fmu_models:
            # Only fetch remote info for models that don't have a version set yet
            if model.version is None:
                # Retrieve all available FMU models from the API
                fmus = to_models(self.session.get(f"{API_ENDPOINT}/api/fmus"), FmuModelInformation, lambda x: x["data"])
                try:
                    # Match the model by ID or filename
                    fmu = next(x for x in fmus if x.id == model.id or x.filename == model.filename)
                except StopIteration as e:
                    assert model.filename is not None
                    raise FmuModelNotFoundError(model.filename) from e
                # Populate the version and ID from the matched remote model
                model.version = fmu.version
                model.id = fmu.id
        return fmu_models

    def find_models_by_filename(self, filename: str) -> list[FmuModelInformation]:
        """Search the STC platform for FMU models whose filename matches the given string.

        Fetches all available FMU models from the API and returns those with
        an exact filename match. Returns an empty list if no models match.

        Args:
            filename: The exact FMU filename to search for (e.g. ``"MyModel.fmu"``)

        Returns:
            List of FMU model records matching the filename

        """
        # Fetch all FMU models from the API
        fmus = to_models(self.session.get(f"{API_ENDPOINT}/api/fmus"), FmuModelInformation, lambda x: x["data"])
        # Filter to only those whose filename matches the search term
        matched_fmus = list(filter(lambda x: x.filename == filename, fmus))
        return matched_fmus

    def delete_models(self, id_list: list[uuid.UUID | str]) -> bool:
        """Remove one or more FMU models from the STC platform by their IDs.

        Args:
            id_list: List of FMU model IDs to delete

        Returns:
            ``True`` if the server accepted the deletion request

        """
        # Send a DELETE request with the list of model IDs converted to strings
        return self.session.delete(f"{API_ENDPOINT}/api/fmus", json=[str(x) for x in id_list]).ok

    def upload_model(self, fmu_path: Path) -> UploadedModelInfo:
        """Upload an FMU file to the STC platform.

        The file is sent as a multipart form upload. On success the server
        returns metadata about the newly created model record.

        Args:
            fmu_path: Local filesystem path to the ``.fmu`` file to upload

        Returns:
            Metadata for the newly uploaded model, including its assigned ID and version

        """
        # Open the FMU file in binary mode and upload it as a multipart form
        with fmu_path.open("rb") as f:
            files = {"file": ("ErrorAtInit.fmu", f, "multipart/form-data")}
            return to_model(self.session.post(f"{API_ENDPOINT}/api/fmus", files=files), UploadedModelInfo)


def _query_results(session: RequestsSession, measurement_id: UUID, q: MeasurementQuery) -> list[QueryResult]:
    r = to_models(
        session.post(
            f"{API_ENDPOINT}/api/plot/measurements/{measurement_id}/query",
            json=q.model_dump(by_alias=True, mode="json"),
        ),
        QueryResult,
    )
    return r


class SimulationResults(Iterator[list[QueryResult]]):
    """Iterator that pages through simulation measurement results in configurable time steps.

    Wraps a list of ``Measurements`` and exposes an iterator interface that
    queries the STC API for result data one time window at a time. Use
    :meth:`step` to configure the window size and :meth:`reset` to restart
    iteration from a different measurement index or with different variables.
    """

    _measurements: list[Measurements]
    _step: timedelta = timedelta(minutes=15)
    _index: int = 0
    _current_time: timedelta = timedelta()
    _start_time: timedelta
    _end_time: timedelta
    _query: MeasurementQuery

    session: RequestsSession
    project_id: UUID

    def __init__(
        self,
        session: RequestsSession,
        measurements: list[Measurements],
        project_id: UUID,
        index: int = 0,
    ) -> None:
        # sourcery skip: simplify-len-comparison
        assert len(measurements) > 0
        self._measurements = measurements
        self.session = session
        self.project_id = project_id
        self.index = index
        self._end_time = timedelta(milliseconds=measurements[index].metadata.end_time)
        self._start_time = timedelta(milliseconds=measurements[index].metadata.start_time)

        # Build measurement query
        self._set_measurement_query(measurements[index])

    def _set_measurement_query(
        self,
        m: Measurements,
        query_variables: list[QueryVariable] | None = None,
    ) -> None:
        self._query = MeasurementQuery(
            time_from=timedelta(milliseconds=m.metadata.start_time).seconds,
            time_to=timedelta(m.metadata.start_time).seconds + self._step.seconds,
            variables=(
                self._resolve_query_instance_id(p)
                if (p := query_variables) is not None
                else [
                    x
                    for xs in (
                        (
                            (
                                QueryVariable(
                                    instance_id=m_inst.instance_id,
                                    name=var.name,
                                    causality=var.causality,
                                )
                            )
                            for var in m_inst.variables
                        )
                        for m_inst in m.metadata.instances
                    )
                    for x in xs
                ]
            ),
        )

    def _resolve_query_instance_id(self, qvs: list[QueryVariable]) -> list[QueryVariable]:
        mapping_id = {
            inst.instance_name: inst.instance_id for inst in self._measurements[self._index].metadata.instances
        }
        for qv in qvs:
            if qv.instance_id is None:
                assert qv.instance_name is not None
                assert qv.instance_name in mapping_id, f"Could not resolve instance id for {qv.instance_name}"
                qv.instance_id = mapping_id[qv.instance_name]
        return qvs

    def measurement_size(self) -> int:
        """Return the total number of measurement records available for iteration.

        Returns:
            Number of measurement records

        """
        return len(self._measurements)

    @property
    def measurements(self) -> list[Measurements]:
        """Access the underlying measurement records used by this iterator.

        Returns:
            All measurement records associated with this simulation result set

        """
        return self._measurements

    def step(self, t: timedelta) -> None:
        """Configure the time window size used when paging through results.

        Each call to ``next()`` will return data for a window of this duration.
        The default step is 15 minutes.

        Args:
            t: Duration of each query time window

        """
        self._step = t

    def reset(self, index: int = 0, query_variables: list[QueryVariable] | None = None) -> None:
        """Restart iteration from the beginning of a specific measurement record.

        Resets the internal time cursor to the start of the measurement at the
        given ``index`` and optionally narrows the query to a specific set of
        variables. Call this to re-iterate over the same or a different
        measurement without creating a new ``SimulationResults`` object.

        Args:
            index: Zero-based index of the measurement record to iterate over, by default 0
            query_variables: Specific variables to include in query results. If ``None``,
            all variables from the measurement are included.

        """
        assert len(self._measurements) > index
        # Rebuild the measurement query for the selected measurement index
        self._set_measurement_query(self._measurements[index], query_variables)
        self._index = index
        # Reset the time boundaries and cursor to the start of the selected measurement
        self._end_time = timedelta(milliseconds=self._measurements[index].metadata.end_time)
        self._start_time = timedelta(milliseconds=self._measurements[index].metadata.start_time)
        self._current_time = self._start_time

    def query_variables(self, query_variables: list[QueryVariable]) -> None:
        """Replace the set of variables included in subsequent query results.

        Instance IDs are resolved automatically from instance names when not
        already set on the provided ``QueryVariable`` objects.

        Args:
            query_variables: Variables to include in future query results

        """
        # Resolve instance IDs from instance names for any variables missing them
        _ = self._resolve_query_instance_id(query_variables)
        # Replace the query's variable list with the resolved variables
        self._query.variables = query_variables

    def __iter__(self) -> Self:
        """Return the iterator object."""
        return self

    def __next__(self) -> list[QueryResult]:
        """Fetch the next page of query results for the current time window.

        Each invocation advances the internal time cursor by one step (see
        :meth:`step`) and returns the data for that window. Iteration ends
        when the time cursor reaches the measurement's end time.

        Returns:
            Query results for the current time window

        Raises:
            StopIteration: When all time windows in the measurement have been exhausted

        """
        # Stop iterating once the current time cursor has passed the measurement end time
        if self._current_time >= self._end_time:
            raise StopIteration
        # Query results for the current time window
        r = _query_results(self.session, self._measurements[self._index].id, self._query)
        # Advance the time cursor by one step
        self._current_time += self._step
        # Slide the query time window forward for the next iteration
        self._query.time_from = to_millis(self._current_time)
        self._query.time_to = self._query.time_from + to_millis(self._step)
        return r


class MeasurementClient(BaseClient):
    """Client for accessing simulation result data from the STC platform.

    In STC, a **measurement** is the recorded simulation result for a single
    model instance — i.e. the time-series data produced by one FMU during a
    simulation run. A single simulation therefore produces one measurement per
    model instance involved.

    This client provides methods to list, retrieve, and query those per-instance
    measurements, as well as a convenience method to obtain a paginated iterator
    over all measurements from a given simulation.
    """

    def measurements(self, project_id: UUID, simulation_id: UUID | None = None) -> list[Measurements]:
        """List all per-instance simulation result records for a project.

        Each returned object represents the simulation result (measurement) of
        a single model instance. A simulation with *N* model instances will
        therefore produce *N* measurement records.

        When ``simulation_id`` is provided, only the measurements produced by
        that specific simulation run are returned.

        Args:
            project_id: ID of the project whose measurement records to retrieve
            simulation_id: Restrict results to a specific simulation run, by default None

        Returns:
            One metadata object per model instance that recorded data in the matching simulation(s)

        """
        # Build the base query URL including variable metadata
        query_url: str = f"{API_ENDPOINT}/api/plot/project/{project_id}?include-vars?=true"
        # Optionally filter by simulation ID
        query_url = f"{query_url}&simulation-id={simulation_id}" if simulation_id is not None else query_url
        r = to_models(
            self.session.get(query_url),
Measurements,
        )
        return r

    def measurement(self, measurement_id: UUID) -> Measurements:
        """Retrieve the full metadata for the simulation result of a single model instance.

        A measurement represents the recorded output of one FMU model instance
        during a simulation run. The returned object includes the list of
        recorded variables and their instance information.

        Args:
            measurement_id: Unique identifier of the per-instance simulation result to retrieve

        Returns:
            Complete simulation result metadata for the model instance, including its recorded variables and
            instance details

        """
        return to_model(self.session.get(f"{API_ENDPOINT}/api/plot/measurements/{measurement_id}"), Measurements)

    def query(self, measurement_id: UUID, q: MeasurementQuery) -> list[QueryResult]:
        """Query time-series variable data from a single model instance's simulation result.

        A measurement is the recorded simulation result for one model instance.
        This method retrieves variable values from that result within a specified
        time range. If any variable in ``q`` is missing its ``instance_id``, it
        is resolved automatically from the model instance metadata using the
        variable's ``instance_name``.

        Args:
            measurement_id: Unique identifier of the per-instance simulation result to query
            q: Query specification including the time range and the list of variables to retrieve

        Returns:
            Time-series data for each requested variable from this model instance

        """
        # Lazily-loaded instance name-to-ID mapping, fetched only if needed
        instances: dict[str, UUID] | None = None

        # Resolve missing instance IDs by looking them up from measurement metadata
        for qvar in q.variables:
            if qvar.instance_id is None:
                if not instances:
                    logger.info(measurement_id)
                    # Fetch measurement metadata once to build the instance mapping
                    measurement = self.measurement(measurement_id)
                    instances = {x.instance_name: x.instance_id for x in measurement.metadata.instances}
                qvar.instance_id = instances.get(qvar.instance_name) if qvar.instance_name else None

        return _query_results(self.session, measurement_id, q)

    def simulation_results(self, project_id: UUID, simulation_id: UUID) -> SimulationResults | None:
        """Obtain a paginated iterator over all per-instance simulation results for a run.

        Each measurement in the iterator represents the recorded result of one
        model instance from the specified simulation. The returned
        :class:`SimulationResults` iterator lets you page through the time-series
        data of all model instances in configurable time steps.

        Args:
            project_id: ID of the project containing the simulation
            simulation_id: ID of the simulation run whose per-instance results to iterate over

        Returns:
            A results iterator over all model-instance measurements, or ``None`` if the simulation has not yet produced
            any measurement data

        """
        # Fetch measurements for the given project and simulation
        r: list[Measurements] = self.measurements(project_id, simulation_id)
        # Return a results iterator if measurements exist, otherwise None
        return SimulationResults(self.session, r, project_id) if r else None


class SimulatorClient(BaseClient):
    """Client for creating, controlling, and monitoring simulators on the STC platform.

    Manages the full simulator lifecycle: creation, readiness polling, start/stop
    control, result recording, and graceful termination. Long-running operations
    such as waiting for readiness are executed asynchronously via a thread pool.
    """

    _executor: ThreadPoolExecutor
    _cached_simulation_id: dict[SimulatorID, tuple[ProjectID, SimulationID]]

    def __init__(self, session: RequestsSession) -> None:
        super().__init__(session)
        self._executor = ThreadPoolExecutor(max_workers=10)
        self._cached_simulation_id = {}

    def wait_until_ready(self, *simulator_ids: UUID, timeout: int = 120) -> bool:
        """Block until all specified simulators have finished initializing and are ready to run.

        Polls each simulator's status in sequence. Returns ``True`` as soon as
        all simulators report ready, or ``False`` if the ``timeout`` is exceeded
        before all are ready.

        Args:
            *simulator_ids: One or more simulator IDs to wait for
            timeout: Maximum time to wait in seconds, by default 120

        Returns:
            ``True`` if all simulators became ready within the timeout, ``False`` otherwise

        """
        start = datetime.now(tz=UTC)
        # Poll each simulator in sequence until it reports ready
        for simulator_id in simulator_ids:
            while not self.ready(simulator_id):
                # Return False if the overall timeout has been exceeded
                if (datetime.now(tz=UTC) - start).seconds > timeout:
                    logger.warning(
                        f"Simulation {simulator_id} was not initialized within the time bound - {timeout} seconds"
                    )
                    return False
                time.sleep(1)
        return True

    def ready(self, simulator_id: UUID) -> bool:
        """Check whether a simulator has completed initialization and is ready to start.

        A simulator is considered ready when it is connected to the platform
        and has progressed past the ``"initialized"`` state.

        Args:
            simulator_id: ID of the simulator to check

        Returns:
            ``True`` if the simulator is ready to accept commands

        """
        # A simulator is ready when it is connected and has moved past the "initialized" state
        return (p := self.status(simulator_id)).is_connected and p.status != "initialized"

    def finished(self, *simulator_ids: UUID) -> bool:
        """Determine whether all specified simulators have completed their runs.

        A simulator is considered finished if its simulation time has reached
        the configured end time, or if it has already been cleaned up by the
        platform (HTTP 404 or 410).

        Args:
            *simulator_ids: One or more simulator IDs to check

        Returns:
            ``True`` if every simulator has finished, ``False`` otherwise

        """
        # Track completion status for each simulator; default to not finished
        statuses = [False] * len(simulator_ids)
        for idx, simulator_id in enumerate(simulator_ids):
            try:
                s = self.status(simulator_id)
            except APIResponseError as e:
                # A 410 Gone or 404 Not Found means the simulator has already been cleaned up
                if e.status_code in [410, 404]:
                    statuses[idx] = True
                continue

            # Mark as finished when simulation time has reached the configured end time
            if s.simulation_time is not None and s.end_time is not None and math.isclose(s.simulation_time, s.end_time):
                statuses[idx] = True

        return all(statuses)

    def create(self, model: SimulationConfig) -> tuple[list[SimulatorStatus], Future[bool]]:
        """Provision one or more simulators on the STC platform from a configuration.

        Sends the simulation configuration to the API and returns immediately
        with the initial statuses. A background ``Future`` is also returned
        that resolves to ``True`` once all created simulators are ready to
        accept start commands.

        Args:
            model: The simulation configuration describing which models, parameters, and connections to use

        Returns:
            A tuple of (initial simulator statuses, a future that resolves to ``True`` when all simulators are ready)

        Raises:
            PyStclientError: If the API returns no simulator statuses

        """
        # Post the simulation configuration to the API and parse the returned statuses
        statuses: list[SimulatorStatus] = to_models(
            self.session.post(
                f"{API_ENDPOINT}/api/simulators", json=model.model_dump(exclude_none=True, by_alias=True, mode="json")
            ),
            SimulatorStatus,
        )
        if not statuses:
            raise PyStclientError("Unable to retrieve simulator information!")

        # Cache the project/simulation ID pair for each simulator for later retrieval
        for item in statuses:
            # For type == CENTRALIZED, API does not include simulation in a status for the first few requests.
            simulation = item.simulation
            if simulation is not None:
                self._cached_simulation_id[item.id] = item.project_id, simulation.id

        simulator_ids = (x.id for x in statuses)

        # Return statuses immediately and a background future that resolves when all simulators are ready
        return statuses, self._executor.submit(self.wait_until_ready, *simulator_ids)

    def status(self, simulator_id: UUID) -> SimulatorStatus:
        """Retrieve the current status of a running or recently stopped simulator.

        Returns detailed information including connection state, simulation
        time, and the simulator's lifecycle phase.

        Args:
            simulator_id: ID of the simulator to query

        Returns:
            Current status snapshot of the simulator

        """
        return to_model(
            self.session.get(f"{API_ENDPOINT}/api/simulators/{simulator_id}"),
            SimulatorStatus,
        )

    def start(
        self,
        simulator_id: UUID,
        *,
        record: bool = False,
    ) -> bool:
        """Begin executing a simulator that is in the ready state.

        Optionally starts recording simulation results at the same time.
        Use ``record=True`` to combine the start and record-results commands
        into a single API call.

        Args:
            simulator_id: ID of the simulator to start
            record: If ``True``, automatically begin recording results upon start, by default ``False``

        Returns:
            ``True`` if the start command was accepted by the server

        """
        # Choose the start-and-record or plain start endpoint based on the record flag
        return raise_if_not_ok(
            self.session.put(
                f"{API_ENDPOINT}/api/simulators/{simulator_id}/{'start-and-record' if record else 'start'}"
            )
        ).ok

    def stop(self, simulator_id: UUID) -> bool:
        """Pause a running simulator without ending the simulation.

        The simulator can be resumed later with :meth:`start`.

        Args:
            simulator_id: ID of the simulator to stop

        Returns:
            ``True`` if the stop command was accepted by the server

        """
        return raise_if_not_ok(self.session.put(f"{API_ENDPOINT}/api/simulators/{simulator_id}/stop")).ok

    def _wait_for_measurements(
        self, project_id: UUID, simulation_id: UUID, timeout: int = 240
    ) -> SimulationResults | None:
        start = datetime.now(tz=UTC)
        while (datetime.now(tz=UTC) - start).seconds < timeout:
            r = to_models(
                self.session.get(
                    f"{API_ENDPOINT}/api/plot/project/{project_id}?include-vars?=true&simulation-id={simulation_id}",
                ),
                Measurements,
            )
            if len(r) > 0:
                return SimulationResults(self.session, r, project_id)
            time.sleep(5)
        return None

    def end_simulation(self, simulator_id: UUID) -> Future[SimulationResults | None]:
        """Gracefully end a simulation and asynchronously wait for result data.

        Sends the ``end-simulation`` command to the simulator and starts a
        background thread that polls for measurement results. The returned
        ``Future`` resolves to a :class:`SimulationResults` iterator once
        results are available, or ``None`` if results do not appear within
        the timeout.

        Args:
            simulator_id: ID of the simulator whose simulation to end

        Returns:
            A future that resolves to a results iterator, or ``None`` on timeout

        """
        # Retrieve the project and simulation IDs from cache or by querying the simulator status
        project_id, simulation_id = None, None
        if simulator_id in self._cached_simulation_id:
            project_id, simulation_id = self._cached_simulation_id[simulator_id]
        else:
            p = self.status(simulator_id)
            assert p.simulation is not None, "Simulator has no associated simulation"
            project_id, simulation_id = p.project_id, p.simulation.id

        # Remove the cached entry since the simulation is ending
        _ = self._cached_simulation_id.pop(simulator_id, None)

        # Start polling for measurement results in a background thread
        f = self._executor.submit(self._wait_for_measurements, project_id, simulation_id)
        # Send the end-simulation command to the simulator
        _ = raise_if_not_ok(
            self.session.put(
                f"{API_ENDPOINT}/api/simulators/{simulator_id}/command",
                json=["end-simulation", {"sas/key": "", "sas/url": ""}],
            )
        )
        return f

    def terminate(self, simulator_id: UUID) -> bool:
        """Terminate a simulator and release its server-side resources.

        Unlike :meth:`end_simulation`, this does not wait for results to be
        persisted. Use this to clean up simulators that are stuck or no longer
        needed.

        Args:
            simulator_id: ID of the simulator to terminate

        Returns:
            ``True`` if the server accepted the termination request

        """
        return self.session.delete(f"{API_ENDPOINT}/api/simulators/{simulator_id}").ok

    def start_logging(self, simulator_id: UUID) -> bool:
        """Begin recording simulation results for a running simulator.

        Recorded results can later be retrieved via the measurement API.
        To stop recording and trigger an upload, call :meth:`stop_logging`.

        Args:
            simulator_id: ID of the simulator to start recording for

        Returns:
            ``True`` if the record command was accepted by the server

        """
        return raise_if_not_ok(self.session.put(f"{API_ENDPOINT}/api/simulators/{simulator_id}/record-results")).ok

    def stop_logging(self, simulator_id: UUID) -> bool:
        """Stop recording simulation results and upload them to the platform.

        After this call, the recorded data becomes available through the
        measurement and query APIs.

        Args:
            simulator_id: ID of the simulator to stop recording for

        Returns:
            ``True`` if the stop-and-upload command was accepted by the server

        """
        return raise_if_not_ok(
            self.session.put(f"{API_ENDPOINT}/api/simulators/{simulator_id}/stop-recording-and-upload-results")
        ).ok


class ProjectClient(BaseClient):
    """Client for managing STC projects and their associated configurations.

    Provides methods for creating, deleting, and inspecting projects, as well
    as managing their FMU model selections, parameter sets, variable
    connections, logging configuration, and completed simulation history.
    """

    model_client: ModelClient

    def __init__(self, session: RequestsSession, model_client: ModelClient) -> None:
        super().__init__(session)
        self.model_client = model_client

    def info(self, project_id: ProjectID) -> ProjectInformation:
        """Retrieve detailed metadata for a single project.

        Args:
            project_id: Unique identifier of the project

        Returns:
            Project metadata including name, creation date, and configuration

        """
        return to_model(self.session.get(f"{API_ENDPOINT}/api/projects/{project_id}"), ProjectInformation)

    def create(self, model: models.BaseProject) -> ProjectInformation:
        """Create a new project on the STC platform.

        Args:
            model: Project definition including name and optional settings

        Returns:
            Metadata of the newly created project, including its assigned ID

        """
        return to_model(self.session.post(f"{API_ENDPOINT}/api/projects", json=model.dict()), ProjectInformation)

    def info_all(self) -> list[ProjectInformation]:
        """List metadata for all projects accessible to the authenticated user.

        Returns:
            Metadata for every available project

        """
        return to_models(self.session.get(f"{API_ENDPOINT}/api/projects"), ProjectInformation)

    def delete(self, project_id: ProjectID) -> bool:
        """Permanently delete a project and all its associated data from the platform.

        Args:
            project_id: ID of the project to delete

        Returns:
            ``True`` if the server accepted the deletion request

        """
        r = self.session.delete(f"{API_ENDPOINT}/api/projects/{project_id!s}")
        return raise_if_not_ok(r).ok

    def select_models(self, project_id: ProjectID, fmu_models: list[FmuSelect]) -> bool:
        """Assign one or more FMU models to a project for use in simulations.

        Model version and ID are resolved automatically from the API if not
        already set on the provided ``FmuSelect`` objects.

        Args:
            project_id: ID of the project to assign models to
            fmu_models: FMU model selectors identifying which models to assign

        Returns:
            ``True`` if the models were successfully assigned

        """
        # Ensure all models have their version and ID populated from the remote API
        fmu_models = self.model_client.retrieve_model_info_by_name(fmu_models)
        # Build the payload with the resolved FMU version IDs
        json_data = {"fmu-version-ids": [str(x.version) for x in fmu_models]}
        r = self.session.post(f"{API_ENDPOINT}/api/projects/{project_id}/fmus", json=json_data)
        return raise_if_not_ok(r).ok

    def deselect_all_models(self, project_id: ProjectID) -> bool:
        """Remove all FMU model assignments from a project.

        After this call the project will have no models selected and cannot
        start new simulations until models are re-assigned with :meth:`select_models`.

        Args:
            project_id: ID of the project to clear model selections from

        Returns:
            ``True`` if the deselection was accepted by the server

        """
        # Post an empty version-ID list to clear all selected models from the project
        r = self.session.post(f"{API_ENDPOINT}/api/projects/{project_id}/fmus", json={"fmu-version-ids": []})
        return raise_if_not_ok(r).ok

    def log_config(self, project_id: ProjectID) -> LoggingConfiguration:
        """Retrieve the current logging configuration for a project.

        The logging configuration controls which variables and at what
        frequency data is recorded during simulations.

        Args:
            project_id: ID of the project to retrieve logging configuration for

        Returns:
            The project's current logging settings

        """
        r = to_model(
            self.session.get(f"{API_ENDPOINT}/api/projects/{project_id}/log-config"),
            LoggingConfiguration,
        )
        return r

    def update_log_config(self, project_id: ProjectID, log_config: LoggingConfiguration) -> bool:
        """Replace the logging configuration for a project.

        Overwrites the project's existing logging settings with the provided
        configuration. This affects which variables are recorded in future
        simulation runs.

        Args:
            project_id: ID of the project to update
            log_config: New logging configuration to apply

        Returns:
            ``True`` if the server accepted the update

        """
        # log_config_stored = self.log_config(project_id)  # noqa: ERA001
        # log_config_stored.merge(log_config)  # noqa: ERA001
        # Serialize the logging configuration and PUT it to the project endpoint
        r = self.session.put(
            f"{API_ENDPOINT}/api/projects/{project_id}",
            json=log_config.model_dump(by_alias=True),
        )
        return raise_if_not_ok(r).ok

    def fmu_variables(self, project_id: ProjectID) -> list[FmuVariables]:
        """List all input, output, and parameter variables for every FMU model in a project.

        Args:
            project_id: ID of the project whose FMU variables to retrieve

        Returns:
            Variable definitions grouped by FMU model

        """
        r = to_models(self.session.get(f"{API_ENDPOINT}/api/projects/{project_id}/fmus/variables"), FmuVariables)
        return r

    def parameters_including_causality(self, project_id: ProjectID) -> list[SimulationParameters]:
        """Retrieve simulation parameters with variables classified by causality.

        Fetches the project's FMU variables, connection topology, and parameter
        configurations, then categorizes each variable as an input, output, or
        parameter based on its causality in the FMU model description.

        Args:
            project_id: ID of the project

        Returns:
            Parameter configurations with variables sorted into ``inputs``, ``outputs``, and ``parameters`` lists

        """
        # Fetch FMU variables and connection topology for the project
        variables = self.fmu_variables(project_id)
        conns = self.connections(project_id)
        # Build a mapping from instance name to FMU model type using the connection graph nodes
        inst_fmu_map = {x.instance: x.model_type for x in conns.nodes or []}
        # Build a mapping from FMU name to its variable name/causality pairs
        fmu_variable_map = {
            x.fmu_name: {y.name: y.causality for y in x.inputs + x.outputs + x.parameters} for x in variables
        }
        # Retrieve all parameter configurations for the project
        params = self.parameters(project_id)
        # Classify each variable into inputs, outputs, or parameters based on causality
        for param in params:
            for mp in param.model_parameters:
                for var in mp.variables:
                    fmu_name = inst_fmu_map.get(mp.name)

                    # This fmu was probably renamed but not removed in db, so we skip it
                    if fmu_name is None:
                        continue

                    causality = fmu_variable_map.get(fmu_name, {}).get(var.name, None)
                    assert causality is not None
                    if causality == "input":
                        mp.inputs.append(var)
                    elif causality == "output":
                        mp.outputs.append(var)
                    elif causality == "parameter":
                        mp.parameters.append(var)
                # Clear the generic variables list now that they have been categorized
                mp.variables.clear()
        return params

    def update_parameters(self, project_id: ProjectID, *simulation_parameters: SimulationParameters) -> bool:
        """Merge new or modified simulation parameters into a project's existing configuration.

        Fetches the current parameter sets (with causality), merges the
        provided parameters (new values take precedence), serializes the
        result as EDN, and uploads it to the project.

        Args:
            project_id: ID of the project to update
            *simulation_parameters: One or more parameter sets to merge into the project

        Returns:
            ``True`` if the server accepted the update

        """
        # Fetch existing parameters with causality info so the merge is complete
        existing_parameters = self.parameters_including_causality(project_id)
        # Merge the existing parameters with the new ones, with new values taking precedence
        params = merge_dicts(
            {k: v for x in existing_parameters for k, v in x.model_dump().items()},
            {k: v for x in simulation_parameters for k, v in x.model_dump().items()},
        )
        # Serialize the merged parameters as EDN and PUT to the project endpoint
        r = self.session.put(
            f"{API_ENDPOINT}/api/projects/{project_id}",
            json={"simulation-parameters": edn_format.dumps(params)},
        )
        return raise_if_not_ok(r).ok

    def delete_parameters(self, project_id: ProjectID, *parameter_names: str) -> bool:
        """Remove named parameter sets from a project's configuration.

        If specific names are given, only those sets are removed. If all
        parameter sets are deleted, a default ``"Config 1"`` placeholder is
        created. When called with no names, all parameters are cleared.

        Args:
            project_id: ID of the project to modify
            *parameter_names: Names of the parameter sets to delete

        Returns:
            ``True`` if the server accepted the deletion

        """
        params: dict[str, Any] | None = None

        if parameter_names:
            # Fetch existing parameters and exclude the ones being deleted
            existing_parameters = self.parameters_including_causality(project_id)
            # Fall back to a default "Config 1" entry if all parameters are removed
            params = {k: v for x in existing_parameters for k, v in x.dict().items() if k not in parameter_names} or {
                "Config 1": None
            }

        # Serialize the remaining parameters as EDN and PUT to the project endpoint
        r = self.session.put(
            f"{API_ENDPOINT}/api/projects/{project_id}",
            json={"simulation-parameters": edn_format.dumps(params)},
        )
        return raise_if_not_ok(r).ok

    def parameter_names(self, project_id: ProjectID) -> list[str]:
        """List the names of all parameter sets defined in a project.

        These names can be used with :meth:`parameter` to fetch individual
        parameter configurations.

        Args:
            project_id: ID of the project

        Returns:
            Names of the available parameter sets

        """
        r = self.session.get(
            f"{API_ENDPOINT}/api/projects/{project_id}/parameter-set-names",
        )
        return raise_if_not_ok(r).json()

    def parameter(self, project_id: ProjectID, config_name: str) -> SimulationParameters:
        """Retrieve a single named parameter set from a project.

        Use :meth:`parameter_names` to discover available set names.

        Args:
            project_id: ID of the project
            config_name: Name of the parameter set to retrieve

        Returns:
            The requested parameter configuration

        """
        # Fetch all simulation parameters and extract the one matching config_name
        model = to_model(
            self.session.get(
                f"{API_ENDPOINT}/api/projects/{project_id}/simulation-parameters",
            ),
            SimulationParameters,
            lambda x: SimulationParameters.from_response(x, config_name)[0],
        )

        return model

    def parameters(self, project_id: ProjectID) -> list[SimulationParameters]:
        """Retrieve all parameter sets configured for a project.

        Args:
            project_id: ID of the project

        Returns:
            Every parameter configuration defined in the project

        """
        models_ = to_models(
            self.session.get(
                f"{API_ENDPOINT}/api/projects/{project_id}/simulation-parameters",
            ),
            SimulationParameters,
            SimulationParameters.from_response,
        )

        return models_

    def connections(self, project_id: ProjectID) -> FmuConnections:
        """Retrieve the FMU connection graph for a project.

        The connection graph describes how FMU model instances are wired
        together — which output variables feed into which input variables.

        Args:
            project_id: ID of the project whose connections to retrieve

        Returns:
            The project's connection graph including nodes (model instances) and edges (variable connections)

        """
        model = to_model(
            self.session.get(f"{API_ENDPOINT}/api/projects/{project_id}/connections"),
            FmuConnections,
            FmuConnections.from_response,
        )
        return model

    def create_connections(
        self,
        project_id: ProjectID,
        conns: FmuConnections,
    ) -> bool:
        """Define the FMU connection graph for a project.

        Resolves each node in the connection graph to its FMU model, fetches
        variable metadata, validates that connected variables have compatible
        types, and uploads the complete graph to the project.

        Args:
            project_id: ID of the project to configure connections for
            conns: Connection graph describing model instances (nodes) and the variable wiring between them (edges)

        Returns:
            ``True`` if the server accepted the connection configuration

        Raises:
            FmuModelNotFoundError: If a node references an FMU model that cannot be found
            MissingVariablesError: If an edge references variables that do not exist on the connected models

        """
        # Fetch the FMU models associated with this project
        fmus: list[FmuModelInformation] = self.fmus(project_id)
        fmu_map: dict[str, FmuVariables] = {}

        # Resolve each connection node to its FMU model and fetch its variables
        for node in conns.nodes or []:
            # Match the node to an FMU by model ID or filename
            fmu = next(filter(lambda x: node.model_id == x.id or x.filename == node.fmu, fmus), None)

            if fmu is None:
                raise FmuModelNotFoundError(str(node.fmu))

            # Populate model type and ID from the matched FMU if not already set
            node.model_type = node.model_type or fmu.model_name
            node.model_id = str(node.model_id or fmu.id).upper()

            # Fetch variables and variable groups for this specific FMU version
            variables = to_model(
                self.session.get(f"{API_ENDPOINT}/api/fmus/{fmu.id}/version/{fmu.version}/variables"),
                FmuVariables,
            )
            variable_groups = to_models(
                self.session.get(f"{API_ENDPOINT}/api/fmus/{fmu.id}/version/{fmu.version}/osp-model-variable-groups"),
                FmuVariableGroup,
            )
            variables.variable_groups = variable_groups
            fmu_map[node.id] = variables

        # Validate and annotate each edge with the value type from source/target variables
        for edge in conns.edges or []:
            source_fmu = fmu_map.get(edge.source)
            target_fmu = fmu_map.get(edge.target)

            if source_fmu is None or target_fmu is None:
                raise FmuModelNotFoundError(f"{edge.source}-{edge.target}")

            try:
                # Ensure source and target variable types are compatible
                assert (
                    source_fmu.variables[edge.source_handle].value_type
                    == target_fmu.variables[edge.target_handle].value_type
                )
                edge.value_type = source_fmu.variables[edge.source_handle].value_type
            except KeyError as e:
                raise MissingVariablesError from e

        # Serialize the full connection graph and PUT it to the project endpoint
        payload = {"connections": json.dumps(conns.model_dump(by_alias=True, mode="json"))}

        return raise_if_not_json_ok(self.session.put(f"{API_ENDPOINT}/api/projects/{project_id}", json=payload)).ok

    def fmus(self, project_id: ProjectID) -> list[FmuModelInformation]:
        """List the FMU models currently assigned to a project.

        Args:
            project_id: ID of the project whose assigned models to retrieve

        Returns:
            Metadata for each FMU model selected in the project

        """
        r = to_models(self.session.get(f"{API_ENDPOINT}/api/projects/{project_id}/fmus"), FmuModelInformation)
        return r

    def completed_simulations(
        self,
        project_id: ProjectID,
        simulator_ids: Sequence[UUID] | None = None,
        limit: int = 10,
    ) -> list[SimulationInfo]:
        """Retrieve the history of completed simulations for a project.

        Returns metadata for finished simulation runs, optionally filtered
        to only those executed by specific simulators.

        Args:
            project_id: ID of the project whose simulation history to query
            simulator_ids: If provided, only return simulations run by these simulators
            limit: Maximum number of results to return from the API, by default 10

        Returns:
            Metadata for each matching completed simulation

        """
        # Fetch completed simulations from the API with a result limit
        r = to_models(
            self.session.get(
                f"{API_ENDPOINT}/api/projects/{project_id}/simulations/completed",
                params={
                    "limit": limit,
                },
            ),
            SimulationInfo,
            lambda x: x["data"],
        )

        # Optionally filter results to only include the specified simulator IDs
        if simulator_ids:
            simulator_ids_set = {to_uuid(x) for x in simulator_ids}
            r = list(filter(lambda x: to_uuid(x.simulator) in simulator_ids_set, r))

        return r

    def completed_simulations_by_batch_id(
        self,
        project_id: ProjectID,
        batch_id: UUID,
        limit: int = 10,
    ) -> list[SimulationInfo]:
        """Retrieve completed simulations that belong to a specific batch.

        A batch groups multiple simulations that were started together.
        This method fetches recent completed simulations and filters them
        to those matching the given ``batch_id``.

        Args:
            project_id: ID of the project to query
            batch_id: Batch identifier to filter by
            limit: Maximum number of completed simulations to fetch before filtering, by default 10

        Returns:
            Completed simulations belonging to the specified batch

        """
        # Retrieve all completed simulations up to the limit, then filter by batch ID
        sims = self.completed_simulations(project_id, limit=limit)
        return list(filter(lambda x: x.batch_id == batch_id, sims))

    def current_simulators(self, project_id: ProjectID) -> list[SimulatorStatus]:
        """List all simulators that are currently active for a project.

        Returns status information for simulators that have been created but
        not yet terminated or cleaned up.

        Args:
            project_id: ID of the project whose active simulators to list

        Returns:
            Status snapshots for each currently active simulator

        """
        # Fetch the list of currently active simulators for the project
        r = to_models(
            self.session.get(
                f"{API_ENDPOINT}/api/projects/{project_id}/simulators/current",
            ),
            SimulatorStatus,
        )
        return r


class PyStclient:
    """STC Python client.

    Handles OAuth2 authentication (including token caching and refresh)
    and exposes sub-clients for interacting with different areas of the
    STC platform:

    - :attr:`project` — create, configure, and manage projects
    - :attr:`model` — upload, search, and delete FMU models
    - :attr:`simulator` — provision, control, and monitor simulators
    - :attr:`measurement` — query simulation result data

    Subclasses must call :meth:`authenticate` after construction to
    establish an authenticated session before using the sub-clients.
    """

    _token_endpoint: str
    _authorization_endpoint: str
    _jwks_uri: str
    _key_public: KeySet

    def __init__(self) -> None:
        # These are initialized in authenticate() -> _create_session() -> _initialize_sub_clients()
        self._session: OAuth2Session
        self._token: TokenType
        self.project: ProjectClient
        self.model: ModelClient
        self.simulator: SimulatorClient
        self.measurement: MeasurementClient

        # Fetch OpenID Connect discovery metadata from the configured endpoint
        response = requests.get(DISCOVERY_ENDPOINT, timeout=60)
        if response.ok:
            response = response.json()
            # Extract OAuth2 endpoints from the discovery document
            self._token_endpoint = response["token_endpoint"]
            self._authorization_endpoint = response["authorization_endpoint"]
            self._jwks_uri = response["jwks_uri"]
            # Import the public key set used for JWT token validation
            self._key_public = KeySet.import_key_set(requests.get(self._jwks_uri, timeout=60).json())
        else:
            raise ConnectionError("Could not connect to the discovery endpoint!")

    @property
    def token(self) -> TokenType:
        """Access the current OAuth2 token used for API requests.

        Returns:
            The active authentication token (may be a cached or freshly issued token)

        """
        return self._token

    def _initialize_sub_clients(self, session: RequestsSession) -> None:
        self.model = ModelClient(session)
        self.project = ProjectClient(session, self.model)
        self.simulator = SimulatorClient(session)
        self.measurement = MeasurementClient(session)

    @staticmethod
    def _refresh_token(
        token: TokenType,
    ) -> None:
        logger.info("Refreshing token..")
        cache_token(token)

    def _create_session(self, token: TokenType | None = None) -> tuple[str, str, str]:
        url = urlparse(REPLY_URL)

        self._session = OAuth2Session(
            client_id=CLIENT_ID,
            scope=f"openid offline_access https://dnvglb2cprod.onmicrosoft.com/{API_ID}/user_impersonation",
            redirect_uri=url.geturl(),
            response_type="code",
            response_mode="form_post",
            code_challenge_method="S256",
            token_endpoint=self._token_endpoint,
            token=token,
            update_token=self._refresh_token,
        )

        # Initializing sub-clients
        self._initialize_sub_clients(self._session)  # pyright: ignore[reportArgumentType]  # OAuth2Session extends Session

        code_verifier = generate_token(48)

        authorization_uri, state = self._session.create_authorization_url(
            self._authorization_endpoint, code_verifier=code_verifier
        )
        return authorization_uri, state, code_verifier

    def _retrieve_token(self, state: str, code_verifier: str) -> TokenType:
        url = urlparse(REPLY_URL)

        httpd = HTTPServer((url.hostname or "127.0.0.1", url.port or 9090), HandleAuthentication)
        httpd.handle_request()

        assert oidc_code is not None

        if state != oidc_code["state"][0]:
            raise RuntimeError("Mismatching state while verifying the retrieved authorization code!")

        authorization_code = oidc_code["code"][0]
        nonce = generate_token(48)
        token = self._session.fetch_token(
            self._token_endpoint,
            code_verifier=code_verifier,
            code=authorization_code,
            grant_type="authorization_code",
            nonce=nonce,
        )
        assert isinstance(token, dict)
        _ = validate_token(
            access_token=str(token["access_token"]),
            key=self._key_public,
            nonce=nonce,
        )
        self._token = token
        cache_token(self._token)
        return self._token

    def _cached_token(self) -> TokenType | None:
        cached_token = read_token()
        if cached_token is not None:
            _ = validate_token(
                access_token=cached_token["access_token"],
                key=self._key_public,
            )
            token = OAuth2Token.from_dict(cached_token)
            assert isinstance(token, OAuth2Token)
            self._token = token
            return token
        return None

    def authenticate(self, token: TokenType | None = None) -> TokenType:
        """Establish an authenticated session with the STC API.

        Attempts to reuse an existing or cached token. If no valid token is
        available (or the cached token has expired), an interactive OAuth2
        authorization-code flow is initiated — a browser window is opened
        for the user to log in, and the resulting token is cached for future
        sessions.

        This method must be called before using any of the sub-clients
        (:attr:`project`, :attr:`model`, :attr:`simulator`, :attr:`measurement`).

        Args:
            token: A pre-existing token to use instead of performing authentication. When ``None``,
            the client first checks for a cached token on disk.l

        Returns:
            The active authentication token for the session

        """
        try:
            # Attempt to use a cached token if none was provided
            if token is None:
                token = self._cached_token()

            # If a valid token is available, create a session with it and return early
            if token is not None:
                _ = self._create_session(token)
                self._token = token
                return self._token
            logger.info("Authenticating..")
        except ExpiredTokenError:
            logger.info("The token has expired, re-authenticating...")
        except Exception as e:
            logger.exception("Unable to use cached token, re-authenticating...", exc_info=e)

        # No valid cached token available; start the interactive OAuth2 authorization flow
        authorization_uri, state, code_verifier = self._create_session()
        # Open the authorization URL in the user's browser for login
        _ = webbrowser.open(authorization_uri)

        # Wait for the browser redirect and exchange the authorization code for a token
        token = self._retrieve_token(state, code_verifier)

        # Ensure the token is active before returning
        _ = self._session.ensure_active_token(token)

        return token
