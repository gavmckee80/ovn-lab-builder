"""
Unit tests for the topology module.
"""

import ipaddress
import pytest

from ovn_lab_builder.schema import AddressingMode, LabConfig, Port, Switch, SwitchType, VPC
from ovn_lab_builder.topology import LogicalRouter, LogicalSwitch, LogicalSwitchPort, Topology


def test_logical_switch_port():
    """Test LogicalSwitchPort class."""
    # Dynamic addressing port
    port = LogicalSwitchPort(
        vpc_name="vlab",
        switch_name="ls1",
        port_name="lsp1",
        vpc_id=1,
        switch_id=2,
        port_index=3,
        mac_prefix="e1:cc:ff",
        addressing=AddressingMode.DYNAMIC,
    )
    
    assert port.full_name == "vlab-ls1-lsp1"
    assert port.mac == "e1:cc:ff:01:02:03"
    assert port.port_security == ["e1:cc:ff:01:02:03"]
    
    # Static addressing port
    port = LogicalSwitchPort(
        vpc_name="vlab",
        switch_name="ls1",
        port_name="lsp2",
        vpc_id=1,
        switch_id=2,
        port_index=4,
        mac_prefix="e1:cc:ff",
        addressing=AddressingMode.STATIC,
        ip="192.168.1.10",
    )
    
    assert port.full_name == "vlab-ls1-lsp2"
    assert port.mac == "e1:cc:ff:01:02:04"
    assert port.port_security == ["e1:cc:ff:01:02:04 192.168.1.10"]


def test_logical_switch():
    """Test LogicalSwitch class."""
    # Normal switch
    switch = LogicalSwitch(
        vpc_name="vlab",
        name="ls1",
        switch_id=1,
        switch_type=SwitchType.NORMAL,
        subnet="192.168.1.0/24",
        dhcp_enable=True,
        routed=True,
    )
    
    assert switch.full_name == "vlab-ls1"
    assert switch.subnet_str == "192.168.1.0/24"
    assert switch.subnet == ipaddress.IPv4Network("192.168.1.0/24")
    assert switch.router_port_ip == "192.168.1.1/24"
    assert switch.dhcp_server_mac == "e1:cc:ff:01:01:00"
    assert switch.router_port_mac == "e1:cc:ff:01:01:00"
    
    # Verify usable IPs exclude the first 4 for DHCP
    usable_ips = switch.usable_ips
    assert len(usable_ips) == 251  # 256 - 1 (network) - 1 (broadcast) - 4 (DHCP reserved)
    assert str(usable_ips[0]) == "192.168.1.5"  # First usable IP after reserved
    
    # P2P switch with /31 subnet
    switch = LogicalSwitch(
        vpc_name="vlab",
        name="ls2",
        switch_id=2,
        switch_type=SwitchType.P2P,
        subnet="192.168.2.0/31",
        dhcp_enable=False,
        routed=False,
    )
    
    assert switch.full_name == "vlab-ls2"
    assert switch.subnet_str == "192.168.2.0/31"
    assert switch.subnet == ipaddress.IPv4Network("192.168.2.0/31")
    assert switch.router_port_ip is None  # Not routed
    assert switch.router_port_mac is None  # Not routed
    
    # Verify usable IPs for /31 subnet
    usable_ips = switch.usable_ips
    assert len(usable_ips) == 2  # Both addresses usable in /31
    assert str(usable_ips[0]) == "192.168.2.0"
    assert str(usable_ips[1]) == "192.168.2.1"


def test_logical_router():
    """Test LogicalRouter class."""
    router = LogicalRouter(vpc_name="vlab")
    assert router.full_name == "vlab-lr"
    assert len(router.switch_ports) == 0
    
    # Add a switch to the router
    switch = LogicalSwitch(
        vpc_name="vlab",
        name="ls1",
        switch_id=1,
        switch_type=SwitchType.NORMAL,
        subnet="192.168.1.0/24",
        dhcp_enable=True,
        routed=True,
    )
    
    router.add_switch(switch)
    assert len(router.switch_ports) == 1
    assert router.switch_ports["ls1"] == ("192.168.1.1/24", "e1:cc:ff:01:01:00")
    
    # Add a non-routed switch to the router
    switch = LogicalSwitch(
        vpc_name="vlab",
        name="ls2",
        switch_id=2,
        switch_type=SwitchType.P2P,
        subnet="192.168.2.0/31",
        dhcp_enable=False,
        routed=False,
    )
    
    router.add_switch(switch)
    assert len(router.switch_ports) == 1  # Still 1, since ls2 is not routed


def test_topology_build():
    """Test Topology class."""
    # Create a minimal config
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
                "port_count": 2
            },
            {
                "name": "ls2",
                "id": 2,
                "type": "p2p",
                "subnet": "192.168.2.0/31",
                "dhcp_enable": False,
                "routed": False
            }
        ]
    }
    
    config = LabConfig(**config_data)
    topology = Topology(config)
    
    # Verify VPC properties
    assert topology.vpc_name == "vlab"
    assert topology.mac_prefix == "e1:cc:ff"
    assert topology.vpc_id == 1
    
    # Verify switches
    assert len(topology.switches) == 2
    assert "ls1" in topology.switches
    assert "ls2" in topology.switches
    
    # Verify ls1 details
    ls1 = topology.switches["ls1"]
    assert ls1.full_name == "vlab-ls1"
    assert ls1.type == SwitchType.NORMAL
    assert ls1.dhcp_enable is True
    assert ls1.routed is True
    assert len(ls1.ports) == 2
    
    # Verify ls2 details
    ls2 = topology.switches["ls2"]
    assert ls2.full_name == "vlab-ls2"
    assert ls2.type == SwitchType.P2P
    assert ls2.dhcp_enable is False
    assert ls2.routed is False
    assert len(ls2.ports) == 2  # Uses vpc.port_count
    
    # Verify router
    assert topology.router is not None
    assert topology.router.full_name == "vlab-lr"
    assert len(topology.router.switch_ports) == 1  # Only ls1 is routed
    assert "ls1" in topology.router.switch_ports


def test_topology_with_explicit_ports():
    """Test Topology class with explicit port definitions."""
    # Create a config with explicit ports
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
                "dhcp_enable": True,
                "routed": True,
                "ports": [
                    {"name": "lsp1", "addressing": "dynamic"},
                    {"name": "lsp2", "addressing": "static", "ip": "192.168.1.10"}
                ]
            }
        ]
    }
    
    config = LabConfig(**config_data)
    topology = Topology(config)
    
    # Verify ls1 ports
    ls1 = topology.switches["ls1"]
    assert len(ls1.ports) == 2
    
    # Verify first port
    port1 = ls1.ports[0]
    assert port1.port_name == "lsp1"
    assert port1.addressing == AddressingMode.DYNAMIC
    assert port1.ip is None
    
    # Verify second port
    port2 = ls1.ports[1]
    assert port2.port_name == "lsp2"
    assert port2.addressing == AddressingMode.STATIC
    assert port2.ip == "192.168.1.10"


def test_topology_port_limit():
    """Test Topology port creation with subnet size constraints."""
    # Create a config with port_count exceeding subnet size
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
                "type": "p2p",
                "subnet": "192.168.1.0/31",  # Only 2 IPs available
                "port_count": 5  # Asking for more ports than subnet can accommodate
            }
        ]
    }
    
    config = LabConfig(**config_data)
    topology = Topology(config)
    
    # Verify ls1 ports are limited by subnet size
    ls1 = topology.switches["ls1"]
    assert len(ls1.ports) == 2  # Only 2 IPs available in a /31 subnet