# harmflow-site

The source of the product website of [HarmFlow](https://github.com/harmflow), the local-first desktop app that
schedules, runs, and monitors automations through the agent harnesses already on your machine — Claude Code and Codex.
The site will be published at `harmflow.com`.

> [!NOTE]
> **Under construction.** `harmflow.com` serves a placeholder page for now. The first pages are open
> [issues](https://github.com/harmflow/harmflow-site/issues) in this repository; [`docs/site.md`](docs/site.md) says
> what the site will be.

## What it holds

| Path | What it is |
|---|---|
| [`site/`](site/) | The site itself, as GitHub Pages serves it: only this folder is published |
| [`.github/workflows/pages.yml`](.github/workflows/pages.yml) | Packages `site/` on every pull request and deploys it to GitHub Pages on every push to `main` |
| [`docs/site.md`](docs/site.md) | What the site will be: static pages with no build step, in English for now, nothing from another host |
| [`CLAUDE.md`](CLAUDE.md) | Guidance for coding agents that work in this repository |
| [`.github/scripts/`](.github/scripts/) | The site's checks and their tests |

## Checks

Every pull request and every push to `main` runs the site's checks, which read the files as committed. A check fails
when:

- **Languages.** A page sits under `/pt-br/` or `/es-es/`: the site is in English for now, and those prefixes are kept
  for its translations. `--languages en-US,pt-BR,es-ES` publishes them again, and then a page with no version at the
  same English slug in another published language fails too; the root `404.html` is the one exception.
- **Shared blocks.** A page's header or footer differs from the other pages of its language. Whitespace does not
  count, and once the site is translated, neither do a language selector's links to the same page in the other
  languages, which differ on every page by design; every other part of the markup must be the same.
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
