# The site

> [!NOTE]
> This page describes what the site will be. What the repository is, what it holds, and where its work is tracked are
> in the [`README.md`](/README.md) at the root.

## What the site will be

- **Static pages, no build step.** Plain HTML and CSS served by GitHub Pages from the `site/` folder, as committed:
  `site/index.html` is `harmflow.com/`. Every page's content and navigation work with JavaScript disabled.
- **Three languages.** en-US at the root, pt-BR under `/pt-br/`, and es-ES under `/es-es/`, with the same English slugs
  in each. A selector in every page's header leads to the same page in the other two.
- **Nothing from another host.** No third-party script, stylesheet, font, or image: the fonts are served from the site
  itself.
- **First pages.** The landing page, the privacy policy, and the support page, each an open
  [issue](https://github.com/harmflow/harmflow-site/issues) in this repository.

## The page skeleton

Every page is one `index.html` per language, at the same English slug in each tree: `site/privacy/index.html`,
`site/pt-br/privacy/index.html`, and `site/es-es/privacy/index.html` are `/privacy/`, `/pt-br/privacy/`, and
`/es-es/privacy/`. Each language's home is `/`, `/pt-br/`, or `/es-es/`, an under-construction notice until the
landing page replaces it. The sections are `/docs/guide/`, `/docs/reference/`, `/showroom/`, `/privacy/`, and
`/support/`, each a stub until its page is written.

A new page copies a page of the same language and changes only its `<title>`, its `<main>`, and the two links of its
language selector, in the three languages together:

- **Header and footer.** The same markup on every page of one language; only the language selector's links differ.
  The logo leads to the language's home.
  Every link is an absolute path (`/pt-br/support/`), so it reads the same from every page.
- **Language selector.** Names the page's own language without a link, and links to the same page in the other two.
  It is plain links, so it works with JavaScript disabled.
- **Language.** `<html lang>` is `en-US`, `pt-BR`, or `es-ES`.
- **Styles.** `site/styles/site.css`, shared by every page. The logo is `site/app-icon-small.svg` below 64 px and
  `site/app-icon.svg` above, in its fixed colors; every other color is a placeholder until the palette is approved.
- **Footer.** Its last item is where the link to the analytics consent choice goes.
