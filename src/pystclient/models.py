#  Copyright (c) 2026 DNV AS.
#
#  SPDX-License-Identifier: MPL-2.0
#
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Data models for STC API interactions."""

# pyright: reportUnknownMemberType = false
import datetime
import json
import uuid
from collections.abc import Mapping
from functools import cached_property
from typing import Annotated, Any, Self

import edn_format
from edn_format import Keyword
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    computed_field,
    field_serializer,
    model_serializer,
    model_validator,
)

from pystclient.exception import UnexpectedResponseDataError
from pystclient.types import (
    FmuCausalityType,
    FmuVariableType,
    FmuVariableTypeEnum,
    SimulationType,
    from_string_value,
)
from pystclient.utils import random_string, stringify_keys, without_none_values

UUID = Annotated[str | uuid.UUID, PlainSerializer(str, return_type=str)]


#####################################################
# Response models
#####################################################


class ProjectInformation(BaseModel):
    """Information about an STC project."""

    id: uuid.UUID = Field(alias="project/id")
    name: str = Field(alias="project/name")
    created_at: datetime.datetime = Field(alias="project/created-at")
    version: uuid.UUID = Field(alias="project/version-id")


class FmuModelInformation(BaseModel):
    """Information about an FMU model."""

    # STC model id
    id: uuid.UUID = Field(alias="fmu/id")
    # STC model version
    version: uuid.UUID = Field(alias="fmu/version-id")
    filename: str = Field(alias="fmu/filename")
    allows_multiple_instances: Annotated[bool, Field(alias="fmu/allows-multiple-instances?")] = False

    # Same as fmi_version
    fmu_version: Annotated[UUID | None, Field(alias="fmu/version")] = None
    model_name: str = Field(alias="fmu/name")
    access_rights: Annotated[list[str], Field(alias="user/access-rights")] = []
    platforms: list[str] = Field(alias="fmu/platforms")
    fmu_description: Annotated[str, Field(alias="fmu/description")] = ""
    fmi_version: Annotated[str | None, Field(alias="fmi/fmi-version")] = None


class FmuVariable(BaseModel):
    """FMU variable definition."""

    name: str = Field(alias="variable/name")
    causality: str = Field(alias="variable/causality")
    start_value: Annotated[str | None, Field(alias="variable/start-type")] = None
    variability: Annotated[str | None, Field(alias="variable/variability")] = None
    value_type: str = Field(alias="variable/value-type")


class FmuVariableGroup(BaseModel):
    """FMU variable group definition."""

    name: str = Field(alias="variable-group/name")
    tag: str = Field(alias="variable-group/tag")
    variables: Annotated[Mapping[str, str] | None, Field(alias="variable-group/variables")] = {}
    groups: Annotated[list[Mapping[str, Any]] | None, Field(alias="variable-group/groups")] = []
    value_type: str = "variable-group"


class Simulation(BaseModel):
    """Simulation information."""

    id: Annotated[UUID, Field(alias="simulation/id")]
    batch_id: Annotated[UUID | None, Field(alias="simulation/batch-id")] = None


class SimulatorStatus(BaseModel):
    """Status information for a simulator.

    Notes:
    ------
        For type == CENTRALIZED, API does not include simulation in a status for the first few seconds after
        simulator creation.
    """

    id: Annotated[UUID, Field(alias="simulator/id")]
    type: Annotated[str, Field(alias="simulator/type")]
    display_name: Annotated[str, Field(alias="simulator/display-name")]
    status: Annotated[str, Field(alias="simulator/status")]
    project_id: Annotated[UUID, Field(alias="simulator/project-id")]
    simulation: Annotated[Simulation | None, Field(alias="simulator/simulation")] = None
    is_connected: Annotated[bool, Field(alias="simulator/connected?")] = False
    end_time: Annotated[float | None, Field(alias="simulator/end-time")] = None
    simulation_time: Annotated[float | None, Field(alias="simulator/simulation-time")] = None
    batch_id: Annotated[UUID | None, Field(alias="simulator/batch-id")] = None


class FmuVariables(BaseModel):
    """FMU variables collection."""

    fmu_name: Annotated[str | None, Field(alias="fmu/name")] = None
    inputs: Annotated[list[FmuVariable], Field(alias="fmu/inputs")] = []
    outputs: Annotated[list[FmuVariable], Field(alias="fmu/outputs")] = []
    parameters: Annotated[list[FmuVariable], Field(alias="fmu/parameters")] = []
    variable_groups: Annotated[list[FmuVariableGroup], Field(alias="fmu/variable-groups")] = []

    @computed_field
    @cached_property
    def variables(self) -> Mapping[str, FmuVariable | FmuVariableGroup]:
        """Computed field that maps variable names to variables."""
        return {x.name: x for x in self.inputs + self.outputs + self.variable_groups}


class MeasurementVariables(BaseModel):
    """Measurement variable definition."""

    name: str
    type: str
    variability: str
    reference: int
    causality: FmuCausalityType
    start_value: Annotated[float , Field(alias="start-value")] = 0


class MeasurementInstance(BaseModel):
    """Measurement instance information."""

    description: str | None = None
    fmu_id: Annotated[UUID, Field(alias="fmu-uuid")]
    instance_name: Annotated[str, Field(alias="instance-name")]
    name: str
    variables: list[MeasurementVariables] = []
    instance_id: Annotated[str, Field(alias="instance-id")]
    author: str
    version: str | None = None


class MeasurementMetadata(BaseModel):
    """Metadata for measurement."""

    start_time: Annotated[int, Field(alias="start-time")]
    end_time: Annotated[int, Field(alias="end-time")]
    measurement: UUID
    instances: list[MeasurementInstance] = []


class Measurements(BaseModel):
    """Measurement data."""

    id: Annotated[str, Field(alias="plot/measurement-id")]
    simulation_id: Annotated[str, Field(alias="plot/simulation-id")]
    created_at: Annotated[datetime.datetime, Field(alias="plot/created-at")]
    metadata: Annotated[MeasurementMetadata, Field(alias="plot/metadata")]
    filename: Annotated[str, Field(alias="plot/filename")]
    parameter_set_name: Annotated[str | None, Field(alias="plot/parameter-set-name")] = None
    simulation_name: Annotated[str | None, Field(alias="plot/simulation-name")] = None


class QueryResult(BaseModel):
    """Result of a query operation."""

    class Statistics(BaseModel):  # noqa: D106
        mean: float
        min: float
        max: float
        stdev: float

    signal: str
    x: list[str]
    y: list[float]
    module: str
    statistics: Statistics


class UploadedModelInfo(BaseModel):
    """Information about an uploaded model."""

    id: uuid.UUID = Field(alias="fmu/id")
    name: str = Field(alias="fmu/name")


class SimulationInfo(BaseModel):
    """Information about a simulation run."""

    id: Annotated[UUID, Field(alias="simulation/id")]
    name: Annotated[str, Field(alias="simulation/name")]
    simulator: Annotated[UUID, Field(alias="simulation/simulator")]
    created: Annotated[str, Field(alias="simulation/created")]
    project_id: Annotated[UUID, Field(alias="simulation/project")]
    simulation_type: Annotated[str, Field(alias="simulation/type")]
    parameter_set_name: Annotated[str, Field(alias="simulation/parameter-set-name")]
    simulation_time: Annotated[float, Field(alias="simulation/simulation-time")] = 0
    has_time_series_data: Annotated[bool, Field(alias="simulation/has-influx-data?")] = False
    batch_id: Annotated[UUID | None, Field(alias="simulation/batch-id")] = None


#####################################################
# Request models
#####################################################


class FmuSelect(BaseModel):
    """FMU model selection."""

    filename: str | None = None
    version: uuid.UUID | None = None
    id: uuid.UUID | None = None

    @model_validator(mode="after")
    def check_one_exists(self) -> Self:
        """Validate that at least one identifier is provided."""
        assert self.filename is not None or self.version is not None or self.id is not None, (
            "Please provide either filename or version or id"
        )
        return self


class BaseProject(BaseModel):
    """Base project configuration."""

    name: str = "STCProject"
    description: str | None = None


class ModelVariable(BaseModel):
    """Model variable definition."""

    name: str
    type: FmuVariableTypeEnum = FmuVariableTypeEnum.REAL
    initial_value: FmuVariableType


class ModelParameters(BaseModel):
    """Model parameters configuration."""

    name: str
    inputs: list[ModelVariable] = []
    outputs: list[ModelVariable] = []
    parameters: list[ModelVariable] = []
    step_size: float | None = None
    variables: list[ModelVariable] = []


class SimulationParameters(BaseModel):
    """Simulation parameters configuration."""

    config_name: str = "Config 1"
    base_step_size: Annotated[float | None, Field(alias="base-step-size")] = None
    end_time: Annotated[int | None, Field(alias="end-time")] = None
    model_parameters: list[ModelParameters] = []
    model_config = ConfigDict(populate_by_name=True)

    @staticmethod
    def from_response(resp: dict[Any, Any], config_name: str | None = None) -> list[dict[str, Any]]:
        """Parse simulation parameters from API response."""
        params = edn_format.loads(resp["project/simulation-parameters"]) or {"Config 1": None}

        config_names = [config_name] if config_name is not None else params.keys()
        param_list = []

        for name in config_names:
            if config := params.get(name, {}):
                config = stringify_keys(config)
                model_parameters = [
                    ModelParameters(
                        name=k,
                        variables=[
                            ModelVariable(
                                name=varName,
                                type=(p := FmuVariableTypeEnum(info["type"])),
                                initial_value=from_string_value(info["value"], p),
                            )
                            for varName, info in v.get("initial-values", {}).items()
                            if info["value"] is not None and info["value"] != "None"
                        ],
                        step_size=v.get("step-size", None),
                    )
                    for k, v in config.items()
                    if isinstance(v, (dict, Mapping))
                ]
                param_list.append({**config, "config_name": name, "model_parameters": model_parameters})

        return param_list

    @model_serializer
    def to_dict(self) -> dict[str, Any]:
        """Serialize simulation parameters to dictionary."""
        config: dict[str, Any] = {
            self.config_name: {
                **{
                    model.name: {
                        Keyword("initial-values"): {
                            **{
                                variable.name: {
                                    Keyword("type"): variable.type.value,
                                    Keyword("value"): (
                                        str(variable.initial_value).lower()
                                        if variable.type
                                        in [
                                            FmuVariableTypeEnum.BOOL,
                                            FmuVariableTypeEnum.BOOLEAN,
                                        ]
                                        else str(variable.initial_value)
                                    ),
                                }
                                for variable in model.inputs + model.outputs + model.parameters
                            }
                        },
                        Keyword("step-size"): (str(model.step_size) if model.step_size is not None else None),
                    }
                    for model in self.model_parameters
                },
                Keyword("base-step-size"): (str(self.base_step_size) if self.base_step_size is not None else None),
                Keyword("end-time"): (str(self.end_time) if self.end_time is not None else None),
            }
        }
        return without_none_values(config)


class SimulationConfig(BaseModel):
    """Simulation configuration."""

    project_id: UUID = Field(serialization_alias="project-id")
    os: str = "linux"
    display_name: str = Field(serialization_alias="display-name", default="STCSimulation")
    type: SimulationType = SimulationType.DISTRIBUTED

    # Optional fields
    project_version_id: Annotated[UUID | None, Field(serialization_alias="project-version-id")] = None
    simulation_name: Annotated[str | None, Field(None, serialization_alias="simulation-name")] = None
    parameter_set_names: Annotated[list[str], Field(None, serialization_alias="parameter-set-names")]
    batch_size: Annotated[int, Field(None, serialization_alias="batch-size")] = 1
    is_interactive: Annotated[bool, Field(serialization_alias="interactive?")] = False

    @model_validator(mode="after")
    def validate_interactive(self) -> Self:
        """Non-interactive mode is only supported for distributed simulations."""
        if not self.is_interactive and self.type == SimulationType.CENTRALIZED:
            raise ValueError("Non-interactive mode is only supported for distributed simulations")
        return self

    @model_validator(mode="after")
    def validate_batch_size(self) -> Self:
        """Validate batch size is within acceptable range."""
        batch_size_min: int = 1
        batch_size_max: int = 5
        assert batch_size_min <= self.batch_size <= batch_size_max, (
            f"The allowed batch size is [{batch_size_min}, {batch_size_max}] but got {self.batch_size}"
        )
        assert len(self.parameter_set_names) > 0, "You must specify at least one parameter-set name"
        return self

    @field_serializer("batch_size", when_used="json")
    def serialize_batch_size(self, batch_size: int) -> str:
        """Serialize batch size to string."""
        return str(batch_size)

    @field_serializer("project_id", when_used="json")
    def serialize_project_id(self, project_id: UUID) -> str:
        """Serialize project ID to uppercase string."""
        return str(project_id).upper()


def position_transformer(
    v: Mapping[str, float] | tuple[float, float],
    *args: Any,  # noqa: ANN401, ARG001
    **kwargs: Any,  # noqa: ANN401, ARG001
) -> tuple[float, float]:
    """Transform position from mapping or tuple."""
    return (v["x"], v["y"]) if isinstance(v, Mapping) else v


class FmuNode(BaseModel):
    """FMU node configuration."""

    model_config = ConfigDict(populate_by_name=True)

    instance: str = Field(exclude=True, alias="label")  # label
    fmu: Annotated[str | None, Field(exclude=True)] = None

    # Fmu filename without extension
    model_type: Annotated[str | None, Field(exclude=True, alias="model-type")] = None

    # STC model ID
    model_id: Annotated[UUID | None, Field(exclude=True, alias="model-id")] = None

    id: str = Field(default_factory=lambda: f"Model-{random_string()}")
    position: Annotated[tuple[float, float], BeforeValidator(position_transformer)] = (1000, 1000)
    type: str = "io-node"

    def __init__(
        self,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        try:
            super().__init__(
                **kwargs
                | (
                    {
                        "instance": data["label"],
                        "model_type": data["model-type"],
                        "model_id": data["model-id"],
                    }
                    if (data := kwargs.get("data")) is not None
                    else {}
                )
            )
        except KeyError as e:
            raise UnexpectedResponseDataError from e

    @computed_field
    def data(
        self,
    ) -> dict[str, Any]:
        """Compute data field for serialization."""
        return {"model-type": self.model_type, "label": self.instance, "model-id": self.model_id}

    @field_serializer("position", when_used="json")
    def position_serializer(self, position: tuple[float, float]) -> dict[str, float]:
        """Serialize position to dictionary."""
        return {"x": position[0], "y": position[1]}

    @model_validator(mode="after")
    def model_validator(self) -> Self:
        """Validate that either fmu or model_id is set."""
        if self.fmu is None and self.model_id is None:
            raise ValueError("Either fmu or model_id must be set")
        return self

    def __hash__(self) -> int:
        """Return hash of the node ID."""
        return hash(self.id)


class FmuNodeEdge(BaseModel):
    """FMU node edge (connection) configuration."""

    model_config = ConfigDict(populate_by_name=True)
    value_type: Annotated[str | None, Field(alias="value-type")] = None
    id: UUID | None
    source: str
    source_handle: Annotated[str, Field(alias="source-handle")]
    target: str
    target_handle: Annotated[str, Field(alias="target-handle")]

    def __init__(
        self,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        try:
            super().__init__(
                **kwargs
                | (
                    {
                        "value_type": kwargs["data"]["value-type"],
                    }
                    if "data" in kwargs
                    else {}
                )
            )
        except KeyError as e:
            raise UnexpectedResponseDataError from e

    @computed_field
    def data(
        self,
    ) -> dict[str, Any]:
        """Compute data field for serialization."""
        return {"value-type": self.value_type}


class FmuConnections(BaseModel):
    """FMU connections configuration."""

    nodes: list[FmuNode] | None = None
    edges: list[FmuNodeEdge] | None = None

    @staticmethod
    def from_response(r: dict[str, Any]) -> dict[str, Any]:
        """Parse FMU connections from API response."""
        connections = json.loads(r.get("project/connections", "{}"))
        nodes = connections.get("nodes", [])
        edges = connections.get("edges", [])
        return {"nodes": nodes, "edges": edges}

    @staticmethod
    def build_connections(connections: list[tuple[FmuNode, str, FmuNode, str] | FmuNode]) -> "FmuConnections":
        """Build FMU connections from list of connections and nodes."""
        conns: list[tuple[FmuNode, str, FmuNode, str]] = []
        fmu_nodes: list[FmuNode] = []
        for x in connections:
            if isinstance(x, FmuNode):
                fmu_nodes.append(x)
            else:
                conns.append(x)
        edges = [
            FmuNodeEdge(
                id=uuid.uuid4(),
                source=x[0].id,
                source_handle=x[1],
                target=x[2].id,
                target_handle=x[3],
            )
            for x in conns
        ]
        nodes = list({x for a, _, c, _ in conns for x in (a, c)})
        nodes += fmu_nodes
        return FmuConnections(nodes=nodes, edges=edges)


class LoggingConfiguration(BaseModel):
    """Logging configuration for simulations."""

    model_config = ConfigDict(populate_by_name=True)
    post_plotting: bool = False

    log_config_stored: Annotated[str, Field(alias="project/log-config", exclude=True)] = "{}"

    def __init__(
        self,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """Initialize logging configuration."""
        super().__init__(**kwargs)
        log_config = edn_format.loads(self.log_config_stored)
        assert isinstance(log_config, Mapping)
        self.post_plotting = log_config.get("_config", {}).get("post-plotting?", self.post_plotting)

    @model_serializer
    def to_dict(self) -> dict[str, Any]:
        """Serialize logging configuration to dictionary."""
        log_config = edn_format.loads(self.log_config_stored)
        assert isinstance(log_config, Mapping)
        return {
            "log-config": edn_format.dumps(
                {
                    **log_config,
                    "_config": {"post-plotting?": self.post_plotting},
                }
            ),
        }

    def merge(self, *others: "LoggingConfiguration") -> None:
        """Merge logging configurations."""
        config_stored = edn_format.loads(self.log_config_stored)
        assert isinstance(config_stored, Mapping)

        for other in others:
            self.post_plotting = other.post_plotting
            other_config_stored = edn_format.loads(other.log_config_stored)
            assert isinstance(other_config_stored, Mapping)
            config_stored = {**config_stored, **other_config_stored}

        self.log_config_stored = str(edn_format.dumps(config_stored))


class QueryVariable(MeasurementVariables):
    """Query variable configuration."""

    model_config = ConfigDict(populate_by_name=True)
    instance_id: Annotated[UUID | None, Field(alias="instance-id")] = None
    instance_name: Annotated[str | None, Field(exclude=True)] = None
    # Required from parent: name and causality

    def __init__(
        self,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        super().__init__(
            **kwargs,
            reference=0,
            start_value=0,
            type="",
            variability="",
        )

    @model_validator(mode="after")
    def check_name_id(self) -> Self:
        """Validate that either instance ID or name is set."""
        assert self.instance_id is not None or self.instance_name is not None, "One of instance id or name must be set!"
        return self


class MeasurementQuery(BaseModel):
    """Measurement query configuration."""

    model_config = ConfigDict(populate_by_name=True)
    variables: list[QueryVariable]
    time_from: Annotated[int, Field(alias="from")]
    time_to: Annotated[int, Field(alias="to")]
    window_period: Annotated[str, Field(alias="window-period")] = "20ms"

    @model_validator(mode="after")
    def check_one_exists(self) -> Self:
        """Validate that time_from is less than time_to."""
        assert self.time_from < self.time_to, "Query variable `time_to` must be strictly greater than `time_from`"
        return self
