# OpenShift OVN-Kubernetes Log Debug Setter

This Python script dynamically generates a Kubernetes `ConfigMap` to enable debug logging for OVN-Kubernetes components. It can target all nodes in a cluster or be filtered to only include nodes running specific pods, and optionally restart the pods to immediately apply the new configuration. The script also supports reverting debug logging settings by removing the ConfigMap and restarting affected pods.

## Features

- **Dynamic Node Discovery:** Automatically fetches node names from your Kubernetes cluster
- **Flexible Kubeconfig Support:** Use command-line arguments or interactive prompts for kubeconfig path
- **SSL Certificate Bypass:** Option to disable SSL verification for clusters with self-signed certificates
- **Targeted Configuration:** Filter nodes by pod name pattern to apply settings only to specific nodes
- **Automated Application:** Creates or replaces the `ConfigMap` directly in the specified namespace
- **Pod Restart Option:** Automatically restart ovnkube-node pods to immediately apply debug logging
- **Revert Functionality:** Remove debug logging configuration and restart affected pods to return to normal logging
- **Dry-Run Mode:** Preview all changes and see generated ConfigMap without making any modifications
- **Debug Output:** View generated YAML structure for troubleshooting
- **Customizable Log Levels:** Configure both OVN-Kubernetes and OVN log levels independently
- **Comprehensive CLI:** Full command-line interface with help and examples

## Requirements

- Python 3.6+
- Access to a Kubernetes/OpenShift cluster
- Valid kubeconfig file

## Installation

