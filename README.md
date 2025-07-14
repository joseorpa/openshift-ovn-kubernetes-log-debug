# Openshift ovn kubernetes log debug setter

This Python script dynamically generates a Kubernetes `ConfigMap` to override environment variables for OVN-Kubernetes components. It can target all nodes in a cluster or be filtered to only include nodes running specific pods.

## Features

-   **Dynamic Node Discovery:** Automatically fetches node names from your Kubernetes cluster.
-   **Targeted Configuration:** Filter nodes by a pod name pattern, allowing you to apply settings only to nodes running specific applications (e.g., `ovn-kubernetes-node` pods).
-   **Automated Application:** Creates or replaces the `ConfigMap` directly in the specified namespace using the official Kubernetes Python client.
-   **Flexible Authentication:** Works seamlessly whether run from inside a cluster (using a service account) or locally (using a `kubeconfig` file).

## Requirements

-   Python 3.6+
-   Access to a Kubernetes cluster.

## Installation

1.  Save the `k8s_configmap_generator.py` script.
2.  Install the required Python libraries using pip and the `requirements.txt` file:

    ```bash
    pip install -r requirements.txt
    ```

## Configuration

Before running the script, you can adjust the following variables inside the `main()` function at the bottom of `k8s_configmap_generator.py`:

-   `NAMESPACE`: The target namespace for the `ConfigMap`.
    -   **Default:** `"openshift-ovn-kubernetes"`

-   `FILTER_NODES_BY_PODS`: A boolean to control the node discovery method.
    -   **`True`:** (Default) The script will only include nodes that are running pods matching the `POD_NAME_PATTERN`.
    -   **`False`:** The script will include all nodes found in the cluster.

-   `POD_NAME_PATTERN`: The string pattern to search for in pod names. This is **required** if `FILTER_NODES_BY_PODS` is `True`.
    -   **Default:** `"ovn-kubernetes-node"`
    -   *Example:* To target nodes running pods for "my-app", you would set this to `"my-app"`.

## Usage

1.  Ensure your `kubeconfig` is correctly set up if you are running the script from your local machine. If running inside a cluster, ensure the service account has the necessary RBAC permissions to `list` nodes and pods, and to `create`/`get`/`replace` ConfigMaps.

2.  Run the script from your terminal:

    ```bash
    python k8s_configmap_generator.py
    ```

The script will print its progress to the console, indicating which nodes were found and confirming when the `ConfigMap` has been successfully applied.
