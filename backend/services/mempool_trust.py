"""
Trusting a home server's own certificate for the owner's Mempool (#188).

A StartOS server's https:// home-network address has a certificate from
that server's own authority ("<name> Local Root CA"), which no public trust
store knows (and macOS rejects its Ed25519 certificates outright), so
BitcoinTX can't use that Mempool. The owner may trust that server's root
certificate for that one Mempool address: its requests are then checked
against that root, and only it (outbound.own_node_client). It is offered
only for a home-network address, so it can't become a way around a real
certificate problem, and never applies to public price sites.

Login only, never the AI key (routers/settings.py); stored with the price
settings (outbound.TRUSTED_ROOT_KEY), kept across a restore like them.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import ssl
from dataclasses import dataclass
from urllib.parse import urlparse

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.x509.oid import NameOID
from fastapi import HTTPException

from backend.services import outbound

TIMEOUT = 10.0
# Home-network names and addresses (RFC 6762 .local, .lan, RFC 1918), and a
# one-word name (no dot): what a home server answers to
PRIVATE_SUFFIXES = (".local", ".lan")
PRIVATE_NETWORKS = tuple(ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
ONLY_PRIVATE = ("Only a home-network https address can be trusted this way: a .local or .lan name, "
                "a one-word name, or 10.x, 172.16–31.x or 192.168.x.")


@dataclass(frozen=True)
class Root:
    """A root certificate: PEM, its name, its SHA-256 fingerprint ("AB:CD:…")."""
    pem: str
    name: str
    sha256: str


def private_address(url: str | None) -> bool:
    """
    Whether a Mempool address is an https home-network one (the only kind
    offered). Judged on the host the connection will use: plain ASCII, the
    same for urlparse and httpx (no Unicode dots: "evil。com" connects to
    evil.com), and a number the resolver reads as an IPv4 address
    ("134744072", "0x08080808" are 8.8.8.8) is that address, not a name.
    """
    parsed = urlparse(url or "")
    host = (parsed.hostname or "").rstrip(".").lower()
    if parsed.scheme != "https" or not host or not host.isascii():
        return False
    if (outbound.connection_host(url) or "").rstrip(".").lower() != host:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        if "." in host:
            return host.endswith(PRIVATE_SUFFIXES)
        try:  # a one-word name, unless the resolver takes it for an address
            ip = ipaddress.ip_address(socket.inet_aton(host))
        except OSError:
            return True
    return any(ip in network for network in PRIVATE_NETWORKS)


def root_of(pem: str) -> Root:
    cert = x509.load_pem_x509_certificate(pem.encode())
    names = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    name = str(names[0].value) if names else cert.subject.rfc4514_string()
    return Root(pem=pem, name=name, sha256=cert.fingerprint(hashes.SHA256()).hex(":").upper())


def _host_port(url: str) -> tuple[str, int]:
    parsed = urlparse(url)
    return parsed.hostname or "", parsed.port or 443


async def _handshake(url: str, context: ssl.SSLContext) -> list[bytes]:
    host, port = _host_port(url)
    return await asyncio.wait_for(outbound.own_node_certificates(host, port, context), TIMEOUT)


async def shown_root(url: str) -> Root:
    """
    The root certificate the Mempool shows (the last of its chain), checked
    to be a root (a self-issued authority), and that the Mempool's
    certificate is valid for its address under it.
    """
    unchecked = ssl.create_default_context()
    unchecked.check_hostname, unchecked.verify_mode = False, ssl.CERT_NONE
    try:
        chain = await _handshake(url, unchecked)
    except (OSError, asyncio.TimeoutError, ssl.SSLError) as exc:
        raise HTTPException(status_code=502, detail=f"Your Mempool at {_host_port(url)[0]} didn't answer.") from exc
    last = x509.load_der_x509_certificate(chain[-1]) if chain else None
    if last is None or last.issuer != last.subject or not _is_authority(last):
        raise HTTPException(status_code=422, detail=(
            "This server doesn't show its root certificate, so it can't be trusted here."))
    root = root_of(ssl.DER_cert_to_PEM_cert(chain[-1]))
    try:
        await _handshake(url, outbound.trusting(root.pem))
    except ssl.SSLError as exc:
        raise HTTPException(status_code=422, detail=(
            f"Even with its root certificate, the Mempool's certificate isn't valid for "
            f"{_host_port(url)[0]}, so it can't be trusted.")) from exc
    except (OSError, asyncio.TimeoutError) as exc:
        raise HTTPException(status_code=502, detail=f"Your Mempool at {_host_port(url)[0]} didn't answer.") from exc
    return root


def _is_authority(cert: x509.Certificate) -> bool:
    try:
        return bool(cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca)
    except x509.ExtensionNotFound:
        return False


async def offer(url: str | None) -> dict:
    """What the card shows before the owner trusts: the server and its root."""
    if not private_address(url):
        raise HTTPException(status_code=422, detail=ONLY_PRIVATE)
    root = await shown_root(url)
    return {"server": _host_port(url)[0], "name": root.name, "sha256": root.sha256}


async def trusted(url: str | None, sha256: str) -> Root:
    """The root to keep: the one the owner was shown, still the server's."""
    if not private_address(url):
        raise HTTPException(status_code=422, detail=ONLY_PRIVATE)
    root = await shown_root(url)
    if root.sha256 != sha256.strip().upper():
        raise HTTPException(status_code=409, detail=(
            "The server's certificate changed since it was shown: look at it again before trusting it."))
    return root
