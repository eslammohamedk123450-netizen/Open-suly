from __future__ import annotations

import pytest

from app.services.browser_network_policy import BrowserNetworkPolicy


def public_resolver(_host: str, _port: int):
    return ('93.184.216.34',)


def policy(**overrides):
    values = {
        'allowed_hosts': frozenset({'example.com'}),
        'resolver': public_resolver,
    }
    values.update(overrides)
    return BrowserNetworkPolicy(**values)


def test_browser_policy_accepts_allowlisted_public_https_target():
    result = policy().validate('https://example.com/path?q=1')
    assert result.hostname == 'example.com'
    assert result.port == 443
    assert result.addresses == ('93.184.216.34',)


def test_browser_policy_rejects_non_allowlisted_host_and_subdomain_by_default():
    with pytest.raises(ValueError, match='host_not_allowlisted'):
        policy().validate('https://sub.example.com/')


def test_browser_policy_allows_only_explicit_subdomains_when_enabled():
    result = policy(allow_subdomains=True).validate('https://docs.example.com/')
    assert result.hostname == 'docs.example.com'
    with pytest.raises(ValueError, match='host_not_allowlisted'):
        policy(allow_subdomains=True).validate('https://evil-example.com/')


@pytest.mark.parametrize('url', [
    'file:///etc/passwd',
    'ftp://example.com/file',
    'https://user:pass@example.com/',
    'https:///missing-host',
    'https://example.com:8443/',
    'https://example.com:0/',
    'https://example.com\\n.evil/',
    'https://example.com@127.0.0.1/',
])
def test_browser_policy_rejects_unsafe_url_forms(url):
    with pytest.raises(ValueError):
        policy().validate(url)


@pytest.mark.parametrize("url", [
    "https://example.com/path\n.evil",
    "https://example.com/\tpath",
    "https://example.com/\u202e/path",
    "https://example.com/\u200f/path",
])
def test_browser_policy_rejects_unicode_controls_and_bidi_characters(url):
    with pytest.raises(ValueError, match="url_invalid"):
        policy().validate(url)


@pytest.mark.parametrize('url', [
    'http://127.0.0.1/',
    'https://169.254.169.254/latest/meta-data/',
    'http://[::1]/',
    'https://localhost/',
    'https://service.internal/',
    'https://printer.local/',
])
def test_browser_policy_rejects_private_or_ip_literal_hosts(url):
    with pytest.raises(ValueError):
        policy(allowed_hosts=frozenset({'example.com', 'localhost', '169.254.169.254', '127.0.0.1', '::1'})).validate(url)


@pytest.mark.parametrize("host", [
    "127.1",
    "2130706433",
    "0x7f000001",
])
def test_browser_policy_rejects_legacy_numeric_ipv4_host_encodings(host):
    with pytest.raises(ValueError, match="ip_literal"):
        policy().validate(f"https://{host}/")


def test_browser_policy_rejects_private_dns_answers_even_for_allowlisted_host():
    with pytest.raises(ValueError, match='private_address'):
        policy(resolver=lambda *_args: ('10.0.0.5',)).validate('https://example.com/')


def test_browser_policy_rejects_mixed_public_and_private_dns_answers():
    with pytest.raises(ValueError, match='private_address'):
        policy(resolver=lambda *_args: ('93.184.216.34', '192.168.1.10')).validate('https://example.com/')


def test_browser_policy_rejects_empty_or_invalid_dns_answers():
    with pytest.raises(ValueError, match='dns_resolution_empty'):
        policy(resolver=lambda *_args: ()).validate('https://example.com/')
    with pytest.raises(ValueError, match='dns_address_invalid'):
        policy(resolver=lambda *_args: ('not-an-ip',)).validate('https://example.com/')


@pytest.mark.parametrize("host", [
    "Example.com",
    ".example.com",
    "example.com.",
    "bad..example.com",
    "localhost",
    "service.internal",
    "127.0.0.1",
    "2130706433",
])
def test_browser_policy_rejects_noncanonical_or_nonpublic_allowlist_hosts(host):
    with pytest.raises(ValueError):
        BrowserNetworkPolicy(allowed_hosts=frozenset({host}))


def test_browser_policy_requires_nonempty_host_and_port_allowlists():
    with pytest.raises(ValueError, match='allowed_hosts'):
        BrowserNetworkPolicy(allowed_hosts=frozenset())
    with pytest.raises(ValueError, match='allowed_ports'):
        BrowserNetworkPolicy(allowed_hosts=frozenset({'example.com'}), allowed_ports=frozenset())