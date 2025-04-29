"""
Utility functions for OVN Virtual Lab Builder.

This module provides helper functions for loading and validating configuration,
as well as setting up logging.
"""

import json
import logging
import os
import sys
from typing import Any, Dict, Optional

from .schema import LabConfig


def setup_logging(level: str = "INFO", json_format: bool = False) -> None:
    """Set up logging configuration.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Whether to output logs in JSON format
    """
    log_level = getattr(logging, level.upper())
    
    if json_format:
        # JSON format for structured logging
        class JsonFormatter(logging.Formatter):
            def format(self, record):
                log_record = {
                    "timestamp": self.formatTime(record),
                    "level": record.levelname,
                    "name": record.name,
                    "message": record.getMessage(),
                }
                
                if hasattr(record, "exc_info") and record.exc_info:
                    log_record["exception"] = self.formatException(record.exc_info)
                
                return json.dumps(log_record)
        
        formatter = JsonFormatter()
    else:
        # Standard format for human readability
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Configure console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    
    # Add handlers
    root_logger.addHandler(console_handler)


def load_config(config_path: str) -> LabConfig:
    """Load and validate a configuration file.
    
    Args:
        config_path: Path to the JSON configuration file
        
    Returns:
        Validated LabConfig object
        
    Raises:
        FileNotFoundError: If the configuration file does not exist
        ValueError: If the configuration is invalid
        json.JSONDecodeError: If the configuration is not valid JSON
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with open(config_path, "r") as f:
        config_data = json.load(f)
    
    try:
        config = LabConfig(**config_data)
        return config
    except Exception as e:
        raise ValueError(f"Invalid configuration: {str(e)}")


def get_connection_strings(socket_dir: Optional[str] = None) -> Dict[str, str]:
    """Get connection strings for OVN databases.
    
    Args:
        socket_dir: Directory containing OVN sockets, or None to use default
        
    Returns:
        Dictionary with connection strings for northbound and southbound databases
    """
    if not socket_dir:
        # Use default socket locations based on operating system
        if sys.platform == "darwin":  # macOS
            socket_dir = "/opt/local/var/run/ovn"
        else:  # Linux and others
            socket_dir = "/var/run/ovn"
    
    return {
        "northbound": f"unix:{socket_dir}/ovnnb_db.sock",
        "southbound": f"unix:{socket_dir}/ovnsb_db.sock",
    }