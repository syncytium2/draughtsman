#!/usr/bin/env python3
"""Does the published site actually answer, and on HTTPS?

    tools/site_check.py                 # check the domain in ./CNAME
    tools/site_check.py --repo syncytium2/draughtsman
    tools/site_check.py --selftest

WHY THIS EXISTS. `draughtsman.tonydefazio.com` served plain HTTP for weeks with
no certificate at all. Port 443 answered with GitHub's `*.github.io` wildcard,
which does not cover the host, so every browser refused the connection. Nothing
here noticed. `tests/test_readme_links.py` checks that the README's links
resolve; the site's own scheme had never been asked about by anything, and it was
found by a person opening it in a browser.

WHY A TOOL AND NOT A TEST. This config cannot be reconciled by storing it, which
is the usual remedy in this repository. It lives in four places and only one of
them is a file:

    DNS record -> syncytium2.github.io    at the registrar. Not representable here.
    the custom domain                     `CNAME` AND the Pages settings.
    https_enforced                        Pages settings ONLY. No file can hold it.
    the certificate                       GitHub's to issue. Observable, not settable.

So the only available check is to ASK THE LIVE SITE, and that is a network call.
In a suite where `DRAUGHTSMAN_NO_SKIPS` turns a skip into a failure, a
network-dependent test goes red on GitHub's outage rather than on our defect —
and a check that cries wolf is a check that gets switched off. This runs on
demand, by whoever deploys.

WHAT IT WOULD HAVE CAUGHT, and the order matters: a 200 over HTTP proves nothing.
The site was serving 200 over HTTP the entire time it was broken.
"""

from __future__ import annotations

import argparse
import json
import socket
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TIMEOUT = 20


class Result:
    def __init__(self) -> None:
        self.checks: list[tuple[bool, str]] = []

    def add(self, ok: bool, msg: str) -> None:
        self.checks.append((bool(ok), msg))

    @property
    def ok(self) -> bool:
        return all(ok for ok, _ in self.checks)

    def report(self) -> str:
        return "\n".join(f"  {'ok  ' if ok else 'FAIL'}  {m}" for ok, m in self.checks)


def cert_names(host: str, port: int = 443) -> tuple[set[str], str | None, str | None]:
    """The names the served certificate covers: (names, subject, error).

    VERIFICATION MUST BE ON, and not only because it is the real question.
    `getpeercert()` returns an EMPTY DICT when `verify_mode` is `CERT_NONE` —
    Python only populates it for a verified peer. A first draft of this file
    turned verification off in order to "look at" the certificate and therefore
    reported `SAN=none` for a certificate that was correct, which is a checker
    reporting a defect it invented. So the handshake is done exactly as a browser
    does it, and the failure text is what gets reported.

    THE WILDCARD IS THE TRAP THIS ANSWERS. GitHub answers 443 for an
    unprovisioned custom domain with its own `*.github.io` certificate, so the
    TRANSPORT connects and only the name check fails. Anything that merely opened
    a socket would have passed all through the outage.
    """
    ctx = ssl.create_default_context()          # verify + check_hostname, as a browser
    try:
        with socket.create_connection((host, port), timeout=TIMEOUT) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as tls:
                cert = tls.getpeercert() or {}
    except ssl.SSLCertVerificationError as e:
        return set(), None, str(e)
    names = {v for k, v in cert.get("subjectAltName", ()) if k == "DNS"}
    subject = None
    for rdn in cert.get("subject", ()):
        for k, v in rdn:
            if k == "commonName":
                subject = v
    return names, subject, None


def covers(names: set[str], host: str) -> bool:
    if host in names:
        return True
    parent = host.split(".", 1)[1] if "." in host else host
    return f"*.{parent}" in names


def _head(url: str) -> tuple[int, str | None]:
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    op = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(url, method="GET")
    try:
        with op.open(req, timeout=TIMEOUT) as r:
            return r.status, r.headers.get("Location")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Location")


