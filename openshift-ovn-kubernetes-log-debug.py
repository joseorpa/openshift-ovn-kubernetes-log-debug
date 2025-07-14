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

def render_configmap_template(nodes):
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
    OVN_KUBE_LOG_LEVEL=5
    # You might also/instead want to enable debug logging for ovn-controller:
    OVN_LOG_LEVEL=dbg
{%- endif %}
{% endfor %}
  _master: |
    # This sets the log level for the ovn-kubernetes master process as well as the ovn-dbchecker:
    OVN_KUBE_LOG_LEVEL=5
    # You might also/instead want to enable debug logging for northd, nbdb and sbdb on all masters:
    OVN_LOG_LEVEL=dbg
"""
    # Render the template with the list of nodes
    return Environment().from_string(template_str).render(nodes=nodes)

def apply_configmap(api_instance, namespace, configmap_body):
    """Creates or updates the ConfigMap in the specified namespace."""
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
    
    args = parser.parse_args()
    
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
    configmap_yaml = render_configmap_template(nodes)
    print("Template rendered.")
    
    if args.debug:
        # Debug: Show the generated YAML structure
        print("\nGenerated ConfigMap YAML:")
        print("=" * 50)
        print(configmap_yaml)
        print("=" * 50)

    # --- Parse YAML to Python Dictionary ---
    configmap_body = yaml.safe_load(configmap_yaml)
    
    # --- Apply the ConfigMap ---
    print(f"Applying ConfigMap to namespace '{NAMESPACE}'...")
    apply_configmap(core_v1, NAMESPACE, configmap_body)
    print("Script finished successfully.")

if __name__ == "__main__":
    # Before running, ensure you have the required libraries installed:
    # pip install kubernetes jinja2 pyyaml
    main()
