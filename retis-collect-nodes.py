#!/usr/bin/env python3

import os
import sys
import argparse
import subprocess
import urllib.request
import tempfile
import time
from kubernetes import client, config

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

def get_nodes_from_configmap(api_instance, namespace='openshift-ovn-kubernetes'):
    """Read the env-overrides ConfigMap and extract node names."""
    print(f"Reading ConfigMap 'env-overrides' from namespace '{namespace}'...")
    
    try:
        configmap = api_instance.read_namespaced_config_map(
            name='env-overrides',
            namespace=namespace
        )
        print("✓ Found ConfigMap 'env-overrides'")
    except client.ApiException as e:
        if e.status == 404:
            print(f"✗ ConfigMap 'env-overrides' not found in namespace '{namespace}'")
            print("Please ensure the debug logging ConfigMap exists before running this script.")
            return []
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
        print("✗ No worker nodes found in ConfigMap data")
        return []
    else:
        print(f"✓ Found {len(affected_nodes)} worker nodes in ConfigMap:")
        for node in affected_nodes:
            print(f"  - {node}")
    
    return affected_nodes



def download_retis_script_locally(script_url="https://raw.githubusercontent.com/retis-org/retis/main/tools/retis_in_container.sh"):
    """Download the retis_in_container.sh script locally."""
    print(f"Downloading retis_in_container.sh from {script_url}...")
    
    try:
        # Create a temporary file
        temp_fd, temp_path = tempfile.mkstemp(suffix='.sh', prefix='retis_in_container_')
        
        with os.fdopen(temp_fd, 'wb') as temp_file:
            with urllib.request.urlopen(script_url) as response:
                temp_file.write(response.read())
        
        # Make the local file executable
        os.chmod(temp_path, 0o755)
        
        print(f"✓ Downloaded retis_in_container.sh to {temp_path}")
        return temp_path
        
    except Exception as e:
        print(f"✗ Failed to download retis_in_container.sh: {e}")
        return None

