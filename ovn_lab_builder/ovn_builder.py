"""
OVN Builder module for OVN Virtual Lab Builder.

This module contains the adapter that interacts with OVN using ovsdbapp.
It provides methods to create and destroy OVN objects based on topology.
"""

import ipaddress
import logging
from typing import Dict, List, Optional, Set, Tuple

from ovsdbapp.backend.ovs_idl import Connection
from ovsdbapp.schema.ovn_northbound import impl_idl as northbound_impl
from ovsdbapp.schema.ovn_southbound import impl_idl as southbound_impl

from .topology import LogicalRouter, LogicalSwitch, LogicalSwitchPort, Topology

logger = logging.getLogger(__name__)


class OvnBuilder:
    """Adapter for interacting with OVN databases using ovsdbapp."""

    def __init__(self, nb_connection_string: str, sb_connection_string: str):
        """Initialize the OVN builder with connection strings.
        
        Args:
            nb_connection_string: Connection string for the OVN Northbound database
            sb_connection_string: Connection string for the OVN Southbound database
        """
        # Initialize connections to OVN databases
        self.nb_conn = Connection(nb_connection_string, timeout=60)
        self.sb_conn = Connection(sb_connection_string, timeout=60)
        
        # Create API instances
        self.nb_api = northbound_impl.OvnNbApiIdlImpl(self.nb_conn)
        self.sb_api = southbound_impl.OvnSbApiIdlImpl(self.sb_conn)

    def build(self, topology: Topology) -> None:
        """Build an OVN topology based on the specified configuration.
        
        This method is idempotent - it can be called multiple times with
        the same topology without causing errors.
        
        Args:
            topology: The desired topology to create
        """
        logger.info(f"Building topology: {topology}")
        
        # Create logical router if needed
        if topology.router:
            self._create_logical_router(topology.router)
        
        # Create switches and their components
        for switch in topology.switches.values():
            self._create_logical_switch(switch)
            
            # Create DHCP options if enabled
            if switch.dhcp_enable and switch.dhcp_options:
                self._create_dhcp_options(switch)
            
            # Create switch ports
            for port in switch.ports:
                self._create_logical_switch_port(switch, port)
            
            # Connect to router if needed
            if switch.routed and topology.router:
                self._connect_switch_to_router(switch, topology.router)
        
        logger.info(f"Topology {topology.vpc_name} built successfully")

    def destroy(self, topology: Topology) -> None:
        """Destroy an OVN topology.
        
        This method is idempotent - it can be called multiple times
        without causing errors if components are already removed.
        
        Args:
            topology: The topology to destroy
        """
        logger.info(f"Destroying topology: {topology}")
        
        # Remove router and router ports first
        for switch in topology.switches.values():
            if switch.routed and topology.router:
                self._disconnect_switch_from_router(switch, topology.router)
        
        if topology.router:
            self._delete_logical_router(topology.router)
        
        # Remove DHCP options and ports
        for switch in topology.switches.values():
            # Remove ports first
            for port in switch.ports:
                self._delete_logical_switch_port(port)
            
            # Remove DHCP options
            if switch.dhcp_enable:
                self._delete_dhcp_options(switch)
            
            # Remove the switch
            self._delete_logical_switch(switch)
        
        logger.info(f"Topology {topology.vpc_name} destroyed successfully")

    def _create_logical_router(self, router: LogicalRouter) -> None:
        """Create a logical router if it doesn't exist.
        
        Args:
            router: The logical router to create
        """
        name = router.full_name
        
        # Check if the router already exists
        existing = self.nb_api.lr_get(name).execute(check_error=False)
        if existing:
            logger.debug(f"Logical router {name} already exists")
            return
        
        # Create the router
        txn = self.nb_api.transaction()
        
        txn.add(
            self.nb_api.lr_add(
                name,
                external_ids={"ovn-lab-builder": "true"},
                options={
                    "always_learn_from_arp_request": "false",
                    "dynamic_neigh_routers": "true"
                }
            )
        )
        
        txn.commit()
        logger.info(f"Created logical router: {name}")

    def _create_logical_switch(self, switch: LogicalSwitch) -> None:
        """Create a logical switch if it doesn't exist.
        
        Args:
            switch: The logical switch to create
        """
        name = switch.full_name
        
        # Check if the switch already exists
        existing = self.nb_api.ls_get(name).execute(check_error=False)
        if existing:
            logger.debug(f"Logical switch {name} already exists")
            return
        
        # Create the switch
        txn = self.nb_api.transaction()
        
        txn.add(
            self.nb_api.ls_add(
                name,
                external_ids={
                    "ovn-lab-builder": "true",
                    "switch-type": switch.type.value
                },
                other_config={"subnet": switch.subnet_str}
            )
        )
        
        txn.commit()
        logger.info(f"Created logical switch: {name}")

    def _create_dhcp_options(self, switch: LogicalSwitch) -> None:
        """Create DHCP options for a logical switch.
        
        Args:
            switch: The logical switch to create DHCP options for
        """
        if not switch.dhcp_options:
            logger.warning(f"No DHCP options available for switch {switch.full_name}")
            return
        
        # Create DHCP options
        txn = self.nb_api.transaction()
        
        # Create the DHCP options
        cidr = str(switch.subnet)
        dhcp_uuid = txn.add(
            self.nb_api.dhcp_options_add(
                cidr=cidr,
                options=switch.dhcp_options,
                external_ids={"ovn-lab-builder": "true"}
            )
        )
        
        # Associate DHCP options with the switch
        txn.add(
            self.nb_api.ls_set_dhcpv4_options(
                switch.full_name,
                dhcp_uuid
            )
        )
        
        # Set excluded IPs if needed
        if switch.subnet.prefixlen < 31:  # Not needed for /31 subnets
            hosts = list(switch.subnet.hosts())
            if len(hosts) >= 4:
                # Exclude the first 4 IPs
                exclude_ips = [str(hosts[i]) for i in range(4)]
                txn.add(
                    self.nb_api.ls_set_other_config(
                        switch.full_name,
                        {"exclude_ips": ",".join(exclude_ips)}
                    )
                )
        
        txn.commit()
        logger.info(f"Created DHCP options for switch: {switch.full_name}")

    def _create_logical_switch_port(self, switch: LogicalSwitch, port: LogicalSwitchPort) -> None:
        """Create a logical switch port if it doesn't exist.
        
        Args:
            switch: The logical switch that the port belongs to
            port: The logical switch port to create
        """
        name = port.full_name
        
        # Check if the port already exists
        existing = self.nb_api.lsp_get(name).execute(check_error=False)
        if existing:
            logger.debug(f"Logical switch port {name} already exists")
            return
        
        # Create the port
        txn = self.nb_api.transaction()
        
        # Add the port to the switch
        txn.add(
            self.nb_api.lsp_add(
                switch.full_name,
                name,
                external_ids={"ovn-lab-builder": "true"}
            )
        )
        
        # Set port addressing
        if port.addressing == "dynamic":
            txn.add(
                self.nb_api.lsp_set_addresses(
                    name,
                    [f"{port.mac} dynamic"]
                )
            )
        elif port.addressing == "static" and port.ip:
            txn.add(
                self.nb_api.lsp_set_addresses(
                    name,
                    [f"{port.mac} {port.ip}"]
                )
            )
        else:  # unknown
            txn.add(
                self.nb_api.lsp_set_addresses(
                    name,
                    ["unknown"]
                )
            )
        
        # Set port security
        txn.add(
            self.nb_api.lsp_set_port_security(
                name,
                port.port_security
            )
        )
        
        txn.commit()
        logger.info(f"Created logical switch port: {name}")

    def _connect_switch_to_router(self, switch: LogicalSwitch, router: LogicalRouter) -> None:
        """Connect a logical switch to a logical router.
        
        Args:
            switch: The logical switch to connect
            router: The logical router to connect to
        """
        router_port_name = f"{router.full_name}-{switch.name}"
        switch_port_name = f"{switch.full_name}-{router.full_name}"
        
        router_ip = switch.router_port_ip
        router_mac = switch.router_port_mac
        
        if not router_ip or not router_mac:
            logger.warning(f"Cannot connect switch {switch.full_name} to router: missing IP or MAC")
            return
        
        # Check if the ports already exist
        existing_router_port = self.nb_api.lrp_get(router_port_name).execute(check_error=False)
        existing_switch_port = self.nb_api.lsp_get(switch_port_name).execute(check_error=False)
        
        if existing_router_port and existing_switch_port:
            logger.debug(f"Switch {switch.full_name} already connected to router {router.full_name}")
            return
        
        # Create the ports
        txn = self.nb_api.transaction()
        
        # Create router port
        if not existing_router_port:
            txn.add(
                self.nb_api.lrp_add(
                    router.full_name,
                    router_port_name,
                    router_mac,
                    [router_ip],
                    external_ids={"ovn-lab-builder": "true"}
                )
            )
        
        # Create switch port
        if not existing_switch_port:
            txn.add(
                self.nb_api.lsp_add(
                    switch.full_name,
                    switch_port_name,
                    external_ids={"ovn-lab-builder": "true"}
                )
            )
            
            txn.add(
                self.nb_api.lsp_set_type(
                    switch_port_name,
                    "router"
                )
            )
            
            txn.add(
                self.nb_api.lsp_set_options(
                    switch_port_name,
                    {"router-port": router_port_name}
                )
            )
            
            txn.add(
                self.nb_api.lsp_set_addresses(
                    switch_port_name,
                    ["router"]
                )
            )
        
        txn.commit()
        logger.info(f"Connected switch {switch.full_name} to router {router.full_name}")

    def _delete_logical_router(self, router: LogicalRouter) -> None:
        """Delete a logical router if it exists.
        
        Args:
            router: The logical router to delete
        """
        name = router.full_name
        
        # Check if the router exists
        existing = self.nb_api.lr_get(name).execute(check_error=False)
        if not existing:
            logger.debug(f"Logical router {name} does not exist")
            return
        
        # Delete the router
        txn = self.nb_api.transaction()
        txn.add(self.nb_api.lr_del(name))
        txn.commit()
        logger.info(f"Deleted logical router: {name}")

    def _delete_logical_switch(self, switch: LogicalSwitch) -> None:
        """Delete a logical switch if it exists.
        
        Args:
            switch: The logical switch to delete
        """
        name = switch.full_name
        
        # Check if the switch exists
        existing = self.nb_api.ls_get(name).execute(check_error=False)
        if not existing:
            logger.debug(f"Logical switch {name} does not exist")
            return
        
        # Delete the switch
        txn = self.nb_api.transaction()
        txn.add(self.nb_api.ls_del(name))
        txn.commit()
        logger.info(f"Deleted logical switch: {name}")

    def _delete_dhcp_options(self, switch: LogicalSwitch) -> None:
        """Delete DHCP options for a logical switch.
        
        Args:
            switch: The logical switch to delete DHCP options for
        """
        # Find DHCP options for this switch's subnet
        cidr = str(switch.subnet)
        dhcp_options = self.nb_api.dhcp_options_list().execute(check_error=False)
        
        dhcp_uuid = None
        for opt in dhcp_options:
            if opt.cidr == cidr:
                dhcp_uuid = opt.uuid
                break
        
        if not dhcp_uuid:
            logger.debug(f"No DHCP options found for switch {switch.full_name}")
            return
        
        # Delete the DHCP options
        txn = self.nb_api.transaction()
        txn.add(self.nb_api.dhcp_options_del(dhcp_uuid))
        txn.commit()
        logger.info(f"Deleted DHCP options for switch: {switch.full_name}")

    def _delete_logical_switch_port(self, port: LogicalSwitchPort) -> None:
        """Delete a logical switch port if it exists.
        
        Args:
            port: The logical switch port to delete
        """
        name = port.full_name
        
        # Check if the port exists
        existing = self.nb_api.lsp_get(name).execute(check_error=False)
        if not existing:
            logger.debug(f"Logical switch port {name} does not exist")
            return
        
        # Delete the port
        txn = self.nb_api.transaction()
        txn.add(self.nb_api.lsp_del(name))
        txn.commit()
        logger.info(f"Deleted logical switch port: {name}")

    def _disconnect_switch_from_router(self, switch: LogicalSwitch, router: LogicalRouter) -> None:
        """Disconnect a logical switch from a logical router.
        
        Args:
            switch: The logical switch to disconnect
            router: The logical router to disconnect from
        """
        router_port_name = f"{router.full_name}-{switch.name}"
        switch_port_name = f"{switch.full_name}-{router.full_name}"
        
        # Check if the ports exist
        existing_router_port = self.nb_api.lrp_get(router_port_name).execute(check_error=False)
        existing_switch_port = self.nb_api.lsp_get(switch_port_name).execute(check_error=False)
        
        # Delete the ports
        txn = self.nb_api.transaction()
        
        if existing_router_port:
            txn.add(self.nb_api.lrp_del(router_port_name))
        
        if existing_switch_port:
            txn.add(self.nb_api.lsp_del(switch_port_name))
        
        txn.commit()
        logger.info(f"Disconnected switch {switch.full_name} from router {router.full_name}")