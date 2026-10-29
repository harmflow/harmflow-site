#!/usr/bin/env python3
"""Tests of the secret scan the Checks workflow (.github/workflows/checks.yml) runs over the tree,
`gitleaks dir ROOT --redact --no-banner`, which installs gitleaks before it runs this test: a tree with no secret
passes, and the same tree with a private key in one of its pages fails, without printing the key. The key is made
here, in a temporary directory, and never committed: a committed one would fail the scan of the repository itself.

Without gitleaks on the PATH, it fails in CI and is skipped elsewhere, saying so.

Usage: scan-secrets-test.py [unittest options]
"""

import os
import shutil
import subprocess
import tempfile
import unittest

# The workflow's command, with the tree to scan after "dir".
SCAN = ["gitleaks", "dir", None, "--redact", "--no-banner"]

PAGE = '<!doctype html>\n<html lang="en-US">\n<body>%s</body>\n</html>\n'


def gitleaks_missing():
    return shutil.which("gitleaks") is None


@unittest.skipIf(
    gitleaks_missing() and not os.environ.get("CI"),
    "gitleaks is not on the PATH (CI installs it before this test)",
)
class SecretScanTest(unittest.TestCase):
    def setUp(self):
        self.assertFalse(gitleaks_missing(), "gitleaks is not on the PATH")
        scratch = tempfile.mkdtemp(prefix="scan-secrets-test.")
        self.addCleanup(shutil.rmtree, scratch)
        self.scratch = scratch
        self.root = os.path.join(scratch, "site")
        self.write("privacy/index.html", PAGE % "<p>No secret here.</p>")

    def write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def scan(self):
        command = [self.root if arg is None else arg for arg in SCAN]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        return result.returncode, result.stdout

    def test_a_tree_with_no_secret_passes(self):
        rc, out = self.scan()
        self.assertEqual(rc, 0, out)
        self.assertIn("no leaks found", out)

    def test_a_private_key_in_a_page_fails_without_printing_it(self):
        key = os.path.join(self.scratch, "key.pem")
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", key],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        with open(key, encoding="ascii") as f:
            pem = f.read()
        self.write("index.html", PAGE % ("<pre>\n%s</pre>" % pem))
        rc, out = self.scan()
        self.assertEqual(rc, 1, out)
        self.assertRegex(out, r"leaks found: [1-9]")
        body = pem.splitlines()[1]
        self.assertNotIn(body, out)


if __name__ == "__main__":
    unittest.main()
