import os
import sys
import argparse
import yaml
from jinja2 import Environment
from kubernetes import client, config

def get_all_node_names(api_instance):
    """Fetches a list of all node names from the cluster."""
    print("Fetching all node names from the cluster...")
    try:
        node_list = api_instance.list_node()
        node_names = [item.metadata.name for item in node_list.items]
        if not node_names:
            print("Warning: No nodes found in the cluster.")
        else:
            print(f"Found {len(node_names)} total nodes.")
        return node_names
    except client.ApiException as e:
        print(f"Error fetching nodes from Kubernetes API: {e}")
        print("Please ensure your kube-config is correct and you have permissions to list nodes.")
        return []

def get_nodes_by_pod_filter(api_instance, pod_name_pattern):
    """
    Fetches a list of unique node names that are running pods whose names contain the provided pattern.
    """
    print(f"Fetching nodes running pods with names containing '{pod_name_pattern}'...")

    try:
        pod_list = api_instance.list_pod_for_all_namespaces(watch=False)
        # Use a set to store unique node names
        nodes_with_pods = set()
        for item in pod_list.items:
            # Ensure the pod is scheduled to a node and its name matches the pattern
            if item.spec.node_name and pod_name_pattern in item.metadata.name:
                nodes_with_pods.add(item.spec.node_name)

        if not nodes_with_pods:
            print(f"Warning: No pods found with names matching the pattern '{pod_name_pattern}'.")
        else:
            print(f"Found {len(nodes_with_pods)} nodes running matching pods.")
        return list(nodes_with_pods)
    except client.ApiException as e:
        print(f"Error fetching pods from Kubernetes API: {e}")
        print("Please ensure your kube-config is correct and you have permissions to list pods.")
        return []

def render_configmap_template(nodes, ovn_kube_log_level=3, ovn_log_level='warn'):
    """Renders the ConfigMap YAML using a Jinja2 template."""
    # This uses an inline string as the template.
    template_str = """
kind: ConfigMap
apiVersion: v1
metadata:
  name: env-overrides
  namespace: openshift-ovn-kubernetes
data:
{% for node in nodes %}
{%- if 'master' not in node.lower() %}
  {{ node }}: |
    # This sets the log level for the ovn-kubernetes node process:
    OVN_KUBE_LOG_LEVEL={{ ovn_kube_log_level }}
    # You might also/instead want to enable debug logging for ovn-controller:
    OVN_LOG_LEVEL={{ ovn_log_level }}
{%- endif %}
{% endfor %}
  _master: |
    # This sets the log level for the ovn-kubernetes master process as well as the ovn-dbchecker:
    OVN_KUBE_LOG_LEVEL={{ ovn_kube_log_level }}
    # You might also/instead want to enable debug logging for northd, nbdb and sbdb on all masters:
    OVN_LOG_LEVEL={{ ovn_log_level }}
"""
    # Render the template with the list of nodes and log levels
    return Environment().from_string(template_str).render(
        nodes=nodes, 
        ovn_kube_log_level=ovn_kube_log_level, 
        ovn_log_level=ovn_log_level
    )

def apply_configmap(api_instance, namespace, configmap_body, dry_run=False):
    """Creates or updates the ConfigMap in the specified namespace."""
    if dry_run:
        print(f"[DRY RUN] Would apply ConfigMap 'env-overrides' to namespace '{namespace}'")
        return
    
    try:
        # Check if the namespace exists
        api_instance.read_namespace(name=namespace)
    except client.ApiException as e:
        if e.status == 404:
            print(f"Namespace '{namespace}' does not exist. Creating it...")
            namespace_body = client.V1Namespace(metadata=client.V1ObjectMeta(name=namespace))
            api_instance.create_namespace(body=namespace_body)
            print(f"Namespace '{namespace}' created.")
        else:
            raise

    try:
        # Check if the ConfigMap already exists
        api_instance.read_namespaced_config_map(name=configmap_body['metadata']['name'], namespace=namespace)
        print("ConfigMap 'env-overrides' already exists. Replacing it...")
        api_instance.replace_namespaced_config_map(
            name=configmap_body['metadata']['name'],
            namespace=namespace,
            body=configmap_body
        )
        print("ConfigMap 'env-overrides' replaced.")
    except client.ApiException as e:
        if e.status == 404:
            print("ConfigMap 'env-overrides' does not exist. Creating it...")
            api_instance.create_namespaced_config_map(
                namespace=namespace,
                body=configmap_body
            )
            print("ConfigMap 'env-overrides' created.")
        else:
            print(f"Error checking/creating ConfigMap: {e}")
            raise

