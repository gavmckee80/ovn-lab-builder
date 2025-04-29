"""
Command-line interface for OVN Virtual Lab Builder.

This module implements the CLI using Click, with commands for building
and destroying OVN virtual lab topologies.
"""

import logging
import sys
from typing import Optional

import click

from ..ovn_builder import OvnBuilder
from ..schema import LabConfig
from ..topology import Topology
from ..utils import get_connection_strings, load_config, setup_logging

logger = logging.getLogger(__name__)


@click.group()
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], case_sensitive=False),
    default="INFO",
    help="Set the logging level",
)
@click.option(
    "--json-logs",
    is_flag=True,
    help="Output logs in JSON format",
)
@click.version_option(version="0.1.0")
def cli(log_level: str, json_logs: bool) -> None:
    """OVN Virtual Lab Builder - Create and destroy OVN virtual lab topologies."""
    # Set up logging
    setup_logging(log_level, json_logs)


@cli.command()
@click.option(
    "--config",
    "-c",
    required=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True),
    help="Path to the JSON configuration file",
)
@click.option(
    "--socket-dir",
    "-s",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, readable=True),
    help="Directory containing OVN socket files",
)
def build(config: str, socket_dir: Optional[str]) -> None:
    """Build an OVN virtual lab topology from a configuration file."""
    try:
        # Load and validate the configuration
        lab_config = load_config(config)
        
        # Create topology model
        topology = Topology(lab_config)
        
        # Get OVN connection strings
        conn_strings = get_connection_strings(socket_dir)
        
        # Create OVN builder and build the topology
        builder = OvnBuilder(
            nb_connection_string=conn_strings["northbound"],
            sb_connection_string=conn_strings["southbound"],
        )
        
        # Build the topology
        builder.build(topology)
        
        logger.info(f"Successfully built topology: {topology}")
        click.echo(f"Topology '{lab_config.vpc.name}' successfully built")
        
    except Exception as e:
        logger.error(f"Failed to build topology: {str(e)}", exc_info=True)
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--config",
    "-c",
    required=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True),
    help="Path to the JSON configuration file",
)
@click.option(
    "--socket-dir",
    "-s",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, readable=True),
    help="Directory containing OVN socket files",
)
def destroy(config: str, socket_dir: Optional[str]) -> None:
    """Destroy an OVN virtual lab topology defined in a configuration file."""
    try:
        # Load and validate the configuration
        lab_config = load_config(config)
        
        # Create topology model
        topology = Topology(lab_config)
        
        # Get OVN connection strings
        conn_strings = get_connection_strings(socket_dir)
        
        # Create OVN builder and destroy the topology
        builder = OvnBuilder(
            nb_connection_string=conn_strings["northbound"],
            sb_connection_string=conn_strings["southbound"],
        )
        
        # Destroy the topology
        builder.destroy(topology)
        
        logger.info(f"Successfully destroyed topology: {topology}")
        click.echo(f"Topology '{lab_config.vpc.name}' successfully destroyed")
        
    except Exception as e:
        logger.error(f"Failed to destroy topology: {str(e)}", exc_info=True)
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()