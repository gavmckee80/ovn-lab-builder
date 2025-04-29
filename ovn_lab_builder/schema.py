"""
Schema definitions for OVN Virtual Lab Builder.

This module contains Pydantic models that validate the JSON configuration
and enforce constraints as specified in the requirements.
"""

from enum import Enum
from ipaddress import IPv4Network
from typing import List, Optional, Union

from pydantic import BaseModel, Field, validator, root_validator


class AddressingMode(str, Enum):
    """Valid addressing modes for logical switch ports."""
    DYNAMIC = "dynamic"
    STATIC = "static"
    UNKNOWN = "unknown"


class SwitchType(str, Enum):
    """Valid switch types."""
    NORMAL = "normal"
    MGMT = "mgmt"
    P2P = "p2p"


class Port(BaseModel):
    """Logical switch port configuration."""
    name: str
    addressing: AddressingMode
    ip: Optional[str] = None

    @validator('ip')
    def validate_ip_if_static(cls, v, values):
        """Validate that IP is provided if addressing is static."""
        if values.get('addressing') == AddressingMode.STATIC and not v:
            raise ValueError("IP address must be provided when addressing mode is 'static'")
        return v


class Switch(BaseModel):
    """Logical switch configuration."""
    name: str
    id: int
    type: SwitchType
    subnet: str
    dhcp_enable: bool = False
    routed: bool = False
    port_count: Optional[int] = None
    ports: Optional[List[Port]] = None

    @validator('subnet')
    def validate_subnet(cls, v):
        """Validate that subnet is a valid CIDR."""
        try:
            IPv4Network(v)
            return v
        except ValueError:
            raise ValueError(f"Invalid subnet: {v}")

    @root_validator
    def validate_ports_or_count(cls, values):
        """Validate that either port_count or ports is provided, not both."""
        if values.get('ports') is not None and values.get('port_count') is not None:
            raise ValueError("Cannot specify both 'ports' and 'port_count'")
        
        # Ensure at least one is provided
        if values.get('ports') is None and values.get('port_count') is None:
            vpc_port_count = values.get('vpc_port_count')
            if vpc_port_count is None:
                raise ValueError("Must specify either 'ports' or 'port_count'")
        
        return values


class VPC(BaseModel):
    """VPC configuration."""
    name: str
    mac_prefix: str
    id: int
    port_count: Optional[int] = None

    @validator('mac_prefix')
    def validate_mac_prefix(cls, v):
        """Validate MAC prefix format (e.g., e1:cc:ff)."""
        if not all(c in '0123456789abcdef:' for c in v.lower()):
            raise ValueError(f"Invalid MAC prefix: {v}")
        
        parts = v.split(':')
        if len(parts) != 3:
            raise ValueError(f"MAC prefix must have 3 octets: {v}")
        
        for part in parts:
            if len(part) != 2:
                raise ValueError(f"Each octet must be 2 hex digits: {v}")
        
        return v.lower()


class LabConfig(BaseModel):
    """Top-level configuration model."""
    vpc: VPC
    switches: List[Switch]

    @validator('switches')
    def validate_switch_ids(cls, v):
        """Validate that switch IDs are unique."""
        ids = [switch.id for switch in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Switch IDs must be unique")
        return v

    @root_validator
    def inject_vpc_port_count(cls, values):
        """Inject vpc.port_count into switches that don't have port_count or ports."""
        vpc = values.get('vpc')
        switches = values.get('switches')
        
        if vpc and switches:
            for switch in switches:
                # Set vpc_port_count for validation in Switch.validate_ports_or_count
                if not hasattr(switch, 'vpc_port_count') and vpc.port_count is not None:
                    setattr(switch, 'vpc_port_count', vpc.port_count)
        
        return values