"""
Unit tests for the ovn_builder module.
"""

import pytest
from unittest.mock import MagicMock, patch

from ovn_lab_builder.schema import AddressingMode, LabConfig, SwitchType
from ovn_lab_builder.topology import LogicalRouter, LogicalSwitch, LogicalSwitchPort, Topology
from ovn_lab_builder.ovn_builder import OvnBuilder


@pytest.fixture
def mock_nb_api():
    """Create a mock for the northbound API."""
    mock = MagicMock()
    
    # Setup common transaction operations
    txn = MagicMock()
    mock.transaction.return_value = txn
    txn.add.return_value = "uuid"
    txn.commit.return_value = None
    
    return mock


@pytest.fixture
def mock_sb_api():
    """Create a mock for the southbound API."""
    return MagicMock()


@pytest.fixture
def mock_topology():
    """Create a mock topology with switches and a router."""
    # Create VPC and topology
    topology = MagicMock(spec=Topology)
    topology.vpc_name = "vlab"
    topology.mac_prefix = "e1:cc:ff"
    topology.vpc_id = 1
    
    # Create logical switch
    ls1 = MagicMock(spec=LogicalSwitch)
    ls1.vpc_name = "vlab"
    ls1.name = "ls1"
    ls1.full_name = "vlab-ls1"
    ls1.id = 1
    ls1.type = SwitchType.NORMAL
    ls1.subnet_str = "192.168.1.0/24"
    ls1.dhcp_enable = True
    ls1.routed = True
    ls1.dhcp_options = {
        "server_id": "192.168.1.1",
        "server_mac": "e1:cc:ff:01:01:00",
        "router": "192.168.1.1",
        "dns_server": "8.8.8.8",
        "lease_time": "3600",
    }
    ls1.router_port_ip = "192.168.1.1/24"
    ls1.router_port_mac = "e1:cc:ff:01:01:00"
    
    # Create port for the switch
    port1 = MagicMock(spec=LogicalSwitchPort)
    port1.vpc_name = "vlab"
    port1.switch_name = "ls1"
    port1.port_name = "lsp1"
    port1.full_name = "vlab-ls1-lsp1"
    port1.vpc_id = 1
    port1.switch_id = 1
    port1.port_index = 1
    port1.mac_prefix = "e1:cc:ff"
    port1.mac = "e1:cc:ff:01:01:01"
    port1.addressing = AddressingMode.DYNAMIC
    port1.port_security = ["e1:cc:ff:01:01:01"]
    
    ls1.ports = [port1]
    
    # Create logical router
    router = MagicMock(spec=LogicalRouter)
    router.vpc_name = "vlab"
    router.full_name = "vlab-lr"
    router.switch_ports = {"ls1": ("192.168.1.1/24", "e1:cc:ff:01:01:00")}
    
    # Assign to topology
    topology.switches = {"ls1": ls1}
    topology.router = router
    
    return topology


@patch("ovn_lab_builder.ovn_builder.Connection")
@patch("ovn_lab_builder.ovn_builder.northbound_impl")
@patch("ovn_lab_builder.ovn_builder.southbound_impl")
def test_ovn_builder_init(mock_sb_impl, mock_nb_impl, mock_connection):
    """Test OvnBuilder initialization."""
    # Setup mocks
    mock_nb_conn = MagicMock()
    mock_sb_conn = MagicMock()
    mock_connection.side_effect = [mock_nb_conn, mock_sb_conn]
    
    mock_nb_api = MagicMock()
    mock_sb_api = MagicMock()
    mock_nb_impl.OvnNbApiIdlImpl.return_value = mock_nb_api
    mock_sb_impl.OvnSbApiIdlImpl.return_value = mock_sb_api
    
    # Create the builder
    builder = OvnBuilder(
        nb_connection_string="tcp:1.2.3.4:6641",
        sb_connection_string="tcp:1.2.3.4:6642",
    )
    
    # Verify the builder was initialized correctly
    assert builder.nb_conn == mock_nb_conn
    assert builder.sb_conn == mock_sb_conn
    assert builder.nb_api == mock_nb_api
    assert builder.sb_api == mock_sb_api
    
    # Verify connection was created with the correct parameters
    mock_connection.assert_any_call("tcp:1.2.3.4:6641", timeout=60)
    mock_connection.assert_any_call("tcp:1.2.3.4:6642", timeout=60)


