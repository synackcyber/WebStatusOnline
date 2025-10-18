"""
Monitoring checker module.
Performs actual health checks for targets.
"""
import asyncio
import platform
import time
import re
from typing import Tuple, Optional, Dict, Any
import httpx
import logging

logger = logging.getLogger(__name__)

# Cache system type at module level (never changes during runtime)
_SYSTEM = platform.system().lower()

# Reusable HTTP client (connection pooling)
_HTTP_CLIENT = None

async def _get_http_client():
    """Get or create singleton HTTP client with connection pooling."""
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None:
        _HTTP_CLIENT = httpx.AsyncClient(
            follow_redirects=False,  # Keep HTTP and HTTPS separate - don't follow redirects
            verify=True,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
            timeout=httpx.Timeout(10.0, connect=5.0)
        )
    return _HTTP_CLIENT


async def check_ping(address: str, timeout: int = 5, packet_count: int = 3, min_success: int = 1) -> Tuple[bool, Optional[float], Optional[str]]:
    """
    Check if a host is reachable via ICMP ping using multiple packets.

    Args:
        address: IP address or hostname to ping
        timeout: Timeout in seconds per packet
        packet_count: Number of ICMP packets to send (default: 3)
        min_success: Minimum packets that must succeed (default: 1)

    Returns:
        Tuple of (success, response_time, error_message)
    """
    # Sanitize address (trim whitespace)
    address = address.strip()

    # Validate parameters
    if packet_count < 1:
        return False, None, "Invalid packet_count: must be >= 1"
    if min_success < 1 or min_success > packet_count:
        return False, None, f"Invalid min_success: must be between 1 and {packet_count}"
    if timeout < 1:
        return False, None, "Invalid timeout: must be >= 1"

    # Build ping command using cached system type
    if _SYSTEM == 'windows':
        # Windows ping: -n count, -w timeout_in_ms
        cmd = ['ping', '-n', str(packet_count), '-w', str(timeout * 1000), address]
    else:
        # Unix-like systems (Linux, macOS, etc.): -c count, -W timeout_in_seconds
        # Note: -i 0.2 (200ms interval) requires root on some systems, so we use default interval
        cmd = ['ping', '-c', str(packet_count), '-W', str(timeout), address]

    start_time = time.time()

    try:
        # Run ping command
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            # Allow extra time for all packets (default interval is ~1s between packets)
            total_timeout = (timeout * packet_count) + packet_count + 2
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=total_timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return False, None, f"Ping timeout after {total_timeout}s"

        response_time = time.time() - start_time

        # Parse ping output to get statistics
        output = stdout.decode('utf-8', errors='replace')
        stats = _parse_ping_output(output, _SYSTEM)

        if stats:
            packets_sent = stats['packets_sent']
            packets_received = stats['packets_received']
            packet_loss_pct = stats['packet_loss_pct']
            avg_rtt = stats['avg_rtt']

            # Determine success based on minimum packets received
            if packets_received >= min_success:
                # Success: At least min_success packets returned
                if packet_loss_pct > 0:
                    rtt_str = f"{avg_rtt:.3f}s" if avg_rtt else "N/A"
                    msg = f"OK ({packet_loss_pct:.0f}% loss, {packets_received}/{packets_sent} pkts, RTT: {rtt_str})"
                    logger.debug(f"Ping {address}: {msg}")
                # Use parsed avg_rtt if available, otherwise use total response_time
                return True, avg_rtt if avg_rtt is not None else response_time, None
            else:
                # Failure: Not enough packets returned
                error_msg = f"{packet_loss_pct:.0f}% packet loss ({packets_received}/{packets_sent} received)"
                return False, None, error_msg
        else:
            # Couldn't parse output, fall back to return code
            if process.returncode == 0:
                return True, response_time, None
            else:
                error_msg = stderr.decode('utf-8', errors='replace').strip() if stderr else "Ping failed"
                return False, None, error_msg

    except FileNotFoundError:
        # Ping command not found, try TCP fallback
        logger.warning(f"Ping command not found, using TCP fallback for {address}")
        return await check_tcp_port(address, 80, timeout)

    except Exception as e:
        return False, None, f"Ping error: {str(e)}"


