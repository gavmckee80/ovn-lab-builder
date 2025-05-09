# OVN Virtual Lab Builder

A modular, testable, and extensible tool to programmatically build and tear down OVN-based virtual lab topologies from external JSON configuration files.

## Features

- **Separation of Concerns**: Architecture separates intent → model → execution
- **Idempotence**: Re-running the same configuration reconciles state without errors
- **Deterministic Naming**: All names derive from config (e.g., `<vpc.name>-ls<N>`, `<vpc.name>-ls<N>-lsp<P>`)
- **Extensibility**: Support for new switch and port types via schema and model subclasses
- **Robust Validation**: Fail fast on invalid JSON, malformed CIDRs, duplicates, etc.

## Installation

```bash
# From PyPI (not available yet)
pip install ovn-lab-builder

# From source
git clone https://github.com/yourusername/ovn-lab-builder.git
cd ovn-lab-builder
pip install -e .
```

## Quick Start

1. Create a JSON configuration file:

```json
{
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
      "subnet": "192.168.10.0/24",
      "dhcp_enable": true,
      "routed": true,
      "port_count": 6
    }
  ]
}
```

2. Build the topology:

```bash
ovn-lab-builder build --config path/to/your/config.json
```

3. Destroy the topology when you're done:

```bash
ovn-lab-builder destroy --config path/to/your/config.json
```

## Configuration Schema

### Top-Level Structure

| Field | Type | Description |
|-------|------|-------------|
| vpc | object | Global VPC settings |
| switches | array | List of logical switches |

### VPC Object

| Field | Type | Description |
|-------|------|-------------|
| name | string | Prefix for all generated OVN object names |
| mac_prefix | string | First three octets of MAC addresses (e.g., e1:cc:ff) |
| id | int | Numeric VPC ID (used in MAC generation) |
| port_count | int | Default number of ports per switch (optional, overridden per-switch) |

### Switches

| Field | Type | Description / Constraints |
|-------|------|---------------------------|
| name | string | Logical switch name suffix (ls<N>) |
| id | int | Unique ID used in MAC generation |
| type | enum | One of: normal, mgmt, p2p |
| subnet | string | IPv4 subnet (e.g., /24, /31 for P2P) |
| dhcp_enable | bool | Enables DHCP on the switch (default: false) |
| routed | bool | If true, connect to VPC router (default: false) |
| port_count | int | Overrides vpc.port_count when ports are autogenerated (optional) |
| ports | array | Explicit port definitions (optional, mutually exclusive with port_count) |

### Ports

| Field | Type | Description |
|-------|------|-------------|
| name | string | Port suffix (lsp<P>) |
| addressing | enum | One of: dynamic, static, unknown |
| ip | string | Required if addressing == "static" |

## Example Configurations

### Auto-Generated Ports

```json
{
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
      "subnet": "192.168.10.0/24",
      "dhcp_enable": true,
      "routed": true,
      "port_count": 6
    },
    {
      "name": "ls2",
      "id": 2,
      "type": "p2p",
      "subnet": "192.168.1.0/31",
      "dhcp_enable": false,
      "routed": false,
      "port_count": 2
    },
    {
      "name": "mgmt",
      "id": 3,
      "type": "mgmt",
      "subnet": "192.168.0.0/24",
      "dhcp_enable": true,
      "routed": true,
      "port_count": 2
    }
  ]
}
```

### Explicit Port Definition

```json
{
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
      "subnet": "192.168.10.0/24",
      "dhcp_enable": true,
      "routed": true,
      "ports": [
        { "name": "lsp1", "addressing": "dynamic" },
        { "name": "lsp2", "addressing": "static", "ip": "192.168.10.20" }
      ]
    }
  ]
}
```

## CLI Reference

### Global Options

- `--log-level`: Set the logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`)
- `--json-logs`: Output logs in JSON format
- `--version`: Show the version and exit
- `--help`: Show help message and exit

### Build Command

```
ovn-lab-builder build --config CONFIG [--socket-dir SOCKET_DIR]
```

Options:
- `--config, -c`: Path to the JSON configuration file (required)
- `--socket-dir, -s`: Directory containing OVN socket files (optional)

### Destroy Command

```
ovn-lab-builder destroy --config CONFIG [--socket-dir SOCKET_DIR]
```

Options:
- `--config, -c`: Path to the JSON configuration file (required)
- `--socket-dir, -s`: Directory containing OVN socket files (optional)

## Development

### Setting Up Development Environment

```bash
# Clone the repository
git clone https://github.com/yourusername/ovn-lab-builder.git
cd ovn-lab-builder

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dev dependencies
pip install -e ".[dev]"
```

### Running Tests

```bash
pytest
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.