def restart_ovnkube_pods(api_instance, namespace, pod_pattern, nodes, dry_run=False):
    """Restart ovnkube-node pods on the specified nodes by deleting them.
    
    Note: pod_pattern was used for node filtering, but this function always restarts ovnkube-node pods.
    """
    print(f"\nRestarting ovnkube-node pods on {len(nodes)} nodes (nodes were identified using pattern: {pod_pattern})...")
    
    try:
        # Get all pods in the namespace
        pod_list = api_instance.list_namespaced_pod(namespace=namespace)
        
        pods_to_restart = []
        for pod in pod_list.items:
            # Always look for ovnkube-node pods on the specified nodes
            if ("ovnkube-node" in pod.metadata.name and 
                pod.spec.node_name in nodes):
                pods_to_restart.append(pod)
        
        if not pods_to_restart:
            print(f"No ovnkube-node pods found on the specified nodes.")
            return
        
        print(f"Found {len(pods_to_restart)} ovnkube-node pods to restart:")
        for pod in pods_to_restart:
            print(f"  - {pod.metadata.name} (on {pod.spec.node_name})")
        
        if dry_run:
            print(f"\n[DRY RUN] Would delete {len(pods_to_restart)} ovnkube-node pods (DaemonSet will recreate them)")
            return
        
        # Delete the pods
        print("\nDeleting pods (DaemonSet will recreate them)...")
        for pod in pods_to_restart:
            try:
                api_instance.delete_namespaced_pod(
                    name=pod.metadata.name,
                    namespace=namespace,
                    body=client.V1DeleteOptions()
                )
                print(f"✓ Deleted {pod.metadata.name}")
            except client.ApiException as e:
                print(f"✗ Failed to delete {pod.metadata.name}: {e}")
        
        print(f"\nPod restart initiated. The DaemonSet will recreate the pods automatically.")
        print("Note: It may take a few moments for the pods to fully restart and become ready.")
        
    except client.ApiException as e:
        print(f"Error restarting pods: {e}")
        raise

def revert_debug_logging(api_instance, namespace, pod_pattern, restart_pods=False, dry_run=False):
    """Revert debug logging by removing the ConfigMap and optionally restarting pods."""
    print(f"Reverting debug logging configuration...")
    
    try:
        # Try to read the existing ConfigMap
        print(f"Reading existing ConfigMap 'env-overrides' from namespace '{namespace}'...")
        try:
            configmap = api_instance.read_namespaced_config_map(
                name='env-overrides',
                namespace=namespace
            )
            print("✓ Found existing ConfigMap")
        except client.ApiException as e:
            if e.status == 404:
                print("✓ No ConfigMap found to revert. Debug logging is already disabled.")
                return
            else:
                print(f"Error reading ConfigMap: {e}")
                raise
        
        # Extract node names from ConfigMap data (excluding _master)
        affected_nodes = []
        if configmap.data:
            for key in configmap.data.keys():
                if key != '_master':
                    affected_nodes.append(key)
        
        if not affected_nodes:
            print("✓ No nodes found in ConfigMap data")
        else:
            print(f"✓ Found {len(affected_nodes)} nodes in ConfigMap:")
            for node in affected_nodes:
                print(f"  - {node}")
        
        # Delete the ConfigMap
        if dry_run:
            print(f"\n[DRY RUN] Would delete ConfigMap 'env-overrides'")
        else:
            print(f"\nDeleting ConfigMap 'env-overrides'...")
            try:
                api_instance.delete_namespaced_config_map(
                    name='env-overrides',
                    namespace=namespace,
                    body=client.V1DeleteOptions()
                )
                print("✓ ConfigMap deleted successfully")
            except client.ApiException as e:
                print(f"Error deleting ConfigMap: {e}")
                raise
        
        # Restart pods if requested and we have nodes
        if restart_pods and affected_nodes:
            restart_ovnkube_pods(api_instance, namespace, pod_pattern, affected_nodes, dry_run)
        elif restart_pods:
            print("No nodes to restart pods on.")
        
        if dry_run:
            print("\n[DRY RUN] Debug logging configuration would be reverted successfully!")
        else:
            print("\nDebug logging configuration reverted successfully!")
        if not restart_pods:
            print("Note: You may want to restart ovnkube-node pods manually for changes to take effect immediately.")
        
    except Exception as e:
        print(f"Error during revert process: {e}")
        raise

