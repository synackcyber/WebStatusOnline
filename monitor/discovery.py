"""
Network Discovery Module
Discovers devices on the network via ping sweep and port scanning.
"""
import asyncio
import ipaddress
import logging
import socket
from typing import List, Dict, Optional
from .checker import check_ping, check_http

logger = logging.getLogger(__name__)

# Maximum subnet size to prevent DOS attacks
MAX_SUBNET_SIZE = 4096  # /20 for IPv4


async def discover_subnet(
    subnet: str,
    max_concurrent: int = 50,
    timeout: int = 2,
    check_http: bool = True
) -> List[Dict]:
    """
    Discover devices in a subnet.

    Args:
        subnet: Subnet in CIDR notation (e.g., '192.168.1.0/24')
        max_concurrent: Maximum concurrent pings
        timeout: Timeout for each check in seconds
        check_http: Whether to check for HTTP/HTTPS

    Returns:
        List of discovered devices with their capabilities
    """
    try:
        network = ipaddress.ip_network(subnet, strict=False)
    except ValueError as e:
        logger.error(f"Invalid subnet: {e}")
        return []

    # Protect against scanning huge subnets (DOS prevention)
    if network.num_addresses > MAX_SUBNET_SIZE:
        logger.error(
            f"Subnet too large: {network.num_addresses} addresses "
            f"(max: {MAX_SUBNET_SIZE}). Use a smaller subnet (e.g., /20 or smaller)."
        )
        return []

    logger.info(f"Starting discovery on {subnet} ({network.num_addresses} addresses)")

    # Create list of IPs to scan (skip network and broadcast)
    hosts = list(network.hosts()) if network.num_addresses > 2 else [network.network_address]

    discovered_devices = []

    # Use semaphore to limit concurrent operations
    semaphore = asyncio.Semaphore(max_concurrent)

    async def discover_host(ip: str):
        async with semaphore:
            device_info = {
                'ip': ip,
                'hostname': None,
                'status': 'unknown',
                'ping_response_time': None,
                'http_enabled': False,
                'https_enabled': False,
                'suggested_type': 'ping',
                'suggested_name': ip
            }

            # Step 1: Ping check
            success, response_time, _ = await check_ping(ip, timeout)

            if not success:
                return None  # Skip unreachable hosts

            device_info['status'] = 'up'
            device_info['ping_response_time'] = response_time

            # Try to resolve hostname
            try:
                hostname = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, socket.gethostbyaddr, ip
                    ),
                    timeout=1
                )
                device_info['hostname'] = hostname[0]
                device_info['suggested_name'] = hostname[0]
            except (socket.herror, socket.gaierror, OSError, asyncio.TimeoutError, Exception) as e:
                # Hostname resolution failed - not critical, continue without it
                logger.debug(f"Hostname resolution failed for {ip}: {e}")

            # Step 2: HTTP/HTTPS Discovery (if enabled)
            if check_http:
                http_info = await discover_http_services(ip, timeout)
                device_info.update(http_info)

                if device_info['https_enabled']:
                    device_info['suggested_type'] = 'https'
                elif device_info['http_enabled']:
                    device_info['suggested_type'] = 'http'

            return device_info

    # Run discovery in batches to avoid memory spike
    # Process in chunks to prevent creating millions of task objects
    batch_size = 500  # Process 500 hosts at a time
    discovered_devices = []

    for i in range(0, len(hosts), batch_size):
        batch = hosts[i:i + batch_size]
        logger.debug(f"Processing batch {i//batch_size + 1}/{(len(hosts)-1)//batch_size + 1} ({len(batch)} hosts)")

        tasks = [discover_host(str(ip)) for ip in batch]
        results = await asyncio.gather(*tasks)

        # Filter out None results (unreachable hosts)
        batch_devices = [d for d in results if d is not None]
        discovered_devices.extend(batch_devices)

    logger.info(f"Discovery complete: found {len(discovered_devices)} active devices")

    return discovered_devices


async def discover_http_services(ip: str, timeout: int = 2) -> Dict:
    """
    Check if HTTP or HTTPS services are available.

    Args:
        ip: IP address to check
        timeout: Timeout in seconds

    Returns:
        Dictionary with HTTP/HTTPS availability
    """
    http_info = {
        'http_enabled': False,
        'https_enabled': False,
        'http_status': None,
        'https_status': None
    }

    # Check HTTPS (port 443)
    try:
        success, _, error = await check_http(f'https://{ip}', timeout)
        if success:
            http_info['https_enabled'] = True
            http_info['https_status'] = 'Available'
        elif error and 'SSL' not in error:
            # If it's not an SSL error, HTTPS might still be there
            http_info['https_status'] = f'Error: {error}'
    except (asyncio.TimeoutError, OSError, Exception) as e:
        logger.debug(f"HTTPS check failed for {ip}: {e}")

    # Check HTTP (port 80)
    try:
        success, _, error = await check_http(f'http://{ip}', timeout)
        if success:
            http_info['http_enabled'] = True
            http_info['http_status'] = 'Available'
        elif error:
            http_info['http_status'] = f'Error: {error}'
    except (asyncio.TimeoutError, OSError, Exception) as e:
        logger.debug(f"HTTP check failed for {ip}: {e}")

    return http_info


async def discover_single_host(
    ip: str,
    check_http: bool = True,
    timeout: int = 3
) -> Optional[Dict]:
    """
    Discover a single host with full details.

    Args:
        ip: IP address to discover
        check_http: Whether to check HTTP/HTTPS
        timeout: Timeout for checks

    Returns:
        Device information dictionary or None if unreachable
    """
    device_info = {
        'ip': ip,
        'hostname': None,
        'status': 'unknown',
        'ping_response_time': None,
        'http_enabled': False,
        'https_enabled': False,
        'suggested_type': 'ping',
        'suggested_name': ip
    }

    # Ping check
    success, response_time, _ = await check_ping(ip, timeout)

    if not success:
        return None

    device_info['status'] = 'up'
    device_info['ping_response_time'] = response_time

    # Hostname resolution
    try:
        hostname = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None, socket.gethostbyaddr, ip
            ),
            timeout=1
        )
        device_info['hostname'] = hostname[0]
        device_info['suggested_name'] = hostname[0]
    except (socket.herror, socket.gaierror, OSError, asyncio.TimeoutError, Exception) as e:
        # Hostname resolution failed - not critical
        logger.debug(f"Hostname resolution failed for {ip}: {e}")

    # HTTP discovery
    if check_http:
        http_info = await discover_http_services(ip, timeout)
        device_info.update(http_info)

        if device_info['https_enabled']:
            device_info['suggested_type'] = 'https'
        elif device_info['http_enabled']:
            device_info['suggested_type'] = 'http'

    return device_info


def suggest_monitoring_config(device: Dict) -> Dict:
    """
    Suggest monitoring configuration based on discovered device info.

    Args:
        device: Device information from discovery

    Returns:
        Suggested monitoring configuration
    """
    config = {
        'name': device.get('suggested_name', device['ip']),
        'type': device.get('suggested_type', 'ping'),
        'address': device['ip'],
        'check_interval': 60,
        'failure_threshold': 3
    }

    return config