def _parse_ping_output(output: str, system: str) -> Optional[dict]:
    """
    Parse ping command output to extract statistics.

    Args:
        output: Raw stdout from ping command
        system: Operating system ('windows', 'linux', 'darwin', etc.)

    Returns:
        Dict with keys: packets_sent, packets_received, packet_loss_pct, avg_rtt
        Returns None if parsing fails
    """
    try:
        if system == 'windows':
            # Windows format: "Packets: Sent = 3, Received = 3, Lost = 0 (0% loss)"
            match = re.search(r'Sent = (\d+), Received = (\d+), Lost = \d+ \((\d+)% loss\)', output)
            if not match:
                return None

            packets_sent = int(match.group(1))
            packets_received = int(match.group(2))
            packet_loss_pct = float(match.group(3))

            # Extract average time: "Average = 23ms"
            avg_match = re.search(r'Average = (\d+)ms', output)
            avg_rtt = float(avg_match.group(1)) / 1000.0 if avg_match else None

            return {
                'packets_sent': packets_sent,
                'packets_received': packets_received,
                'packet_loss_pct': packet_loss_pct,
                'avg_rtt': avg_rtt
            }
        else:
            # Unix format: "3 packets transmitted, 3 received, 0% packet loss, time 404ms"
            match = re.search(r'(\d+) packets transmitted, (\d+) (?:packets )?received, (?:\+\d+ errors, )?(\d+(?:\.\d+)?)% packet loss', output)
            if not match:
                return None

            packets_sent = int(match.group(1))
            packets_received = int(match.group(2))
            packet_loss_pct = float(match.group(3))

            # Extract average RTT: "rtt min/avg/max/mdev = 0.123/0.456/0.789/0.111 ms"
            rtt_match = re.search(r'rtt min/avg/max/(?:mdev|stddev) = [\d.]+/([\d.]+)/[\d.]+/[\d.]+ ms', output)
            avg_rtt = float(rtt_match.group(1)) / 1000.0 if rtt_match else None

            return {
                'packets_sent': packets_sent,
                'packets_received': packets_received,
                'packet_loss_pct': packet_loss_pct,
                'avg_rtt': avg_rtt
            }
    except Exception as e:
        logger.debug(f"Failed to parse ping output: {e}")
        return None


async def check_tcp_port(address: str, port: int = 80, timeout: int = 5) -> Tuple[bool, Optional[float], Optional[str]]:
    """
    Check if a TCP port is open (fallback for ping).

    Args:
        address: IP address or hostname
        port: TCP port to check
        timeout: Timeout in seconds

    Returns:
        Tuple of (success, response_time, error_message)
    """
    # Sanitize address (trim whitespace)
    address = address.strip()

    start_time = time.time()

    try:
        # Try to open a TCP connection
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(address, port),
            timeout=timeout
        )

        response_time = time.time() - start_time

        # Close the connection
        writer.close()
        await writer.wait_closed()

        return True, response_time, None

    except asyncio.TimeoutError:
        return False, None, f"TCP connection timeout after {timeout}s"
    except ConnectionRefusedError:
        return False, None, f"Connection refused on port {port}"
    except Exception as e:
        return False, None, f"TCP check error: {str(e)}"


async def check_http(url: str, timeout: int = 10) -> Tuple[bool, Optional[float], Optional[str]]:
    """
    Check if an HTTP/HTTPS endpoint is accessible.

    Args:
        url: Full URL to check (must include http:// or https://)
        timeout: Timeout in seconds

    Returns:
        Tuple of (success, response_time, error_message)
    """
    # Sanitize URL (trim whitespace)
    url = url.strip()

    # Ensure URL has protocol
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    start_time = time.time()

    try:
        # Use shared HTTP client for connection pooling
        client = await _get_http_client()

        # Override timeout for this specific request
        response = await client.get(url, timeout=timeout)
        response_time = time.time() - start_time

        # Consider 2xx and 3xx as success
        if 200 <= response.status_code < 400:
            return True, response_time, None
        else:
            return False, response_time, f"HTTP {response.status_code}"

    except httpx.TimeoutException:
        return False, None, f"HTTP timeout after {timeout}s"

    except httpx.ConnectError as e:
        return False, None, f"Connection error: {str(e)}"

    except httpx.TooManyRedirects:
        return False, None, "Too many redirects"

    except httpx.SSLError as e:
        return False, None, f"SSL error: {str(e)}"

    except httpx.HTTPError as e:
        return False, None, f"HTTP error: {str(e)}"

    except Exception as e:
        return False, None, f"Unexpected error: {str(e)}"




async def check_target(
    target_type: str,
    address: str,
    timeout: int,
    snmp_config: Dict[str, Any] = None,
    ping_config: Dict[str, Any] = None
) -> Tuple[bool, Optional[float], Optional[str], Optional[Any]]:
    """
    Check a target based on its type.

    Args:
        target_type: Type of check ('ping', 'http', 'https')
        address: Address to check
        timeout: Timeout in seconds
        snmp_config: Deprecated (kept for compatibility)
        ping_config: Ping configuration dict (for ping targets)
            - packet_count: Number of packets to send (default: 3)
            - min_success: Minimum successful packets required (default: 1)

    Returns:
        Tuple of (success, response_time, error_message, extra_data)
    """
    if target_type == 'ping':
        # Extract ping config with defaults
        ping_config = ping_config or {}
        packet_count = ping_config.get('packet_count', 3)
        min_success = ping_config.get('min_success', 1)

        success, response_time, error = await check_ping(
            address, timeout, packet_count, min_success
        )
        return success, response_time, error, None
    elif target_type in ['http', 'https']:
        # Construct full URL with protocol
        url = f"{target_type}://{address}" if not address.startswith(('http://', 'https://')) else address
        success, response_time, error = await check_http(url, timeout)
        return success, response_time, error, None
    else:
        return False, None, f"Unknown target type: {target_type}", None