def check_site(host: str, repo: str | None = None) -> Result:
    r = Result()

    try:
        code, loc = _head(f"http://{host}/")
        redirects = code in (301, 302, 307, 308) and (loc or "").startswith("https://")
        r.add(redirects,
              f"http://{host}/ -> {code}"
              + (f" {loc}" if loc else "")
              + ("" if redirects else "   [a 200 here is the defect, not a pass:"
                                       " the site served 200 over HTTP the whole"
                                       " time it was broken]"))
    except Exception as e:
        r.add(False, f"http://{host}/ did not answer: {type(e).__name__}: {e}")

    try:
        names, subject, err = cert_names(host)
        if err:
            r.add(False, f"certificate does NOT cover {host}: {err}")
        else:
            r.add(covers(names, host),
                  f"certificate covers {host}"
                  f"   subject={subject}  SAN={sorted(names)}")
    except Exception as e:
        r.add(False, f"no TLS handshake with {host}: {type(e).__name__}: {e}")

    try:
        code, _ = _head(f"https://{host}/")
        r.add(code == 200, f"https://{host}/ -> {code}")
    except Exception as e:
        r.add(False, f"https://{host}/ did not answer: {type(e).__name__}: {e}")

    if repo:
        try:
            out = subprocess.run(["gh", "api", f"repos/{repo}/pages"],
                                 capture_output=True, text=True, timeout=TIMEOUT)
            if out.returncode != 0:
                r.add(False, f"gh api repos/{repo}/pages failed: {out.stderr.strip()[:80]}")
            else:
                d = json.loads(out.stdout)
                r.add(d.get("https_enforced") is True,
                      f"Pages https_enforced={d.get('https_enforced')}")
                state = (d.get("https_certificate") or {}).get("state")
                r.add(state == "approved",
                      f"Pages certificate state={state or 'NONE'}"
                      + ("" if state else "   [GitHub never requested one — set the"
                                          " domain in Pages settings, not by"
                                          " committing CNAME]"))
                r.add(d.get("cname") == host,
                      f"Pages cname={d.get('cname')} matches CNAME file")
        except Exception as e:
            r.add(False, f"could not read Pages settings: {type(e).__name__}: {e}")
    return r


def selftest() -> int:
    """The name check must REJECT the wildcard that was actually served.

    This is the whole point of the tool, so it is the case the selftest pins: an
    unprovisioned GitHub Pages domain gets `*.github.io`, and `*.github.io` must
    not be read as covering `draughtsman.tonydefazio.com`.
    """
    served = {"*.github.com", "*.github.io", "*.githubusercontent.com",
              "github.com", "github.io", "githubusercontent.com"}
    assert not covers(served, "draughtsman.tonydefazio.com"), (
        "the wildcard GitHub serves for an unprovisioned domain was read as "
        "covering it — this tool would have passed all through the outage")
    assert covers({"draughtsman.tonydefazio.com"}, "draughtsman.tonydefazio.com")
    assert covers({"*.tonydefazio.com"}, "draughtsman.tonydefazio.com"), (
        "a real wildcard for the parent domain does cover the host and must pass")
    assert not covers({"*.tonydefazio.com"}, "a.b.tonydefazio.com"), (
        "a wildcard matches one label, not two")
    assert not covers(set(), "draughtsman.tonydefazio.com")

    r = Result()
    r.add(True, "x")
    assert r.ok
    r.add(False, "y")
    assert not r.ok, "a failed check must make the whole result fail"

    print("selftest OK — the served *.github.io wildcard is rejected, a real "
          "wildcard for the parent is accepted, one label only, failures stick")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("host", nargs="?", help="defaults to the domain in ./CNAME")
    ap.add_argument("--repo", help="owner/name, to also read the Pages settings")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv[1:])
    if a.selftest:
        return selftest()
    host = a.host
    if not host:
        cname = ROOT / "CNAME"
        if not cname.exists():
            print("no host given and no CNAME file", file=sys.stderr)
            return 2
        host = cname.read_text().strip()
    r = check_site(host, a.repo)
    print(f"{host}\n{r.report()}")
    print("\nOK" if r.ok else "\nFAILED")
    return 0 if r.ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
