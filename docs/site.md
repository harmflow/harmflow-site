# The site

> [!NOTE]
> This page describes what the site will be. What the repository is, what it holds, and where its work is tracked are
> in the [`README.md`](/README.md) at the root.

## What the site will be

- **Static pages, no build step.** Plain HTML and CSS served by GitHub Pages. Every page's content and navigation work
  with JavaScript disabled.
- **Three languages.** en-US at the root, pt-BR under `/pt-br/`, and es-ES under `/es-es/`, with the same English slugs
  in each. A selector in every page's header leads to the same page in the other two.
- **Nothing from another host.** No third-party script, stylesheet, font, or image: the fonts are served from the site
  itself.
- **First pages.** The layout every page copies, the landing page, the privacy policy, and the support page, each an
  open [issue](https://github.com/harmflow/harmflow-site/issues) in this repository.