def setup_script_on_node(node_name, working_directory, local_script_path, dry_run=False):
    """Copy the retis_in_container.sh script to a specific node and set permissions if needed."""
    print(f"Checking retis_in_container.sh on node {node_name}...")
    
    if dry_run:
        print(f"[DRY RUN] Would check if {working_directory}/retis_in_container.sh exists with correct permissions")
        print(f"[DRY RUN] Would create working directory {working_directory} on {node_name} if needed")
        print(f"[DRY RUN] Would copy {local_script_path} to {node_name}:{working_directory}/retis_in_container.sh if needed")
        print(f"[DRY RUN] Would set executable permissions on the script if needed")
        return True
    
    try:
        # First, check if the script already exists with correct permissions
        check_cmd = f'oc debug node/{node_name} -- chroot /host ls -la {working_directory}/retis_in_container.sh'
        print(f"Checking existing script on {node_name}...")
        
        check_result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True, timeout=30)
        
        script_exists = False
        script_executable = False
        
        if check_result.returncode == 0 and check_result.stdout:
            script_exists = True
            # Check if the script is executable (look for 'x' in permissions)
            permissions = check_result.stdout.strip()
            print(f"Found existing script: {permissions}")
            
            # Check if user, group, or other has execute permission
            if 'x' in permissions[:10]:  # First 10 characters contain permissions
                script_executable = True
                print(f"✓ Script already exists with correct permissions on {node_name}")
                return True
            else:
                print(f"⚠ Script exists but is not executable on {node_name}")
        else:
            print(f"Script does not exist on {node_name}")
        
        # Create working directory if needed
        mkdir_cmd = f'oc debug node/{node_name} -- chroot /host mkdir -p {working_directory}'
        print(f"Ensuring directory exists on {node_name}...")
        
        mkdir_result = subprocess.run(mkdir_cmd, shell=True, capture_output=True, text=True, timeout=30)
        
        if mkdir_result.returncode != 0:
            print(f"⚠ Warning: Failed to create directory on {node_name} (might already exist)")
        
        # Only copy script if it doesn't exist
        if not script_exists:
            print(f"Copying script to {node_name}...")
            
            # Start a debug pod and get its name for copying
            debug_cmd = f'oc debug node/{node_name} --to-namespace=default -- sleep 300'
            print(f"Starting debug pod on {node_name}...")
            
            # Run the debug command in background and capture the pod name
            debug_process = subprocess.Popen(debug_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            # Wait a moment for the pod to start
            time.sleep(10)
            
            # Get the debug pod name
            get_pod_cmd = f'oc get pods -n default --no-headers | grep {node_name.split(".")[0]} | grep debug | head -1 | awk \'{{print $1}}\''
            pod_result = subprocess.run(get_pod_cmd, shell=True, capture_output=True, text=True, timeout=30)
            
            if pod_result.returncode != 0 or not pod_result.stdout.strip():
                print(f"✗ Failed to find debug pod for {node_name}")
                debug_process.terminate()
                return False
            
            debug_pod_name = pod_result.stdout.strip()
            print(f"Using debug pod: {debug_pod_name}")
            
            # Copy the script to the node
            copy_cmd = f'oc cp {local_script_path} default/{debug_pod_name}:/host{working_directory}/retis_in_container.sh'
            print(f"Copying script: {copy_cmd}")
            
            copy_result = subprocess.run(copy_cmd, shell=True, capture_output=True, text=True, timeout=60)
            
            # Terminate the debug pod
            debug_process.terminate()
            
            if copy_result.returncode != 0:
                print(f"✗ Failed to copy script to {node_name}")
                if copy_result.stderr:
                    print(f"Copy error: {copy_result.stderr}")
                return False
            
            print(f"✓ Script copied to {node_name}")
        
        # Set executable permissions if script is not executable
        if not script_executable:
            print(f"Setting executable permissions on {node_name}...")
            chmod_cmd = f'oc debug node/{node_name} -- chroot /host chmod a+x {working_directory}/retis_in_container.sh'
            
            chmod_result = subprocess.run(chmod_cmd, shell=True, capture_output=True, text=True, timeout=30)
            
            if chmod_result.returncode != 0:
                print(f"✗ Failed to set permissions on {node_name}")
                if chmod_result.stderr:
                    print(f"Chmod error: {chmod_result.stderr}")
                return False
            
            print(f"✓ Executable permissions set on {node_name}")
        
        # Final verification
        verify_cmd = f'oc debug node/{node_name} -- chroot /host ls -la {working_directory}/retis_in_container.sh'
        verify_result = subprocess.run(verify_cmd, shell=True, capture_output=True, text=True, timeout=30)
        
        if verify_result.returncode == 0:
            print(f"✓ Script setup complete on {node_name}")
            if verify_result.stdout:
                print(f"Final file info: {verify_result.stdout.strip()}")
            return True
        else:
            print(f"✗ Script verification failed on {node_name}")
            return False
        
    except subprocess.TimeoutExpired:
        print(f"✗ Timeout setting up script on {node_name}")
        return False
    except Exception as e:
        print(f"✗ Error setting up script on {node_name}: {e}")
        return False

def stop_retis_on_node(node_name, dry_run=False):
    """Stop the RETIS systemd unit on a specific node."""
    print(f"Stopping RETIS collection on node: {node_name}")
    
    if dry_run:
        print(f"[DRY RUN] Would execute command:")
        print(f"  Stop RETIS: oc debug node/{node_name} -- chroot /host systemctl stop RETIS")
        return True
    
    try:
        # Stop the RETIS systemd unit
        stop_command_str = f'oc debug node/{node_name} -- chroot /host systemctl stop RETIS'
        print(f"Executing stop command...")
        print(f"DEBUG: Stop command: {stop_command_str}")
        
        stop_result = subprocess.run(stop_command_str, shell=True, capture_output=True, text=True, timeout=60)
        
        if stop_result.returncode != 0:
            print(f"✗ RETIS stop command failed on {node_name} (exit code: {stop_result.returncode})")
            if stop_result.stderr:
                print("Stop error output:")
                print(stop_result.stderr)
            if stop_result.stdout:
                print("Stop output:")
                print(stop_result.stdout)
            return False
        else:
            print(f"✓ RETIS systemd unit successfully stopped on {node_name}")
            if stop_result.stdout:
                print("Stop output:")
                print(stop_result.stdout)
            return True
        
    except subprocess.TimeoutExpired:
        print(f"✗ RETIS stop command timed out on {node_name}")
        return False
    except FileNotFoundError:
        print("✗ 'oc' command not found. Please ensure OpenShift CLI is installed and in PATH.")
        return False
    except Exception as e:
        print(f"✗ Error stopping RETIS on {node_name}: {e}")
        return False

def run_retis_on_node(node_name, retis_image, working_directory, dry_run=False):
    """Run the oc debug command with RETIS collection on a specific node."""
    
    # Construct the shell command that will be executed after 'sh -c'
    # Use full path to the script since we downloaded it to the working directory
    shell_command = f"export RETIS_IMAGE='{retis_image}'; {working_directory}/retis_in_container.sh collect -o events.json --allow-system-changes --ovs-track --stack --probe-stack --filter-packet 'tcp port 8080 or tcp port 8081'"
    
    # Construct the command as a string for shell=True execution (like manual command)
    command_str = f'oc debug node/{node_name} -- chroot /host systemd-run --unit="RETIS" --working-directory={working_directory} sh -c "{shell_command}"'
    
    print(f"\nRunning RETIS collection on node: {node_name}")
    print(f"Working directory: {working_directory}")
    print(f"RETIS Image: {retis_image}")
    print(f"DEBUG: Shell command: {shell_command}")
    print(f"DEBUG: Full command: {command_str}")
    
    if dry_run:
        print(f"[DRY RUN] Would execute commands:")
        print(f"  1. RETIS collection: {command_str}")
        
        # Display the status check command
        status_command_str = f'oc debug node/{node_name} -- chroot /host systemctl status RETIS'
        print(f"  2. Status check: {status_command_str}")
        return True
    
    try:
        print(f"Executing RETIS collection command...")
        print(f"DEBUG: Command string: {command_str}")
        result = subprocess.run(command_str, shell=True, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            print(f"✓ RETIS collection command completed successfully on {node_name}")
            if result.stdout:
                print("Output:")
                print(result.stdout)
        else:
            print(f"✗ RETIS collection command failed on {node_name} (exit code: {result.returncode})")
            if result.stderr:
                print("Error output:")
                print(result.stderr)
            return False
        
        # Check the status of the RETIS systemd unit
        print(f"Checking RETIS systemd unit status on {node_name}...")
        status_command_str = f'oc debug node/{node_name} -- chroot /host systemctl status RETIS'
        
        status_result = subprocess.run(status_command_str, shell=True, capture_output=True, text=True, timeout=60)
        
        # Parse the status output to determine if the unit actually succeeded
        unit_status = "unknown"
        unit_failed = False
        
        if status_result.stdout:
            print("Status output:")
            print(status_result.stdout)
            
            # Look for key indicators in the status output
            status_output = status_result.stdout.lower()
            if "active: failed" in status_output or "failed" in status_output:
                unit_failed = True
                unit_status = "failed"
            elif "active: active" in status_output:
                unit_status = "running"
            elif "active: inactive" in status_output and "exited" in status_output:
                # Check if it completed successfully (exit code 0)
                if "code=exited, status=0" in status_output:
                    unit_status = "completed successfully"
                else:
                    unit_status = "completed with errors"
                    unit_failed = True
        
        if status_result.stderr:
            print("Status error output:")
            print(status_result.stderr)
        
        if unit_failed:
            print(f"✗ RETIS systemd unit failed on {node_name} (status: {unit_status})")
            return False
        elif unit_status == "running":
            print(f"✓ RETIS systemd unit is running on {node_name}")
            return True
        elif unit_status == "completed successfully":
            print(f"✓ RETIS systemd unit completed successfully on {node_name}")
            return True
        else:
            print(f"⚠ RETIS systemd unit status unclear on {node_name} (status: {unit_status})")
            return False
        
    except subprocess.TimeoutExpired:
        print(f"✗ RETIS collection or status check timed out on {node_name}")
        return False
    except FileNotFoundError:
        print("✗ 'oc' command not found. Please ensure OpenShift CLI is installed and in PATH.")
        return False
    except Exception as e:
        print(f"✗ Error running command on {node_name}: {e}")
        return False

def main():
    """Main function to read ConfigMap, extract nodes, and run RETIS collection."""
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Run RETIS collection on nodes from env-overrides ConfigMap",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 retis-collect-nodes.py --kubeconfig /path/to/kubeconfig
  python3 retis-collect-nodes.py --kubeconfig ~/.kube/config --retis-image "custom-registry/retis:latest"
  python3 retis-collect-nodes.py --kubeconfig /path/to/kubeconfig --working-directory /tmp
  python3 retis-collect-nodes.py --kubeconfig /path/to/kubeconfig --dry-run
  python3 retis-collect-nodes.py --kubeconfig /path/to/kubeconfig --stop
  python3 retis-collect-nodes.py --kubeconfig /path/to/kubeconfig --stop --parallel --dry-run
  python3 retis-collect-nodes.py  # Will prompt for kubeconfig path
        """
    )
    
    parser.add_argument(
        '--kubeconfig', '-k',
        help='Path to the kubeconfig file (will prompt if not provided)',
        type=str
    )
    parser.add_argument(
        '--retis-image',
        help='RETIS container image to use (default: image-registry.openshift-image-registry.svc:5000/default/retis)',
        default='image-registry.openshift-image-registry.svc:5000/default/retis',
        type=str
    )
    parser.add_argument(
        '--working-directory',
        help='Working directory for the RETIS collection (default: /var/tmp)',
        default='/var/tmp',
        type=str
    )
    parser.add_argument(
        '--namespace', '-n',
        help='Namespace to read the ConfigMap from (default: openshift-ovn-kubernetes)',
        default='openshift-ovn-kubernetes',
        type=str
    )
    parser.add_argument(
        '--dry-run',
        help='Show what commands would be executed without running them',
        action='store_true'
    )
    parser.add_argument(
        '--parallel',
        help='Run RETIS collection on all nodes in parallel (default: sequential)',
        action='store_true'
    )
    parser.add_argument(
        '--stop',
        help='Stop RETIS collection on all nodes (reads nodes from ConfigMap)',
        action='store_true'
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.stop:
        if args.retis_image != 'image-registry.openshift-image-registry.svc:5000/default/retis':
            print("Warning: --retis-image is ignored when using --stop")
        if args.working_directory != '/var/tmp':
            print("Warning: --working-directory is ignored when using --stop")
    
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
        print("✓ Successfully connected to Kubernetes cluster.")
    except Exception as e:
        print(f"✗ Failed to connect to Kubernetes cluster: {e}")
        print("Please verify your kubeconfig is valid and the cluster is accessible.")
        return

    # --- Get nodes from ConfigMap ---
    nodes = get_nodes_from_configmap(core_v1, args.namespace)
    
    if not nodes:
        print("No nodes found in ConfigMap. Exiting.")
        return
    
    # --- Handle stop operation ---
    if args.stop:
        print(f"\nPreparing to stop RETIS collection on {len(nodes)} nodes...")
        
        if args.dry_run:
            print("\n[DRY RUN] The following stop commands would be executed:")
        
        # Stop RETIS on each node
        if args.parallel:
            print("\nStopping RETIS collection in parallel mode...")
            import concurrent.futures
            
            def stop_with_progress(node):
                return stop_retis_on_node(node, args.dry_run)
            
            success_count = 0
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(nodes), 5)) as executor:
                future_to_node = {executor.submit(stop_with_progress, node): node for node in nodes}
                
                for future in concurrent.futures.as_completed(future_to_node):
                    node = future_to_node[future]
                    try:
                        success = future.result()
                        if success:
                            success_count += 1
                    except Exception as e:
                        print(f"✗ Exception occurred stopping RETIS on node {node}: {e}")
        else:
            print("\nStopping RETIS collection sequentially...")
            success_count = 0
            for i, node in enumerate(nodes, 1):
                print(f"\n--- Stopping RETIS on node {i}/{len(nodes)}: {node} ---")
                success = stop_retis_on_node(node, args.dry_run)
                if success:
                    success_count += 1
        
        # Summary for stop operation
        print(f"\n{'=' * 50}")
        print("RETIS Stop Summary")
        print(f"{'=' * 50}")
        print(f"Total nodes: {len(nodes)}")
        print(f"Successfully stopped: {success_count}")
        print(f"Failed to stop: {len(nodes) - success_count}")
        
        if args.dry_run:
            print("\n[DRY RUN] No actual commands were executed.")
        else:
            if success_count == len(nodes):
                print("\n✓ RETIS collection stopped on all nodes!")
            elif success_count > 0:
                print(f"\n⚠ RETIS collection stopped on {success_count}/{len(nodes)} nodes.")
            else:
                print("\n✗ Failed to stop RETIS collection on all nodes.")
        
        print("Script finished.")
        return
    
    print(f"\nPreparing to run RETIS collection on {len(nodes)} nodes...")
    print(f"RETIS Image: {args.retis_image}")
    print(f"Working Directory: {args.working_directory}")
    
    if args.dry_run:
        print("\n[DRY RUN] The following commands would be executed:")
    
    # --- Download retis_in_container.sh script locally ---
    print(f"\n--- Downloading retis_in_container.sh script locally ---")
    local_script_path = None
    
    if not args.dry_run:
        local_script_path = download_retis_script_locally()
        if not local_script_path:
            print("✗ Failed to download script locally. Cannot proceed.")
            return
    else:
        print("[DRY RUN] Would download retis_in_container.sh locally")
        local_script_path = "/tmp/dummy_script_path"  # placeholder for dry run
    
    try:
        # --- Setup retis_in_container.sh script on each node ---
        print(f"\n--- Setting up retis_in_container.sh script on {len(nodes)} nodes ---")
        setup_success_count = 0
        setup_failed_nodes = []
        
        for i, node in enumerate(nodes, 1):
            print(f"\n--- Setting up script on node {i}/{len(nodes)}: {node} ---")
            setup_success = setup_script_on_node(node, args.working_directory, local_script_path, dry_run=args.dry_run)
            if setup_success:
                setup_success_count += 1
            else:
                setup_failed_nodes.append(node)
        
        if setup_failed_nodes and not args.dry_run:
            print(f"\n⚠ Script setup failed on {len(setup_failed_nodes)} nodes:")
            for node in setup_failed_nodes:
                print(f"  - {node}")
            print("RETIS collection will only run on nodes where script setup succeeded.")
            # Remove failed nodes from the list
            nodes = [node for node in nodes if node not in setup_failed_nodes]
            if not nodes:
                print("No nodes available for RETIS collection. Exiting.")
                return
        
        print(f"\n--- Script setup complete: {setup_success_count}/{len(nodes) + len(setup_failed_nodes)} nodes successful ---")
        
        # --- Run RETIS collection on each node ---
        if args.parallel:
            print("\nRunning RETIS collection in parallel mode...")
            import concurrent.futures
            import threading
            
            def run_with_progress(node):
                return run_retis_on_node(node, args.retis_image, args.working_directory, args.dry_run)
            
            success_count = 0
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(nodes), 5)) as executor:
                future_to_node = {executor.submit(run_with_progress, node): node for node in nodes}
                
                for future in concurrent.futures.as_completed(future_to_node):
                    node = future_to_node[future]
                    try:
                        success = future.result()
                        if success:
                            success_count += 1
                    except Exception as e:
                        print(f"✗ Exception occurred for node {node}: {e}")
        else:
            print("\nRunning RETIS collection sequentially...")
            success_count = 0
            for i, node in enumerate(nodes, 1):
                print(f"\n--- Processing node {i}/{len(nodes)} ---")
                success = run_retis_on_node(node, args.retis_image, args.working_directory, args.dry_run)
                if success:
                    success_count += 1
        
        # --- Summary ---
        print(f"\n{'=' * 50}")
        print("RETIS Collection Summary")
        print(f"{'=' * 50}")
        print(f"Total nodes: {len(nodes)}")
        print(f"Successful: {success_count}")
        print(f"Failed: {len(nodes) - success_count}")
        
        if args.dry_run:
            print("\n[DRY RUN] No actual commands were executed.")
        else:
            if success_count == len(nodes):
                print("\n✓ All RETIS collections completed successfully!")
            elif success_count > 0:
                print(f"\n⚠ {success_count}/{len(nodes)} RETIS collections completed successfully.")
            else:
                print("\n✗ All RETIS collections failed.")
        
        print("Script finished.")
        
    finally:
        # Clean up the temporary script file
        if local_script_path and not args.dry_run and local_script_path != "/tmp/dummy_script_path":
            try:
                os.unlink(local_script_path)
                print(f"Cleaned up temporary file: {local_script_path}")
            except Exception as e:
                print(f"Warning: Failed to clean up temporary file {local_script_path}: {e}")

if __name__ == "__main__":
    main() 