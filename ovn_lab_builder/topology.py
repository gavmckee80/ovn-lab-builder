"""
Topology module for OVN Virtual Lab Builder.

This module contains the core business logic for creating topology objects
from validated configuration data. It implements naming conventions,
IP address allocation, and MAC address generation according to the specification.
"""

import ipaddress
import logging
from typing import Dict, List, Optional, Set, Tuple

from .schema import AddressingMode, LabConfig, Port, Switch, SwitchType

logger = logging.getLogger(__name__)


class LogicalSwitchPort:
    """Representation of an OVN logical switch port."""

    def __init__(
        self,
        vpc_name: str,
        switch_name: str,
        port_name: str,
        vpc_id: int,
        switch_id: int,
        port_index: int,
        mac_prefix: str,
        addressing: AddressingMode,
        ip: Optional[str] = None,
        subnet: Optional[ipaddress.IPv4Network] = None,
    ):
        self.vpc_name = vpc_name
        self.switch_name = switch_name
        self.port_name = port_name
        self.vpc_id = vpc_id
        self.switch_id = switch_id
        self.port_index = port_index
        self.mac_prefix = mac_prefix
        self.addressing = addressing
        self.ip = ip
        self.subnet = subnet

    @property
    def full_name(self) -> str:
        """Get the full OVN name for this port."""
        return f"{self.vpc_name}-{self.switch_name}-{self.port_name}"

    @property
    def mac(self) -> str:
        """Generate the MAC address for this port."""
        # Format: <mac_prefix>:<vpc_id>:<switch_id>:<port_index>
        return f"{self.mac_prefix}:{self.vpc_id:02x}:{self.switch_id:02x}:{self.port_index:02x}"

    @property
    def port_security(self) -> List[str]:
        """Get the port security configuration."""
        if self.addressing == AddressingMode.STATIC and self.ip:
            return [f"{self.mac} {self.ip}"]
        return [self.mac]

    def __str__(self) -> str:
        return f"LogicalSwitchPort(name={self.full_name}, mac={self.mac}, addressing={self.addressing})"


class LogicalSwitch:
    """Representation of an OVN logical switch."""

    def __init__(
        self,
        vpc_name: str,
        name: str,
        switch_id: int,
        switch_type: SwitchType,
        subnet: str,
        dhcp_enable: bool = False,
        routed: bool = False,
    ):
        self.vpc_name = vpc_name
        self.name = name
        self.id = switch_id
        self.type = switch_type
        self.subnet_str = subnet
        self.subnet = ipaddress.IPv4Network(subnet)
        self.dhcp_enable = dhcp_enable
        self.routed = routed
        self.ports: List[LogicalSwitchPort] = []
        self.dhcp_options: Optional[Dict[str, str]] = None

    @property
    def full_name(self) -> str:
        """Get the full OVN name for this switch."""
        return f"{self.vpc_name}-{self.name}"

    @property
    def router_port_ip(self) -> Optional[str]:
        """Get the IP address for the router port connected to this switch."""
        if not self.routed:
            return None
        
        # Use the first usable IP for the router port
        hosts = list(self.subnet.hosts())
        if not hosts:
            # Special case for /31 networks (RFC 3021)
            if self.subnet.prefixlen == 31:
                return str(self.subnet.network_address)
            return None
        
        return f"{hosts[0]}/{self.subnet.prefixlen}"

    @property
    def router_port_mac(self) -> Optional[str]:
        """Get the MAC address for the router port."""
        if not self.routed or not self.dhcp_enable:
            return None
        
        # For router ports, use port_index 0 by convention
        return f"{self.dhcp_server_mac}"

    @property
    def dhcp_server_mac(self) -> str:
        """Generate the MAC address for the DHCP server."""
        # By convention, DHCP server uses port_index 0
        return f"{self.vpc_mac_prefix}:{self.vpc_id:02x}:{self.id:02x}:00"

    @property
    def usable_ips(self) -> List[ipaddress.IPv4Address]:
        """Get the list of usable IP addresses for this subnet."""
        # For P2P links with /31 subnet, both addresses are usable (RFC 3021)
        if self.subnet.prefixlen == 31:
            return list(self.subnet)
        
        # For regular subnets, skip network address and broadcast
        hosts = list(self.subnet.hosts())
        
        # If DHCP is enabled, reserve first 4 IPs
        if self.dhcp_enable and len(hosts) > 4:
            # Reserve first 4 addresses for DHCP infrastructure
            return hosts[4:]
        
        return hosts

    def add_port(self, port: LogicalSwitchPort) -> None:
        """Add a port to this switch."""
        self.ports.append(port)

    def __str__(self) -> str:
        return (
            f"LogicalSwitch(name={self.full_name}, subnet={self.subnet_str}, "
            f"type={self.type}, ports={len(self.ports)})"
        )


