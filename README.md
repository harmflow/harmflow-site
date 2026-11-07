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
| [`docs/site.md`](docs/site.md) | What the site will be: static pages with no build step, in English for now, nothing from another host before the visitor accepts analytics |
| [`CLAUDE.md`](CLAUDE.md) | Guidance for coding agents that work in this repository |
| [`.github/scripts/`](.github/scripts/) | The site's checks and their tests |
| [`scripts/dns-cutover-wizard.sh`](scripts/dns-cutover-wizard.sh) | Walks the domain's owner through pointing `harmflow.com` at GitHub Pages at GoDaddy and enforcing HTTPS, checking each record; safe to re-run |

## Run it locally

The site has no build step: serve `site/` with the standard library's Python and open
[`http://localhost:8000`](http://localhost:8000).

```bash
python3 -m http.server 8000 --directory site
```

This server answers a missing page with its own error, not the site's `404.html`; open
[`http://localhost:8000/404.html`](http://localhost:8000/404.html) to see that page.

## Checks

Every pull request and every push to `main` runs the site's checks, which read the files as committed. A check fails
when:

- **Languages.** A page sits under `/pt-br/` or `/es-es/`: the site is in English for now, and those prefixes are kept
  for its translations. `--languages en-US,pt-BR,es-ES` publishes them again, and then a page with no version at the
  same English slug in another published language fails too; the root `404.html` is the one exception. A page whose
  root element declares no language, or one other than its prefix's — en-US at the root, `404.html` included — fails,
  and so does an element inside a page marked with the `lang` of a language the site does not publish.
- **Paths.** The home page at `/`, or one of the five sections at `/docs/guide/`, `/docs/reference/`, `/showroom/`,
  `/privacy/`, and `/support/`, has no page of its own in en-US: removed, or moved to another slug, even with its links
  and its sitemap entry.
- **Shared blocks.** A page's header or footer differs from the other pages of its language. Whitespace does not
  count, and once the site is translated, neither do a language selector's links to the same page in the other
  languages, which differ on every page by design; every other part of the markup must be the same.
- **Lockup.** A page's header, the 404 page's included, has no `<img>` of `/lockup.svg`, the wordmark's lockup, or
  its `alt` is not `HarmFlow`; or a copy of the wordmark under `site/` (`lockup.svg`, `wordmark*.svg`) holds a
  `<text>` element, a `font-family`, or an `@font-face`, where its master in harmflow-app draws the name as outlines.
  The copy is the master byte for byte, as committed in harmflow-app's `desktop/src-tauri/icons/source/`.
- **Links.** A link, image, or other reference into the site leads to no file, or its `#anchor` to no `id` of its
  page. A reference to `harmflow.com` is one into the site; one to another host is not checked.
- **Media budget.** A media file is over 10 MB, or all of them together are over 300 MB (1 MB is 1,000,000 bytes).
- **Posters.** A page's `<video>` has no `poster`, an empty one, or one that is not an image file by its extension. A
  poster that names no file of the site is the links check's failure.
- **Metadata.** A page other than `404.html` lacks its canonical address, its description, or an Open Graph tag;
  its `og:url` is not its canonical address, or its `og:image` is no image of the site; `sitemap.xml` misses a page or
  lists one the site does not hold; or `robots.txt` does not point to the sitemap.
- **Landing page.** `index.html` has no primary call to action (an `a.cta`), or one leads anywhere but
  harmflow-app on GitHub; its link to the community edition's build instructions is missing, comes before the first
  call to action, or is one; its body does not say that HarmFlow is coming to the Mac App Store; or it links to the
  Mac App Store, where HarmFlow has no page yet.
- **Privacy policy and support page.** In each published language: the privacy policy lacks the heading of one of its
  five parts, found by its `id` (`app`, `website`, `analytics`, `google`, `withdraw`), or a part has no text after its
  heading, or the policy does not name Google Analytics; the support page has no link to harmflow-app's issues, or
  gives an e-mail address, by a `mailto:` link or in its text. Only the support page is read for an address.
- **Typefaces.** An `@font-face` rule takes a font from another host, from a file that is not a `.woff2` file under
  `/fonts/` with `format("woff2")` and the WOFF2 signature, or from no file at all; a family's folder under
  `site/fonts/` has no `LICENSE` with the SIL Open Font License 1.1; or `--font-text` or `--font-mono` loses the
  system's fonts or its generic family. In the browser, on every page and the 404 page, Inter or JetBrains Mono does
  not load, or is fetched from anywhere but `/fonts/` on the site itself as a `.woff2` file that answers 200.
- **Colors.** A stylesheet under `styles/`, a `<style>` element, or a `style` attribute uses a color — hex, `rgb()`,
  `hsl()`, or a named color — that is neither one of the logo's fixed colors (`#22d3ee`, `#8b5cf6`, `#e040fb`) nor a
  placeholder, at any opacity. The placeholders are the custom properties of `site.css`'s `:root` block, which stand
  in until the palette is approved: a new color joins them there.
- **Consent and analytics.** In a headless browser, over every page and the 404 page: with no choice made, or after
  Reject, a page requests anything from another host or sets an analytics cookie; the banner's Accept and Reject differ
  in style, or the banner shows again after a choice; after Accept, the page asks Google's tag to send anything but the
  page view, the click on the landing page's call to action, and the 404 page's visit, or leaves Google signals or ad
  personalization on; after withdrawing through the footer's link, an event is still sent or an analytics cookie
  remains; with JavaScript disabled, a page's content or a link into the site breaks; a page loads or holds a script
  other than the consent's — another file, an inline script, an inline event handler, or a `javascript:` URL — or,
  after Accept, any but Google's tag; a page's main content reads otherwise without JavaScript than with it after
  Reject; or, with JavaScript disabled, a page cannot be reached from every page, the 404 page included, by following
  the site's links. Google's tag is answered with a stand-in, so no request leaves the machine and no Analytics
  property is needed.
- **Task file samples.** A sample of the technical reference is not YAML, or the app's task schema rejects it. A
  sample is a `<pre><code>` block of a page under `docs/reference/` whose text starts with
  `apiVersion: harmflow/v1alpha1`, found by its text, so a new one is checked too. Each is validated against
  `contracts/schemas/task.schema.json` at the commit of harmflow-app that the page's link to the schema pins, fetched by
  its full SHA; a page with samples whose link pins no full SHA fails as well. A failure names the page, the sample by
  its order and the heading above it, and the schema's first error with its path in the document.
- **Secrets.** [gitleaks](https://github.com/gitleaks/gitleaks) finds a secret or a credential in the tree.

Each check has its tests, which build a tree that breaks it and expect it to fail. Run them with the standard
library's Python 3.9 or later, which a Mac has:

```bash
python3 .github/scripts/check-site.py site       # the checks, on site/, the folder GitHub Pages serves
python3 .github/scripts/check-site-test.py       # their tests
gitleaks dir . --redact --no-banner              # the secret scan, with gitleaks installed
python3 .github/scripts/scan-secrets-test.py     # its test, skipped without gitleaks
```

The consent check needs [Playwright](https://playwright.dev/python/) for Python and its Chromium, which CI installs in
a virtual environment of its own. Keep yours outside the clone, where the secret scan does not read it:

```bash
python3 -m venv ~/.venvs/harmflow-site && ~/.venvs/harmflow-site/bin/pip install playwright==1.64.1
~/.venvs/harmflow-site/bin/python -m playwright install chromium
~/.venvs/harmflow-site/bin/python .github/scripts/check-consent.py site    # the consent check
~/.venvs/harmflow-site/bin/python .github/scripts/check-consent-test.py    # its tests, skipped without Playwright
```

The samples check needs [PyYAML](https://pypi.org/project/PyYAML/) and
[jsonschema](https://pypi.org/project/jsonschema/), which CI installs in a virtual environment of its own as well, at
the versions below. jsonschema 4.25.1 is its last release that runs on Python 3.9. The check fetches the schema from
GitHub; its tests supply their own and need no network:

```bash
~/.venvs/harmflow-site/bin/pip install PyYAML==6.0.3 jsonschema==4.25.1
~/.venvs/harmflow-site/bin/python .github/scripts/check-samples.py site    # the samples check
~/.venvs/harmflow-site/bin/python .github/scripts/check-samples-test.py    # its tests, skipped without the packages
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