1. Clone or download this repository
2. Create a virtual environment (recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install the required Python libraries:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Basic Usage

```bash
# Use current oc login session (recommended for OpenShift)
python3 openshift-ovn-kubernetes-log-debug.py --use-current-context

# Specify kubeconfig path explicitly
python3 openshift-ovn-kubernetes-log-debug.py --kubeconfig /path/to/kubeconfig

# Short form
python3 openshift-ovn-kubernetes-log-debug.py -k ~/.kube/config

# Interactive mode - will prompt for kubeconfig path
python3 openshift-ovn-kubernetes-log-debug.py
```

### Advanced Usage

```bash
# Apply ConfigMap and restart pods immediately (using oc login context)
python3 openshift-ovn-kubernetes-log-debug.py --use-current-context --restart-pods

# Preview changes without applying them (dry-run)
python3 openshift-ovn-kubernetes-log-debug.py --use-current-context --dry-run

# Use oc login with SSL bypass for clusters with certificate issues
python3 openshift-ovn-kubernetes-log-debug.py --use-current-context --disable-ssl-verification

# Preview changes with pod restart (dry-run)
python3 openshift-ovn-kubernetes-log-debug.py -k /path/to/kubeconfig --dry-run --restart-pods

# Revert debug logging (remove ConfigMap only)
python3 openshift-ovn-kubernetes-log-debug.py -k /path/to/kubeconfig --revert

# Revert debug logging and restart pods to apply changes immediately
python3 openshift-ovn-kubernetes-log-debug.py -k /path/to/kubeconfig --revert --restart-pods

# Preview revert operation (dry-run)
python3 openshift-ovn-kubernetes-log-debug.py -k /path/to/kubeconfig --revert --dry-run

# Preview complete revert with pod restart (dry-run)
python3 openshift-ovn-kubernetes-log-debug.py -k /path/to/kubeconfig --revert --restart-pods --dry-run

# Include all nodes instead of filtering by pods
python3 openshift-ovn-kubernetes-log-debug.py -k /path/to/kubeconfig --all-nodes

# Use custom pod pattern
python3 openshift-ovn-kubernetes-log-debug.py -k /path/to/kubeconfig --pod-pattern "ovs-node"

# Use custom namespace
python3 openshift-ovn-kubernetes-log-debug.py -k /path/to/kubeconfig --namespace "my-ovn-namespace"

# Show debug output (generated YAML)
python3 openshift-ovn-kubernetes-log-debug.py -k /path/to/kubeconfig --debug

# Disable SSL certificate verification (for clusters with self-signed certificates)
python3 openshift-ovn-kubernetes-log-debug.py -k /path/to/kubeconfig --disable-ssl-verification

# Customize log levels
python3 openshift-ovn-kubernetes-log-debug.py -k /path/to/kubeconfig --ovn-kube-log-level 3 --ovn-log-level warn

# Target a specific list of nodes
python3 openshift-ovn-kubernetes-log-debug.py -k /path/to/kubeconfig --nodes node-a.example.com,node-b.example.com

# Maximum debug logging
python3 openshift-ovn-kubernetes-log-debug.py -k /path/to/kubeconfig --ovn-kube-log-level 10 --ovn-log-level dbg

# Minimal logging
python3 openshift-ovn-kubernetes-log-debug.py -k /path/to/kubeconfig --ovn-kube-log-level 1 --ovn-log-level err

# Complete example with all options (for applying debug config)
python3 openshift-ovn-kubernetes-log-debug.py \
  --kubeconfig /path/to/kubeconfig \
  --pod-pattern "ovnkube-node" \
  --namespace "openshift-ovn-kubernetes" \
  --ovn-kube-log-level 3 \
  --ovn-log-level warn \
  --restart-pods \
  --debug

# Example with SSL verification disabled (for clusters with certificate issues)
python3 openshift-ovn-kubernetes-log-debug.py \
  --kubeconfig /path/to/kubeconfig \
  --disable-ssl-verification \
  --restart-pods
```

## Command-Line Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--kubeconfig` | `-k` | Path to kubeconfig file (prompts if neither this nor --use-current-context provided) | None |
| `--use-current-context` | | Use default kubeconfig and current context (same as oc uses) | `False` |
| `--pod-pattern` | `-p` | Pod name pattern to filter nodes | `ovnkube-node` |
| `--all-nodes` | `-a` | Include all nodes (ignore pod filtering) | `False` |
| `--nodes` | | Comma-separated list of node names to target (overrides `--pod-pattern` and `--all-nodes`) | None |
| `--namespace` | `-n` | Target namespace for ConfigMap | `openshift-ovn-kubernetes` |
| `--restart-pods` | | Restart ovnkube-node pods after applying ConfigMap | `False` |
| `--revert` | | Revert debug logging by removing ConfigMap and restarting affected pods | `False` |
| `--dry-run` | | Show what would be done without making any changes | `False` |
| `--debug` | | Show debug output including generated YAML | `False` |
| `--ovn-kube-log-level` | | OVN Kubernetes log level (1-10) | `3` |
| `--ovn-log-level` | | OVN log level (off, emer, err, warn, info, dbg) | `warn` |
| `--disable-ssl-verification` | | Disable SSL certificate verification (WARNING: Insecure) | `False` |
| `--help` | `-h` | Show help message and exit | |

**Note:** When using `--revert`, the `--all-nodes` option is not allowed, and `--pod-pattern` is ignored (the script reads affected nodes from the existing ConfigMap). Log level options are also ignored during revert operations.

## OpenShift Authentication Integration

The script seamlessly integrates with OpenShift CLI (`oc`) authentication. When you use `oc login`, your authentication tokens are stored in the kubeconfig file, which this script can use directly.

### Using oc login Authentication

```bash
# Step 1: Login to OpenShift (if not already logged in)
oc login https://api.cluster.example.com:6443 --username=myuser

# Step 2: Use the current oc session
python3 openshift-ovn-kubernetes-log-debug.py --use-current-context --restart-pods

# Alternative: Specify kubeconfig explicitly (same result)
python3 openshift-ovn-kubernetes-log-debug.py --kubeconfig ~/.kube/config --restart-pods
```

### Authentication Verification

When using `--use-current-context`, the script will:
- ✅ Verify your current authentication status using `oc whoami`
- ✅ Display the current context and username
- ✅ Use the same bearer tokens that `oc` commands use
- ✅ Respect the current project/namespace context

### Benefits of oc Integration

- **Seamless Authentication**: No need to manage separate kubeconfig files
- **Token Management**: Automatic token refresh handled by oc
- **Context Awareness**: Uses the same cluster context as your oc commands
- **Security**: Leverages OpenShift's built-in authentication mechanisms

### Authentication Examples

```bash
# Check current oc session first
oc whoami
oc project

# Use current session with SSL bypass (for development clusters)
python3 openshift-ovn-kubernetes-log-debug.py --use-current-context --disable-ssl-verification

# Dry run with current session
python3 openshift-ovn-kubernetes-log-debug.py --use-current-context --dry-run

# Full workflow with oc session
python3 openshift-ovn-kubernetes-log-debug.py --use-current-context --restart-pods --debug
```

## Log Level Customization

The script allows you to customize both OVN-Kubernetes and OVN log levels independently:

### OVN-Kubernetes Log Level (`--ovn-kube-log-level`)
- **Range:** 1-10 (integer values)
- **Default:** 3
- **Description:** Controls the verbosity of ovn-kubernetes components
- **Usage:** Higher values provide more verbose logging

### OVN Log Level (`--ovn-log-level`)
- **Options:** off, emer, err, warn, info, dbg
- **Default:** warn
- **Description:** Controls the verbosity of OVN components (ovn-controller, northd, nbdb, sbdb)
- **Usage:** 
  - `off`: No logging
  - `emer`: Emergency messages only
  - `err`: Error messages and above
  - `warn`: Warning messages and above
  - `info`: Informational messages and above
  - `dbg`: Debug messages (most verbose)

### Log Level Examples

```bash
# Light debugging (reduce verbosity)
python3 openshift-ovn-kubernetes-log-debug.py -k /path/to/kubeconfig --ovn-kube-log-level 3 --ovn-log-level warn

# Standard debug logging (default)
python3 openshift-ovn-kubernetes-log-debug.py -k /path/to/kubeconfig --ovn-kube-log-level 3 --ovn-log-level warn

# Maximum verbosity for troubleshooting
python3 openshift-ovn-kubernetes-log-debug.py -k /path/to/kubeconfig --ovn-kube-log-level 10 --ovn-log-level dbg

# Error-level logging only
python3 openshift-ovn-kubernetes-log-debug.py -k /path/to/kubeconfig --ovn-kube-log-level 1 --ovn-log-level err

# Preview with custom log levels
python3 openshift-ovn-kubernetes-log-debug.py -k /path/to/kubeconfig --ovn-kube-log-level 7 --ovn-log-level info --dry-run
```

## What the Script Does

### Apply Debug Logging (Default Mode)
1. **Connects to Kubernetes:** Uses the specified kubeconfig to connect to your cluster
2. **Discovers Nodes:** Selects nodes by precedence:
   - If `--nodes` is provided, uses that exact list
   - Else if `--all-nodes` is provided, includes all nodes
   - Else finds nodes running pods matching the specified pattern (default: `ovnkube-node`)
3. **Generates ConfigMap:** Creates a `ConfigMap` with debug logging configuration for each node
4. **Applies Configuration:** Creates or updates the `env-overrides` ConfigMap in the target namespace
5. **Restarts Pods (Optional):** Deletes matching pods so they restart with new configuration

### Revert Debug Logging (--revert Mode)
1. **Connects to Kubernetes:** Uses the specified kubeconfig to connect to your cluster
2. **Reads Existing ConfigMap:** Finds the current `env-overrides` ConfigMap to identify affected nodes
3. **Extracts Node List:** Determines which nodes were configured for debug logging
4. **Removes ConfigMap:** Deletes the `env-overrides` ConfigMap to disable debug logging
5. **Restarts Pods (Optional):** Deletes matching pods on affected nodes so they restart with normal logging

## Dry-Run Mode

The `--dry-run` option allows you to preview exactly what changes would be made without actually applying them. This is useful for:

- **Safety:** Verify changes before applying them to production
- **Planning:** Understand the impact and scope of operations
- **Debugging:** See the exact ConfigMap structure and affected resources
- **Learning:** Understand what the script does without making changes

### What Dry-Run Shows

#### Apply Mode (`--dry-run`)
- **Complete ConfigMap YAML:** Shows the exact structure and content that would be created
- **Affected Nodes List:** Displays which nodes would be configured for debug logging
- **Pod Information:** Lists specific pods that would be restarted (if `--restart-pods` is used)
- **Clear Indicators:** All operations are prefixed with `[DRY RUN]` markers

#### Revert Mode (`--revert --dry-run`)
- **Current ConfigMap Analysis:** Reads and displays information from existing ConfigMap
- **Affected Nodes:** Shows which nodes are currently configured for debug logging
- **Pod Impact:** Lists specific pods that would be restarted during revert
- **Safe Preview:** No actual deletion or changes are made

### Dry-Run Examples

```bash
# Preview ConfigMap creation
python3 openshift-ovn-kubernetes-log-debug.py -k /path/to/kubeconfig --dry-run

# Preview with pod restart
python3 openshift-ovn-kubernetes-log-debug.py -k /path/to/kubeconfig --dry-run --restart-pods

# Preview revert operation
python3 openshift-ovn-kubernetes-log-debug.py -k /path/to/kubeconfig --revert --dry-run

# Preview complete revert workflow
python3 openshift-ovn-kubernetes-log-debug.py -k /path/to/kubeconfig --revert --restart-pods --dry-run

# Test SSL bypass with dry-run (for certificate issues)
python3 openshift-ovn-kubernetes-log-debug.py -k /path/to/kubeconfig --disable-ssl-verification --dry-run
```

## Generated ConfigMap Structure

The script generates a `ConfigMap` like this (with default log levels):

```yaml
kind: ConfigMap
apiVersion: v1
metadata:
  name: env-overrides
  namespace: openshift-ovn-kubernetes
data:
  worker-1.example.com: |
    # This sets the log level for the ovn-kubernetes node process:
    OVN_KUBE_LOG_LEVEL=3
    # You might also/instead want to enable debug logging for ovn-controller:
    OVN_LOG_LEVEL=warn
  worker-2.example.com: |
    # This sets the log level for the ovn-kubernetes node process:
    OVN_KUBE_LOG_LEVEL=3
    # You might also/instead want to enable debug logging for ovn-controller:
    OVN_LOG_LEVEL=warn
  _master: |
    # This sets the log level for the ovn-kubernetes master process as well as the ovn-dbchecker:
    OVN_KUBE_LOG_LEVEL=3
    # You might also/instead want to enable debug logging for northd, nbdb and sbdb on all masters:
    OVN_LOG_LEVEL=warn
```

With custom log levels (`--ovn-kube-log-level 3 --ovn-log-level warn`):

```yaml
kind: ConfigMap
apiVersion: v1
metadata:
  name: env-overrides
  namespace: openshift-ovn-kubernetes
data:
  worker-1.example.com: |
    # This sets the log level for the ovn-kubernetes node process:
    OVN_KUBE_LOG_LEVEL=3
    # You might also/instead want to enable debug logging for ovn-controller:
    OVN_LOG_LEVEL=warn
  worker-2.example.com: |
    # This sets the log level for the ovn-kubernetes node process:
    OVN_KUBE_LOG_LEVEL=3
    # You might also/instead want to enable debug logging for ovn-controller:
    OVN_LOG_LEVEL=warn
  _master: |
    # This sets the log level for the ovn-kubernetes master process as well as the ovn-dbchecker:
    OVN_KUBE_LOG_LEVEL=3
    # You might also/instead want to enable debug logging for northd, nbdb and sbdb on all masters:
    OVN_LOG_LEVEL=warn
```

## Examples

### Enable Debug Logging for OpenShift OVN-Kubernetes

```bash
# Standard OpenShift setup using oc login (recommended)
python3 openshift-ovn-kubernetes-log-debug.py \
  --use-current-context \
  --restart-pods

# For clusters with certificate issues
python3 openshift-ovn-kubernetes-log-debug.py \
  --use-current-context \
  --disable-ssl-verification \
  --restart-pods

# Custom log levels for more targeted debugging
python3 openshift-ovn-kubernetes-log-debug.py \
  --use-current-context \
  --ovn-kube-log-level 7 \
  --ovn-log-level info \
  --restart-pods
```

### Disable Debug Logging (Revert)

```bash
# Remove debug logging configuration using oc login context
python3 openshift-ovn-kubernetes-log-debug.py \
  --use-current-context \
  --revert \
  --restart-pods

# Alternative: Specify kubeconfig explicitly
python3 openshift-ovn-kubernetes-log-debug.py \
  --kubeconfig ~/.kube/config \
  --revert \
  --restart-pods
```

### Custom Configuration

```bash
# Custom pod pattern, namespace, and log levels
python3 openshift-ovn-kubernetes-log-debug.py \
  --kubeconfig /path/to/kubeconfig \
  --pod-pattern "my-ovn-pods" \
  --namespace "custom-networking" \
  --ovn-kube-log-level 4 \
  --ovn-log-level warn \
  --restart-pods

# Explicit node list (overrides pattern and all-nodes)
python3 openshift-ovn-kubernetes-log-debug.py \
  --kubeconfig /path/to/kubeconfig \
  --nodes node-a.example.com,node-b.example.com \
  --restart-pods
```

### Troubleshooting

```bash
# See exactly what ConfigMap will be generated with custom log levels
python3 openshift-ovn-kubernetes-log-debug.py \
  --kubeconfig /path/to/kubeconfig \
  --ovn-kube-log-level 8 \
  --ovn-log-level info \
  --debug

# Preview changes before applying (recommended)
python3 openshift-ovn-kubernetes-log-debug.py \
  --kubeconfig /path/to/kubeconfig \
  --ovn-kube-log-level 6 \
  --ovn-log-level warn \
  --dry-run

# Check current debug configuration before reverting
python3 openshift-ovn-kubernetes-log-debug.py \
  --kubeconfig /path/to/kubeconfig \
  --revert \
  --dry-run
```

### Production-Safe Workflow

```bash
# Step 1: Preview what will be applied with custom log levels
python3 openshift-ovn-kubernetes-log-debug.py \
  --kubeconfig /path/to/kubeconfig \
  --ovn-kube-log-level 4 \
  --ovn-log-level warn \
  --dry-run \
  --restart-pods

# Step 2: Apply the configuration (if preview looks good)
python3 openshift-ovn-kubernetes-log-debug.py \
  --kubeconfig /path/to/kubeconfig \
  --ovn-kube-log-level 4 \
  --ovn-log-level warn \
  --restart-pods

# Step 3: When done debugging, preview revert
python3 openshift-ovn-kubernetes-log-debug.py \
  --kubeconfig /path/to/kubeconfig \
  --revert \
  --dry-run \
  --restart-pods

# Step 4: Revert to normal logging (if preview looks good)
python3 openshift-ovn-kubernetes-log-debug.py \
  --kubeconfig /path/to/kubeconfig \
  --revert \
  --restart-pods
```

## Requirements for Kubernetes Access

Your kubeconfig must have permissions to:
- List nodes (`get`, `list` on `nodes`)
- List pods in all namespaces (`get`, `list` on `pods`)
- Create/read/update ConfigMaps in the target namespace (`get`, `create`, `update` on `configmaps`)
- Delete pods in the target namespace (only if using `--restart-pods`)

## Troubleshooting

### Permission Errors
Ensure your kubeconfig has the necessary RBAC permissions listed above.

### Connection Issues
- Verify your kubeconfig path is correct
- Check that your cluster is accessible
- Ensure the cluster context is properly set

### SSL/TLS Certificate Issues

If you encounter SSL certificate verification errors like:
```
Failed to connect to Kubernetes cluster: HTTPSConnectionPool(host='api.cluster.example.com', port=6443): Max retries exceeded with url: /api/v1/ (Caused by SSLError(SSLCertVerificationError(1, '[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1035)')))
```

**Causes:**
- Cluster uses self-signed certificates
- Certificate authority (CA) not in system trust store
- Incomplete certificate chain
- Hostname mismatch in certificate

**Solutions (in order of preference):**

1. **Get proper CA certificate** (recommended):
   ```bash
   # Extract CA cert from kubeconfig
   kubectl config view --raw -o jsonpath='{.clusters[0].cluster.certificate-authority-data}' | base64 -d > cluster-ca.crt
   # Add to system trust store (method varies by OS)
   ```

2. **Use embedded CA in kubeconfig** (recommended):
   - Ensure your kubeconfig has `certificate-authority-data` field properly set
   - Contact cluster administrator for proper kubeconfig

3. **Bypass SSL verification** (use with caution):
   ```bash
   python3 openshift-ovn-kubernetes-log-debug.py -k /path/to/kubeconfig --disable-ssl-verification
   ```

**⚠️ Security Warning:** The `--disable-ssl-verification` option should only be used in:
- Development/test environments
- Trusted network environments
- When you understand the security implications

This option makes your connection vulnerable to man-in-the-middle attacks.

### Pod Restart Issues
- Verify the pods are managed by a DaemonSet (they should be recreated automatically)
- Check that the pod pattern matches your actual pod names
- Ensure you have delete permissions on pods

### No Pods Found
- Verify the pod pattern matches your actual pod names (use `--debug` to see what's being searched)
- Check that the pods exist in the expected namespace
- Try `--all-nodes` to include all nodes regardless of pod filtering

### Revert Issues
- If no ConfigMap is found, debug logging is already disabled
- The revert process reads node names from the existing ConfigMap, not from pod discovery
- Use `--debug` with `--revert` to see which nodes will be affected before proceeding
- If ConfigMap exists but contains no node data, only the ConfigMap will be removed

### Dry-Run Best Practices
- **Always use `--dry-run` first** in production environments to preview changes
- Combine `--dry-run` with `--debug` for maximum visibility into what will happen
- Use dry-run to verify the correct nodes and pods will be affected
- Preview both apply and revert operations before executing them
- Dry-run shows the exact ConfigMap YAML that will be generated

## License

This project is licensed under the terms specified in the LICENSE file.
