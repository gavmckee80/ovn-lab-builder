"""
Unit tests for the schema module.
"""

import json
import pytest
from pydantic import ValidationError

from ovn_lab_builder.schema import (
    AddressingMode, LabConfig, Port, Switch, SwitchType, VPC
)


def test_vpc_validation():
    """Test VPC schema validation."""
    # Valid VPC
    vpc = VPC(name="test", mac_prefix="e1:cc:ff", id=1, port_count=2)
    assert vpc.name == "test"
    assert vpc.mac_prefix == "e1:cc:ff"
    assert vpc.id == 1
    assert vpc.port_count == 2

    # Invalid MAC prefix format
    with pytest.raises(ValidationError):
        VPC(name="test", mac_prefix="invalid", id=1)

    # MAC prefix with wrong number of octets
    with pytest.raises(ValidationError):
        VPC(name="test", mac_prefix="e1:cc", id=1)

    # MAC prefix with octets of wrong length
    with pytest.raises(ValidationError):
        VPC(name="test", mac_prefix="e1:c:ff", id=1)


def test_port_validation():
    """Test port schema validation."""
    # Valid dynamic port
    port = Port(name="lsp1", addressing=AddressingMode.DYNAMIC)
    assert port.name == "lsp1"
    assert port.addressing == AddressingMode.DYNAMIC
    assert port.ip is None

    # Valid static port
    port = Port(name="lsp2", addressing=AddressingMode.STATIC, ip="192.168.1.2")
    assert port.name == "lsp2"
    assert port.addressing == AddressingMode.STATIC
    assert port.ip == "192.168.1.2"

    # Missing IP for static addressing
    with pytest.raises(ValidationError):
        Port(name="lsp3", addressing=AddressingMode.STATIC)


def test_switch_validation():
    """Test switch schema validation."""
    # Valid switch with port_count
    switch = Switch(
        name="ls1",
        id=1,
        type=SwitchType.NORMAL,
        subnet="192.168.1.0/24",
        dhcp_enable=True,
        routed=True,
        port_count=2,
    )
    assert switch.name == "ls1"
    assert switch.id == 1
    assert switch.type == SwitchType.NORMAL
    assert switch.subnet == "192.168.1.0/24"
    assert switch.dhcp_enable is True
    assert switch.routed is True
    assert switch.port_count == 2
    assert switch.ports is None

    # Valid switch with explicit ports
    switch = Switch(
        name="ls2",
        id=2,
        type=SwitchType.P2P,
        subnet="192.168.2.0/31",
        ports=[
            Port(name="lsp1", addressing=AddressingMode.DYNAMIC),
            Port(name="lsp2", addressing=AddressingMode.STATIC, ip="192.168.2.1"),
        ],
    )
    assert switch.name == "ls2"
    assert switch.id == 2
    assert switch.type == SwitchType.P2P
    assert switch.subnet == "192.168.2.0/31"
    assert switch.dhcp_enable is False  # Default
    assert switch.routed is False  # Default
    assert switch.port_count is None
    assert len(switch.ports) == 2
    assert switch.ports[0].name == "lsp1"
    assert switch.ports[1].name == "lsp2"

    # Invalid subnet
    with pytest.raises(ValidationError):
        Switch(
            name="ls3",
            id=3,
            type=SwitchType.NORMAL,
            subnet="invalid",
            port_count=2,
        )

    # Both port_count and ports specified
    with pytest.raises(ValidationError):
        Switch(
            name="ls4",
            id=4,
            type=SwitchType.NORMAL,
            subnet="192.168.4.0/24",
            port_count=2,
            ports=[Port(name="lsp1", addressing=AddressingMode.DYNAMIC)],
        )


def test_lab_config_validation():
    """Test lab configuration validation."""
    # Valid config with auto-generated ports
    config_data = {
        "vpc": {
            "name": "vlab",
            "mac_prefix": "e1:cc:ff",
            "id": 1,
            "port_count": 2
        },
        "switches": [
            {
                "name": "ls1",
                "id": 1,
                "type": "normal",
                "subnet": "192.168.1.0/24",
                "dhcp_enable": True,
                "routed": True,
                "port_count": 6
            }
        ]
    }
    config = LabConfig(**config_data)
    assert config.vpc.name == "vlab"
    assert len(config.switches) == 1
    assert config.switches[0].name == "ls1"
    assert config.switches[0].port_count == 6

    # Valid config with explicit ports
    config_data = {
        "vpc": {
            "name": "vlab",
            "mac_prefix": "e1:cc:ff",
            "id": 1
        },
        "switches": [
            {
                "name": "ls1",
                "id": 1,
                "type": "normal",
                "subnet": "192.168.1.0/24",
                "ports": [
                    {"name": "lsp1", "addressing": "dynamic"},
                    {"name": "lsp2", "addressing": "static", "ip": "192.168.1.10"}
                ]
            }
        ]
    }
    config = LabConfig(**config_data)
    assert config.vpc.name == "vlab"
    assert len(config.switches) == 1
    assert config.switches[0].name == "ls1"
    assert len(config.switches[0].ports) == 2

    # Duplicate switch IDs
    config_data = {
        "vpc": {
            "name": "vlab",
            "mac_prefix": "e1:cc:ff",
            "id": 1,
            "port_count": 2
        },
        "switches": [
            {
                "name": "ls1",
                "id": 1,
                "type": "normal",
                "subnet": "192.168.1.0/24",
                "port_count": 2
            },
            {
                "name": "ls2",
                "id": 1,  # Duplicate ID
                "type": "normal",
                "subnet": "192.168.2.0/24",
                "port_count": 2
            }
        ]
    }
    with pytest.raises(ValidationError):
        LabConfig(**config_data)

    # Missing required fields
    config_data = {
        "vpc": {
            "name": "vlab",
            "id": 1,
            # Missing mac_prefix
        },
        "switches": []
    }
    with pytest.raises(ValidationError):
        LabConfig(**config_data)