class LogicalRouter:
    """Representation of an OVN logical router."""

    def __init__(self, vpc_name: str):
        self.vpc_name = vpc_name
        self.switch_ports: Dict[str, Tuple[str, str]] = {}  # switch_name -> (ip, mac)

    @property
    def full_name(self) -> str:
        """Get the full OVN name for this router."""
        return f"{self.vpc_name}-lr"

    def add_switch(self, switch: LogicalSwitch) -> None:
        """Connect a switch to this router."""
        if not switch.routed:
            return
        
        router_ip = switch.router_port_ip
        router_mac = switch.router_port_mac
        
        if router_ip and router_mac:
            self.switch_ports[switch.name] = (router_ip, router_mac)

    def __str__(self) -> str:
        return f"LogicalRouter(name={self.full_name}, connected_switches={len(self.switch_ports)})"


class Topology:
    """Represents a complete OVN topology derived from a validated config."""

    def __init__(self, config: LabConfig):
        self.config = config
        self.vpc_name = config.vpc.name
        self.mac_prefix = config.vpc.mac_prefix
        self.vpc_id = config.vpc.id
        
        self.switches: Dict[str, LogicalSwitch] = {}
        self.router: Optional[LogicalRouter] = None
        
        self._build_topology()

    def _build_topology(self) -> None:
        """Build the complete topology from the configuration."""
        # Create switches
        for switch_config in self.config.switches:
            switch = LogicalSwitch(
                vpc_name=self.vpc_name,
                name=switch_config.name,
                switch_id=switch_config.id,
                switch_type=switch_config.type,
                subnet=switch_config.subnet,
                dhcp_enable=switch_config.dhcp_enable,
                routed=switch_config.routed,
            )
            
            # Add the switch's ports
            self._add_ports_to_switch(switch, switch_config)
            
            # Set DHCP options if enabled
            if switch.dhcp_enable:
                self._setup_dhcp_options(switch)
            
            self.switches[switch.name] = switch
        
        # Create router if needed
        if any(s.routed for s in self.switches.values()):
            self.router = LogicalRouter(self.vpc_name)
            for switch in self.switches.values():
                if switch.routed:
                    self.router.add_switch(switch)

    def _add_ports_to_switch(self, switch: LogicalSwitch, switch_config: Switch) -> None:
        """Add ports to a switch based on configuration."""
        # Use explicit port definitions if provided
        if switch_config.ports:
            for idx, port_config in enumerate(switch_config.ports):
                port = LogicalSwitchPort(
                    vpc_name=self.vpc_name,
                    switch_name=switch.name,
                    port_name=port_config.name,
                    vpc_id=self.vpc_id,
                    switch_id=switch.id,
                    port_index=idx + 1,  # Start from 1 as 0 is reserved for router/DHCP
                    mac_prefix=self.mac_prefix,
                    addressing=port_config.addressing,
                    ip=port_config.ip,
                    subnet=switch.subnet,
                )
                switch.add_port(port)
        else:
            # Autogenerate ports based on port_count
            port_count = switch_config.port_count or self.config.vpc.port_count
            if port_count is None:
                logger.warning(f"No port_count specified for switch {switch.full_name}, skipping port creation")
                return
            
            # Calculate how many ports we can actually create based on available IPs
            usable_ips = switch.usable_ips
            actual_port_count = min(port_count, len(usable_ips))
            
            if actual_port_count != port_count:
                logger.warning(
                    f"Switch {switch.full_name} can only accommodate {actual_port_count} ports "
                    f"instead of requested {port_count} due to subnet size constraints"
                )
            
            for idx in range(actual_port_count):
                port = LogicalSwitchPort(
                    vpc_name=self.vpc_name,
                    switch_name=switch.name,
                    port_name=f"lsp{idx + 1}",
                    vpc_id=self.vpc_id,
                    switch_id=switch.id,
                    port_index=idx + 1,  # Start from 1 as 0 is reserved
                    mac_prefix=self.mac_prefix,
                    addressing=AddressingMode.DYNAMIC if switch.dhcp_enable else AddressingMode.UNKNOWN,
                    subnet=switch.subnet,
                )
                switch.add_port(port)

    def _setup_dhcp_options(self, switch: LogicalSwitch) -> None:
        """Set up DHCP options for a switch."""
        # Only set up DHCP options if DHCP is enabled
        if not switch.dhcp_enable:
            return
        
        # Get the first usable IP for the router/DHCP server
        hosts = list(switch.subnet.hosts())
        if not hosts:
            logger.warning(f"Cannot set up DHCP for switch {switch.full_name}: subnet too small")
            return
        
        server_ip = str(hosts[0])
        dns_server = "8.8.8.8"  # Default DNS server
        
        switch.dhcp_options = {
            "server_id": server_ip,
            "server_mac": switch.dhcp_server_mac,
            "router": server_ip,
            "dns_server": dns_server,
            "lease_time": "3600",  # 1 hour
        }

    def __str__(self) -> str:
        router_info = f", router={self.router}" if self.router else ""
        return f"Topology(vpc={self.vpc_name}, switches={len(self.switches)}{router_info})"