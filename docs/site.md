# The site

> [!NOTE]
> This page describes what the site will be. What the repository is, what it holds, and where its work is tracked are
> in the [`README.md`](/README.md) at the root.

## What the site will be

- **Static pages, no build step.** Plain HTML and CSS served by GitHub Pages from the `site/` folder, as committed:
  `site/index.html` is `harmflow.com/`. Every page's content and navigation work with JavaScript disabled.
- **English for now.** Every page is in en-US, at the root, with English slugs. pt-BR and es-ES come later, under
  `/pt-br/` and `/es-es/` with the same slugs, and until then no page sits under either prefix.
- **Nothing from another host.** No third-party script, stylesheet, font, or image: the fonts are served from the site
  itself.
- **First pages.** The landing page, the privacy policy, and the support page, each an open
  [issue](https://github.com/harmflow/harmflow-site/issues) in this repository.

## The page skeleton

Every page is one `index.html` at its English slug: `site/privacy/index.html` is `/privacy/`. The home, `/`, is an
under-construction notice until the landing page replaces it. The sections are `/docs/guide/`, `/docs/reference/`,
`/showroom/`, `/privacy/`, and `/support/`, each a stub until its page is written.

A new page copies another page and changes only its `<title>` and its `<main>`:

- **Header and footer.** The same markup on every page. The logo leads to the home. Every link is an absolute path
  (`/support/`), so it reads the same from every page.
- **Header.** Stays at the top as the page scrolls: the logo and the name, the Guide, Reference, and Showroom links in
  the middle, and one call to action, a pill that follows `harmflow-app` on GitHub. On a narrow screen the section
  links drop out, since the footer lists them too.
- **Language.** `<html lang>` is `en-US`.
- **Styles.** `site/styles/site.css`, shared by every page. The logo is `site/app-icon-small.svg` below 64 px and
  `site/app-icon.svg` above, in its fixed colors; every other color is a placeholder until the palette is approved.
  The pages are dark only until then, with no light theme to follow the system's setting.
- **Typefaces.** Inter for text and JetBrains Mono for code, the desktop app's own files, in `site/fonts/` with each
  font's license beside it. A page uses the stacks `--font-text` and `--font-mono` from the stylesheet, never a font
  from another host.
- **Footer.** One sentence on what HarmFlow is, then two columns of links: the sections, and the privacy, support,
  and GitHub links. The last item of that column is where the link to the analytics consent choice goes. Under both
  columns, the copyright with the app's license, and the trademark notes for the harnesses and Apple's names.
