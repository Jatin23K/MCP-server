#!/usr/bin/env bash
# wait-for-it.sh
# Use this script to wait for a service to be available before starting another service.
# Example: ./wait-for-it.sh host:port [-s] [-t timeout] [-- command args]
#   -s: Strict mode - exit immediately if a service is not available
#   -t: Timeout in seconds (default: 15)
#   --: After these flags, you can specify a command to run after the service is available

set -e

# Default values
host=""
port=""
timeout=15
strict=false
command=()

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        *:* )
            hostport=(${1//:/ })
            host=${hostport[0]}
            port=${hostport[1]}
            shift
            ;;
        -s | --strict )
            strict=true
            shift
            ;;
        -t | --timeout )
            timeout="$2"
            if [[ ! $timeout =~ ^[0-9]+$ ]]; then
                echo "Error: Invalid timeout value: $timeout" >&2
                exit 1
            fi
            shift 2
            ;;
        -- )
            shift
            command=("$@")
            break
            ;;
        * )
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# Validate host and port
if [[ -z "$host" || -z "$port" ]]; then
    echo "Usage: $0 host:port [-s] [-t timeout] [-- command args]" >&2
    echo "  -s: Strict mode - exit immediately if a service is not available" >&2
    echo "  -t: Timeout in seconds (default: 15)" >&2
    echo "  --: After these flags, you can specify a command to run after the service is available" >&2
    exit 1
fi

# Check if nc (netcat) is available
if ! command -v nc &> /dev/null; then
    echo "Error: netcat (nc) is required but not installed" >&2
    exit 1
fi

echo "Waiting for $host:$port..."

# Wait for the service to be available
start_ts=$(date +%s)
while :
do
    if nc -z "$host" "$port" >/dev/null 2>&1; then
        end_ts=$(date +%s)
        echo "$host:$port is available after $((end_ts - start_ts)) seconds"
        break
    fi
    
    if [[ $(( $(date +%s) - start_ts )) -gt $timeout ]]; then
        echo "Timeout ($timeout seconds) waiting for $host:$port" >&2
        if [[ "$strict" = true ]]; then
            exit 1
        else
            exit 0
        fi
    fi
    
    sleep 1
done

# Execute the command if provided
if [[ ${#command[@]} -gt 0 ]]; then
    echo "Executing: ${command[*]}"
    exec "${command[@]}"
fi
