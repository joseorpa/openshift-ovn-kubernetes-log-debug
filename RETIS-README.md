# RETIS Collection Script

This script (`retis-collect-nodes.py`) reads the `env-overrides` ConfigMap from the `openshift-ovn-kubernetes` namespace, extracts worker node names, and runs RETIS collection on each node using `oc debug`.

## Purpose

The script is designed to run RETIS (eBPF-based network observability tool) collection commands on OpenShift worker nodes that were previously configured for debug logging. It automatically identifies the nodes from the existing ConfigMap and executes the RETIS collection process on each node.

## Prerequisites

1. **OpenShift CLI (`oc`)** - Must be installed and available in PATH
2. **Python 3** with required dependencies
3. **Kubeconfig** - Valid kubeconfig file with appropriate permissions
4. **Existing ConfigMap** - The `env-overrides` ConfigMap must exist in the `openshift-ovn-kubernetes` namespace (created by the main debug logging script)

## Installation

1. Install dependencies:
   ```bash
   # Using the virtual environment (recommended)
   source venv/bin/activate
   pip install -r requirements-retis.txt
   
   # Or install globally
   pip install kubernetes>=18.20.0
   ```

## Usage

### Basic Usage

```bash
# Using virtual environment (recommended)
source venv/bin/activate
python3 retis-collect-nodes.py --kubeconfig /path/to/kubeconfig

# The script will prompt for kubeconfig path if not provided
python3 retis-collect-nodes.py
```

### Advanced Options

```bash
# Custom RETIS image
python3 retis-collect-nodes.py --kubeconfig ~/.kube/config --retis-image "custom-registry/retis:latest"

# Custom working directory
python3 retis-collect-nodes.py --kubeconfig ~/.kube/config --working-directory /tmp

# Dry run (see what would be executed without running)
python3 retis-collect-nodes.py --kubeconfig ~/.kube/config --dry-run

# Run in parallel (faster but less controlled)
python3 retis-collect-nodes.py --kubeconfig ~/.kube/config --parallel

# Custom namespace
python3 retis-collect-nodes.py --kubeconfig ~/.kube/config --namespace custom-ovn-namespace
```

## Command Line Arguments

- `--kubeconfig, -k`: Path to kubeconfig file (prompts if not provided)
- `--retis-image`: RETIS container image (default: `image-registry.openshift-image-registry.svc:5000/default/retis`)
- `--working-directory`: Working directory for collection (default: `/var/tmp`)
- `--namespace, -n`: Namespace containing the ConfigMap (default: `openshift-ovn-kubernetes`)
- `--dry-run`: Show commands without executing them
- `--parallel`: Run collection on all nodes simultaneously

## What the Script Does

1. **Connects to Kubernetes** - Uses the provided kubeconfig to connect to the cluster
2. **Reads ConfigMap** - Fetches the `env-overrides` ConfigMap from the specified namespace
3. **Extracts Node Names** - Parses worker node names from the ConfigMap data (excludes `_master`)
4. **Executes RETIS Collection** - Runs the following command on each node:
   ```bash
   oc debug node/<node-name> -- chroot /host systemd-run --unit="RETIS" --working-directory=<working-dir> sh -c "export RETIS_IMAGE='<retis-image>'; ./retis_in_container.sh collect -o events.json --allow-system-changes --ovs-track --stack --probe-stack --filter-packet 'tcp port 8080 or tcp port 8081'"
   ```

## Output

The script provides detailed output including:
- Node discovery from ConfigMap
- Progress for each node
- Success/failure status for each collection
- Final summary with counts

## Error Handling

- **Missing ConfigMap**: Script exits gracefully if the `env-overrides` ConfigMap doesn't exist
- **Connection Issues**: Validates cluster connectivity before proceeding
- **Command Failures**: Reports individual node failures but continues with remaining nodes
- **Timeouts**: Each collection has a 5-minute timeout to prevent hanging

## Examples

### Typical Workflow

1. First, run the main debug logging script to create the ConfigMap:
   ```bash
   python3 openshift-ovn-kubernetes-log-debug.py --kubeconfig ~/.kube/config
   ```

2. Then run RETIS collection on the same nodes:
   ```bash
   python3 retis-collect-nodes.py --kubeconfig ~/.kube/config
   ```

### Testing Before Execution

```bash
# See what would be executed
python3 retis-collect-nodes.py --kubeconfig ~/.kube/config --dry-run
```

### Custom Configuration

```bash
# Use custom image and working directory
python3 retis-collect-nodes.py \
  --kubeconfig ~/.kube/config \
  --retis-image "quay.io/custom/retis:v1.0" \
  --working-directory "/opt/retis" \
  --parallel
```

## Notes

- The script requires the `oc` command to be available in the system PATH
- Each `oc debug` session creates a temporary pod on the target node
- The RETIS collection process may take several minutes per node
- Results are saved as `events.json` in the specified working directory on each node
- The script can be safely interrupted and rerun if needed 