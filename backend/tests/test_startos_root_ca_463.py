"""
The StartOS package takes this server's root CA from sdk.getRootCa, never by
indexing a serving certificate's chain (#463). Start9's guide,
service-to-service.md, "Trusting this server's certificates": "Do not reach
for the root by indexing `sdk.getSslCertificate`": getSslCertificate is for
serving a certificate, getRootCa for trusting one. The old way took the
third certificate of the chain, which worked only while it had exactly
three. The package README, which Start9's support agent reads, says the same.
"""

import re
from pathlib import Path

PKG = Path(__file__).resolve().parents[2] / "startos"
CODE = PKG / "startos"

# A call, not a mention: a comment may name it.
CHAIN_CALL = re.compile(r"getSslCertificate\s*\(")


def package_code():
    return {p: p.read_text() for p in sorted(CODE.rglob("*.ts"))}


def test_connect_ai_takes_the_root_ca_from_get_root_ca():
    action = (CODE / "actions" / "connectAi.ts").read_text()
    assert "sdk.getRootCa(effects)" in action


def test_no_package_code_reads_a_certificate_chain():
    # The package serves no certificate of its own (StartOS terminates TLS),
    # so a getSslCertificate call anywhere is a root CA taken the wrong way.
    callers = [str(p.relative_to(CODE)) for p, text in package_code().items()
               if CHAIN_CALL.search(text)]
    assert callers == []


def test_the_readme_names_get_root_ca():
    readme = (PKG / "README.md").read_text()
    assert "sdk.getRootCa" in readme
    assert "getSslCertificate" not in readme
