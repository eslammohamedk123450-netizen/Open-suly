"""Fail-closed URL preflight policy for a future isolated browser runtime.

This validates destinations but does not make network requests or replace an
egress proxy. The runtime must repeat validation for every redirect and pin
the resolved addresses at connection time to prevent DNS rebinding.
"""
from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import socket
from typing import Callable, Iterable
from urllib.parse import urlsplit

AddressResolver = Callable[[str, int], Iterable[str]]


def _resolve_addresses(host: str, port: int) -> tuple[str, ...]:
    try:
        results = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError('browser_target_dns_resolution_failed') from exc
    return tuple({item[4][0] for item in results})


@dataclass(frozen=True)
class ValidatedBrowserTarget:
    url: str
    hostname: str
    port: int
    addresses: tuple[str, ...]


@dataclass(frozen=True)
class BrowserNetworkPolicy:
    """A task-specific destination allowlist plus public-address preflight."""

    allowed_hosts: frozenset[str]
    allowed_ports: frozenset[int] = frozenset({80, 443})
    allow_subdomains: bool = False
    resolver: AddressResolver = _resolve_addresses

    def __post_init__(self) -> None:
        if (
            not isinstance(self.allowed_hosts, frozenset)
            or not self.allowed_hosts
            or any(
                not isinstance(host, str)
                or not host
                or host != host.lower()
                or host.startswith('.')
                or host.endswith('.')
                or '/' in host
                or ':' in host
                or '@' in host
                for host in self.allowed_hosts
            )
        ):
            raise ValueError('browser_allowed_hosts_required')
        if (
            not isinstance(self.allowed_ports, frozenset)
            or not self.allowed_ports
            or any(isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535 for port in self.allowed_ports)
        ):
            raise ValueError('browser_allowed_ports_invalid')
        if not isinstance(self.allow_subdomains, bool) or not callable(self.resolver):
            raise ValueError('browser_network_policy_invalid')

    def validate(self, url: str) -> ValidatedBrowserTarget:
        """Validate one navigation target; call again for each redirect."""
        if not isinstance(url, str) or not url or len(url) > 4096 or any(ord(ch) < 32 for ch in url):
            raise ValueError('browser_url_invalid')
        try:
            parsed = urlsplit(url)
            host = parsed.hostname
            port = parsed.port
        except ValueError as exc:
            raise ValueError('browser_url_invalid') from exc
        if (
            parsed.scheme.lower() not in {'http', 'https'}
            or not host
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError('browser_url_scheme_or_authority_invalid')
        try:
            hostname = host.encode('idna').decode('ascii').lower().rstrip('.')
        except UnicodeError as exc:
            raise ValueError('browser_url_hostname_invalid') from exc
        if not hostname or hostname == 'localhost' or hostname.endswith('.localhost') or hostname.endswith('.local') or hostname.endswith('.internal'):
            raise ValueError('browser_url_private_hostname_rejected')
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            pass
        else:
            raise ValueError('browser_url_ip_literal_rejected')
        if hostname not in self.allowed_hosts and not (
            self.allow_subdomains and any(hostname.endswith('.' + allowed) for allowed in self.allowed_hosts)
        ):
            raise ValueError('browser_url_host_not_allowlisted')
        target_port = port or (443 if parsed.scheme.lower() == 'https' else 80)
        if target_port not in self.allowed_ports:
            raise ValueError('browser_url_port_not_allowlisted')
        addresses = tuple(dict.fromkeys(self.resolver(hostname, target_port)))
        if not addresses:
            raise ValueError('browser_target_dns_resolution_empty')
        for address in addresses:
            try:
                parsed_address = ipaddress.ip_address(address)
            except ValueError as exc:
                raise ValueError('browser_target_dns_address_invalid') from exc
            if not parsed_address.is_global:
                raise ValueError('browser_target_private_address_rejected')
        return ValidatedBrowserTarget(
            url=url,
            hostname=hostname,
            port=target_port,
            addresses=addresses,
        )