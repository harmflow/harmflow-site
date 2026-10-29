# harmflow-site

The source of the product website of [HarmFlow](https://github.com/harmflow), the local-first desktop app that
schedules, runs, and monitors automations through the agent harnesses already on your machine — Claude Code and Codex.
The site is published at [`harmflow.com`](https://harmflow.com).

> [!NOTE]
> **Under construction.** `harmflow.com` serves a placeholder page for now. The first pages are open
> [issues](https://github.com/harmflow/harmflow-site/issues) in this repository; [`docs/site.md`](docs/site.md) says
> what the site will be.

## What it holds

| Path | What it is |
|---|---|
| [`site/`](site/) | The site itself, as GitHub Pages serves it: only this folder is published |
| [`.github/workflows/pages.yml`](.github/workflows/pages.yml) | Packages `site/` on every pull request and deploys it to GitHub Pages on every push to `main` |
| [`docs/site.md`](docs/site.md) | What the site will be: static pages with no build step, three languages, nothing from another host |
| [`CLAUDE.md`](CLAUDE.md) | Guidance for coding agents that work in this repository |
| [`.github/scripts/`](.github/scripts/) | The site's checks and their tests |
| [`scripts/dns-cutover-wizard.sh`](scripts/dns-cutover-wizard.sh) | Walks the domain's owner through pointing `harmflow.com` at GitHub Pages at GoDaddy and enforcing HTTPS, checking each record; safe to re-run |

## Checks

Every pull request and every push to `main` runs the site's checks, which read the files as committed. A check fails
when:

- **Parity.** A page has no version at the same English slug in one of the other two languages. The root `404.html`,
  a single page written in all three, is the one exception.
- **Shared blocks.** A page's header or footer differs from the other pages of its language. Whitespace does not
  count, and neither do the language selector's links to the same page in the other two languages, which differ on
  every page by design; every other part of the markup must be the same.
- **Links.** A link, image, or other reference into the site leads to no file, or its `#anchor` to no `id` of its
  page. A reference to `harmflow.com` is one into the site; one to another host is not checked.
- **Media budget.** A media file is over 10 MB, or all of them together are over 300 MB (1 MB is 1,000,000 bytes).
- **Secrets.** [gitleaks](https://github.com/gitleaks/gitleaks) finds a secret or a credential in the tree.

Each check has its tests, which build a tree that breaks it and expect it to fail. Run them with the standard
library's Python 3.9 or later, which a Mac has:

```bash
python3 .github/scripts/check-site.py site       # the checks, on site/, the folder GitHub Pages serves
python3 .github/scripts/check-site-test.py       # their tests
gitleaks dir . --redact --no-banner              # the secret scan, with gitleaks installed
python3 .github/scripts/scan-secrets-test.py     # its test, skipped without gitleaks
```

## Where the work is tracked

Every page and every check is an [issue](https://github.com/harmflow/harmflow-site/issues) of this repository, and
lands through a pull request.

## Part of HarmFlow

- **The app** — [`harmflow-app`](https://github.com/harmflow/harmflow-app): the daemon, the desktop, and the
  installers.
- **Product overview** — the [HarmFlow organization](https://github.com/harmflow) page.
- **Ask or report a bug** — [open an issue](https://github.com/harmflow/harmflow-site/issues) here; a vulnerability
  goes privately through the [security policy](https://github.com/harmflow/.github/blob/main/SECURITY.md), never in a
  public issue.
- **Contribute** — pull requests are open to authorized collaborators only for now; see the
  [contribution guide](https://github.com/harmflow/.github/blob/main/CONTRIBUTING.md).
