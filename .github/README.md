# harmflow-site

The product website of [HarmFlow](https://github.com/harmflow), the local-first desktop app that schedules, runs, and
monitors automations through the agent harnesses already on your machine — Claude Code and Codex. The site will be
published at `harmflow.com`.

> [!NOTE]
> **No pages yet.** The first pages — the layout every page copies, the landing page, the privacy policy, and the
> support page — are open [issues](https://github.com/harmflow/harmflow-site/issues) in this repository.

## What the site will be

- **Static pages, no build step.** Plain HTML and CSS served by GitHub Pages. Every page's content and navigation work
  with JavaScript disabled.
- **Three languages.** en-US at the root, pt-BR under `/pt-br/`, and es-ES under `/es-es/`, with the same English slugs
  in each. A selector in every page's header leads to the same page in the other two.
- **Nothing from another host.** No third-party script, stylesheet, font, or image: the fonts are served from the site
  itself.

## Part of HarmFlow

- **The app** — [`harmflow-app`](https://github.com/harmflow/harmflow-app): the daemon, the desktop, and the
  installers.
- **Product overview** — the [HarmFlow organization](https://github.com/harmflow) page.
- **Ask or report a bug** — [open an issue](https://github.com/harmflow/harmflow-site/issues) here; a vulnerability
  goes privately through the [security policy](https://github.com/harmflow/.github/blob/main/SECURITY.md), never in a
  public issue.
- **Contribute** — pull requests are open to authorized collaborators only for now; see the
  [contribution guide](https://github.com/harmflow/.github/blob/main/CONTRIBUTING.md).