def test_build_topology(mock_nb_api, mock_sb_api, mock_topology):
    """Test building a topology."""
    # Setup the builder with mocks
    builder = OvnBuilder(
        nb_connection_string="tcp:1.2.3.4:6641",
        sb_connection_string="tcp:1.2.3.4:6642",
    )
    builder.nb_api = mock_nb_api
    builder.sb_api = mock_sb_api
    
    # Setup return values for API calls
    mock_nb_api.lr_get.return_value.execute.return_value = None
    mock_nb_api.ls_get.return_value.execute.return_value = None
    mock_nb_api.lsp_get.return_value.execute.return_value = None
    mock_nb_api.lrp_get.return_value.execute.return_value = None
    
    # Build the topology
    builder.build(mock_topology)
    
    # Verify router creation
    mock_nb_api.lr_get.assert_called_with("vlab-lr")
    mock_nb_api.lr_add.assert_called_with(
        "vlab-lr",
        external_ids={"ovn-lab-builder": "true"},
        options={
            "always_learn_from_arp_request": "false",
            "dynamic_neigh_routers": "true"
        }
    )
    
    # Verify switch creation
    mock_nb_api.ls_get.assert_called_with("vlab-ls1")
    mock_nb_api.ls_add.assert_called_with(
        "vlab-ls1",
        external_ids={
            "ovn-lab-builder": "true",
            "switch-type": "normal"
        },
        other_config={"subnet": "192.168.1.0/24"}
    )
    
    # Verify DHCP options creation
    mock_nb_api.dhcp_options_add.assert_called_with(
        cidr="192.168.1.0/24",
        options={
            "server_id": "192.168.1.1",
            "server_mac": "e1:cc:ff:01:01:00",
            "router": "192.168.1.1",
            "dns_server": "8.8.8.8",
            "lease_time": "3600",
        },
        external_ids={"ovn-lab-builder": "true"}
    )
    
    # Verify port creation
    mock_nb_api.lsp_get.assert_called_with("vlab-ls1-lsp1")
    mock_nb_api.lsp_add.assert_called_with(
        "vlab-ls1",
        "vlab-ls1-lsp1",
        external_ids={"ovn-lab-builder": "true"}
    )
    
    # Verify port addressing
    mock_nb_api.lsp_set_addresses.assert_called_with(
        "vlab-ls1-lsp1",
        ["e1:cc:ff:01:01:01 dynamic"]
    )
    
    # Verify router connection
    mock_nb_api.lrp_get.assert_called_with("vlab-lr-ls1")
    mock_nb_api.lrp_add.assert_called_with(
        "vlab-lr",
        "vlab-lr-ls1",
        "e1:cc:ff:01:01:00",
        ["192.168.1.1/24"],
        external_ids={"ovn-lab-builder": "true"}
    )


def test_destroy_topology(mock_nb_api, mock_sb_api, mock_topology):
    """Test destroying a topology."""
    # Setup the builder with mocks
    builder = OvnBuilder(
        nb_connection_string="tcp:1.2.3.4:6641",
        sb_connection_string="tcp:1.2.3.4:6642",
    )
    builder.nb_api = mock_nb_api
    builder.sb_api = mock_sb_api
    
    # Setup return values for API calls
    mock_nb_api.lr_get.return_value.execute.return_value = {"_uuid": "uuid-lr"}
    mock_nb_api.ls_get.return_value.execute.return_value = {"_uuid": "uuid-ls"}
    mock_nb_api.lsp_get.return_value.execute.return_value = {"_uuid": "uuid-lsp"}
    mock_nb_api.lrp_get.return_value.execute.return_value = {"_uuid": "uuid-lrp"}
    
    # Mock DHCP options
    dhcp_options = [MagicMock()]
    dhcp_options[0].cidr = "192.168.1.0/24"
    dhcp_options[0].uuid = "uuid-dhcp"
    mock_nb_api.dhcp_options_list.return_value.execute.return_value = dhcp_options
    
    # Destroy the topology
    builder.destroy(mock_topology)
    
    # Verify router port deletion
    mock_nb_api.lrp_get.assert_called_with("vlab-lr-ls1")
    mock_nb_api.lrp_del.assert_called_with("vlab-lr-ls1")
    
    # Verify switch port deletion
    mock_nb_api.lsp_get.assert_called_with("vlab-ls1-lsp1")
    mock_nb_api.lsp_del.assert_called_with("vlab-ls1-lsp1")
    
    # Verify DHCP options deletion
    mock_nb_api.dhcp_options_list.assert_called_once()
    mock_nb_api.dhcp_options_del.assert_called_with("uuid-dhcp")
    
    # Verify switch deletion
    mock_nb_api.ls_get.assert_called_with("vlab-ls1")
    mock_nb_api.ls_del.assert_called_with("vlab-ls1")
    
    # Verify router deletion
    mock_nb_api.lr_get.assert_called_with("vlab-lr")
    mock_nb_api.lr_del.assert_called_with("vlab-lr")