def get_kubeconfig_path(args):
    """Get the kubeconfig path from arguments or user input."""
    if args.kubeconfig:
        kubeconfig_path = args.kubeconfig
        print(f"Using kubeconfig from command line argument: {kubeconfig_path}")
    else:
        print("No kubeconfig path provided via --kubeconfig argument.")
        kubeconfig_path = input("Please enter the path to your kubeconfig file: ").strip()
        if not kubeconfig_path:
            print("No kubeconfig path provided. Exiting.")
            sys.exit(1)
    
    # Expand user home directory if needed
    kubeconfig_path = os.path.expanduser(kubeconfig_path)
    
    # Check if file exists
    if not os.path.exists(kubeconfig_path):
        print(f"Kubeconfig file not found at: {kubeconfig_path}")
        print("Please verify the file path exists.")
        sys.exit(1)
    
    return kubeconfig_path

def main():
    """Main function to generate and apply the ConfigMap."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Generate and apply OVN-Kubernetes debug logging ConfigMap",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 openshift-ovn-kubernetes-log-debug.py --kubeconfig /path/to/kubeconfig
  python3 openshift-ovn-kubernetes-log-debug.py --kubeconfig ~/.kube/config
  python3 openshift-ovn-kubernetes-log-debug.py --kubeconfig /path/to/kubeconfig --restart-pods
  python3 openshift-ovn-kubernetes-log-debug.py --kubeconfig /path/to/kubeconfig --dry-run
  python3 openshift-ovn-kubernetes-log-debug.py --kubeconfig /path/to/kubeconfig --ovn-kube-log-level 3 --ovn-log-level warn
  python3 openshift-ovn-kubernetes-log-debug.py --kubeconfig /path/to/kubeconfig --revert
  python3 openshift-ovn-kubernetes-log-debug.py --kubeconfig /path/to/kubeconfig --revert --restart-pods
  python3 openshift-ovn-kubernetes-log-debug.py --kubeconfig /path/to/kubeconfig --revert --dry-run
  python3 openshift-ovn-kubernetes-log-debug.py  # Will prompt for kubeconfig path
        """
    )
    parser.add_argument(
        '--kubeconfig', '-k',
        help='Path to the kubeconfig file (will prompt if not provided)',
        type=str
    )
    parser.add_argument(
        '--pod-pattern', '-p',
        help='Pod name pattern to filter nodes (default: ovnkube-node)',
        default='ovnkube-node',
        type=str
    )
    parser.add_argument(
        '--all-nodes', '-a',
        help='Include all nodes in the cluster (ignore pod filtering)',
        action='store_true'
    )
    parser.add_argument(
        '--namespace', '-n',
        help='Target namespace for the ConfigMap (default: openshift-ovn-kubernetes)',
        default='openshift-ovn-kubernetes',
        type=str
    )
    parser.add_argument(
        '--debug',
        help='Show debug output including generated YAML',
        action='store_true'
    )
    parser.add_argument(
        '--restart-pods',
        help='Restart ovnkube-node pods after applying ConfigMap',
        action='store_true'
    )
    parser.add_argument(
        '--revert',
        help='Revert debug logging by removing ConfigMap and restarting affected pods',
        action='store_true'
    )
    parser.add_argument(
        '--dry-run',
        help='Show what would be done without making any changes',
        action='store_true'
    )
    parser.add_argument(
        '--ovn-kube-log-level',
        help='OVN Kubernetes log level (1-10, default: 3)',
        type=int,
        choices=range(1, 11),
        default=3,
        metavar='LEVEL'
    )
    parser.add_argument(
        '--ovn-log-level',
        help='OVN log level (off, emer, err, warn, info, dbg, default: warn)',
        choices=['off', 'emer', 'err', 'warn', 'info', 'dbg'],
        default='warn',
        metavar='LEVEL'
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.revert:
        if args.all_nodes:
            print("Error: --revert cannot be used with --all-nodes")
            sys.exit(1)
        if args.pod_pattern != 'ovnkube-node':
            print("Warning: --pod-pattern is ignored when using --revert (pattern will be read from ConfigMap)")
        if args.ovn_kube_log_level != 3 or args.ovn_log_level != 'warn':
            print("Warning: --ovn-kube-log-level and --ovn-log-level are ignored when using --revert")
    
    # --- Configuration ---
    NAMESPACE = args.namespace
    POD_NAME_PATTERN = args.pod_pattern
    FILTER_NODES_BY_PODS = not args.all_nodes
    
    # Get kubeconfig path
    kubeconfig_path = get_kubeconfig_path(args)

    # --- Load Kubernetes Configuration ---
    try:
        # Try to load in-cluster config first
        config.load_incluster_config()
        print("Loaded in-cluster Kubernetes configuration.")
    except config.ConfigException:
        try:
            # Use the specified kubeconfig file path
            config.load_kube_config(config_file=kubeconfig_path)
            print(f"Loaded kubeconfig from: {kubeconfig_path}")
        except config.ConfigException as e:
            print(f"Could not load kubeconfig from {kubeconfig_path}")
            print(f"Error: {e}")
            try:
                # Fallback to default kube-config file location
                config.load_kube_config()
                print("Loaded default kube-config.")
            except config.ConfigException:
                print("Could not locate a valid kubeconfig file or in-cluster config.")
                print("Please ensure your kubeconfig file exists and is properly configured.")
                return
        except FileNotFoundError:
            print(f"Kubeconfig file not found at: {kubeconfig_path}")
            print("Please verify the file path exists.")
            return

    # --- Create Kubernetes API client ---
    core_v1 = client.CoreV1Api()

    # Test the connection
    try:
        print("Testing connection to Kubernetes cluster...")
        version = core_v1.get_api_resources()
        print("Successfully connected to Kubernetes cluster.")
    except Exception as e:
        print(f"Failed to connect to Kubernetes cluster: {e}")
        print("Please verify your kubeconfig is valid and the cluster is accessible.")
        return

    # --- Handle revert operation ---
    if args.revert:
        revert_debug_logging(core_v1, NAMESPACE, POD_NAME_PATTERN, args.restart_pods, args.dry_run)
        print("Script finished successfully.")
        return

    # --- Get Node Names ---
    nodes = []
    if FILTER_NODES_BY_PODS:
        if not POD_NAME_PATTERN:
            print("Error: Filtering by pods is enabled, but POD_NAME_PATTERN is empty.")
            print("Please specify a pattern to continue.")
            return
        nodes = get_nodes_by_pod_filter(core_v1, POD_NAME_PATTERN)
    else:
        nodes = get_all_node_names(core_v1)

    if not nodes:
        print("No node names were found based on the filter criteria. Cannot create ConfigMap. Exiting.")
        return

    # --- Render ConfigMap YAML ---
    print("Rendering ConfigMap template...")
    print(f"Using log levels: OVN_KUBE_LOG_LEVEL={args.ovn_kube_log_level}, OVN_LOG_LEVEL={args.ovn_log_level}")
    configmap_yaml = render_configmap_template(nodes, args.ovn_kube_log_level, args.ovn_log_level)
    print("Template rendered.")

    if args.debug or args.dry_run:
        # Show the generated YAML structure for debug mode or dry-run
        print("\nGenerated ConfigMap YAML:")
        print("=" * 50)
        print(configmap_yaml)
        print("=" * 50)

    # --- Parse YAML to Python Dictionary ---
    configmap_body = yaml.safe_load(configmap_yaml)
    
    if args.dry_run:
        print(f"\n[DRY RUN] ConfigMap 'env-overrides' would be created/updated in namespace '{NAMESPACE}'")
        print(f"[DRY RUN] This would affect {len(nodes)} nodes:")
        for node in nodes:
            print(f"  - {node}")
    
    # --- Apply the ConfigMap ---
    print(f"\nApplying ConfigMap to namespace '{NAMESPACE}'...")
    apply_configmap(core_v1, NAMESPACE, configmap_body, args.dry_run)
    
    # --- Restart pods if requested ---
    if args.restart_pods:
        restart_ovnkube_pods(core_v1, NAMESPACE, POD_NAME_PATTERN, nodes, args.dry_run)
    
    if args.dry_run:
        print("\n[DRY RUN] Script completed successfully (no changes were made).")
    else:
        print("Script finished successfully.")

if __name__ == "__main__":
    # Before running, ensure you have the required libraries installed:
    # pip install kubernetes jinja2 pyyaml
    main()
