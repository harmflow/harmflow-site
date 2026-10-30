# The site

> [!NOTE]
> This page describes what the site will be. What the repository is, what it holds, and where its work is tracked are
> in the [`README.md`](/README.md) at the root.

## What the site will be

- **Static pages, no build step.** Plain HTML and CSS served by GitHub Pages from the `site/` folder, as committed:
  `site/index.html` is `harmflow.com/`. Every page's content and navigation work with JavaScript disabled. The only
  JavaScript is `site/scripts/consent.js`, for the analytics and its consent.
- **English for now.** Every page is in en-US, at the root, with English slugs. pt-BR and es-ES come later, under
  `/pt-br/` and `/es-es/` with the same slugs, and until then no page sits under either prefix.
- **Nothing from another host before consent.** No third-party stylesheet, font, or image: the fonts are served from
  the site itself. The one script from another host is Google's tag, which a page loads only after the visitor
  accepts analytics.
- **Analytics only after Accept.** On a visitor's first page, a banner asks for consent to Google Analytics 4, with
  Accept and Reject of equal weight, and keeps the choice in the browser's `localStorage`. After Accept, the site
  measures the page views, the clicks on the landing page's primary call to action (`main a.cta`), and the visits to
  the 404 page, and nothing else; the footer's analytics link reopens the choice, and Reject then removes the
  analytics cookies. The property's measurement ID sits only in `site/scripts/consent.js`.
- **Pages.** The landing page at `/`, the privacy policy at `/privacy/`, and the support page at `/support/`. The
  guide, the reference, and the showroom are being written, each an
  [issue](https://github.com/harmflow/harmflow-site/issues) in this repository.

## The page skeleton

Every page is one `index.html` at its English slug: `site/privacy/index.html` is `/privacy/`. The home, `/`, is an
under-construction notice until the landing page replaces it. The sections are `/docs/guide/`, `/docs/reference/`,
`/showroom/`, `/privacy/`, and `/support/`, each a stub until its page is written.

A new page copies another page and changes only its `<title>`, its metadata, and its `<main>`, and gets a line in
`site/sitemap.xml`:

- **Metadata.** Its description, its canonical address (`https://harmflow.com/support/`, with the trailing slash),
  and the Open Graph tags: `og:title` repeats the `<title>`, `og:description` the description, and `og:url` the
  canonical address. Every page shares `og:image`, `site/og-image.png`, 1,200 × 630 pixels.
- **Script.** `<script src="/scripts/consent.js" defer></script>` in its `<head>`, after the stylesheets.
- **404.** `site/404.html` answers every path the site does not hold, at any depth, so its links and assets are
  absolute paths. It has no canonical address, asks search engines not to index it, and is not in the sitemap. Its
  `<body data-page="not-found">` is what the analytics read to measure a visit to it.
- **Header and footer.** The same markup on every page. The logo leads to the home. Every link is an absolute path
  (`/support/`), so it reads the same from every page.
- **Header.** Stays at the top as the page scrolls: the logo and the name, the Guide, Reference, and Showroom links in
  the middle, and one call to action, a pill that follows `harmflow-app` on GitHub. On a narrow screen the section
  links drop out, since the footer lists them too.
- **Language.** `<html lang>` is `en-US`.
- **Styles.** `site/styles/site.css`, shared by every page. The logo is `site/app-icon-small.svg` below 64 px and
  `site/app-icon.svg` above, in its fixed colors; every other color is a placeholder until the palette is approved.
  The pages are dark only until then, with no light theme to follow the system's setting. A page of running text, such
  as the privacy policy, holds its `<main>` in one `<article class="prose">`, a column narrow enough to read.
- **Typefaces.** Inter for text and JetBrains Mono for code, the desktop app's own files, in `site/fonts/` with each
  font's license beside it. A page uses the stacks `--font-text` and `--font-mono` from the stylesheet, never a font
  from another host.
- **Footer.** One sentence on what HarmFlow is, then two columns of links: the sections, and the privacy, support,
  and GitHub links. The last item of that column, Analytics choice, reopens the analytics consent; without JavaScript
  it leads to the privacy policy's part on withdrawing, `/privacy/#withdraw`. Under both
  columns, HarmFlow's copyright and trademark with the app's license, and the trademark notes for the harnesses and
  Apple's names. The site names no person as HarmFlow's owner: HarmFlow is the app and the company.
