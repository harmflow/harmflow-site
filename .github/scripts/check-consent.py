#!/usr/bin/env python3
"""Checks the analytics consent and the analytics in a headless browser, over the site's files as committed: that with
no choice made, or after Reject, a page makes no request to any host but its own and sets no analytics cookie; that
the banner offers Accept and Reject of equal weight and does not show again once a choice is made; that after Accept
only the page views, the clicks on the landing page's primary call to action, and the visits to the 404 page are
measured; that withdrawing through the footer's link stops the measurement and removes the analytics cookies; and that
with JavaScript disabled every page's content and navigation work and no banner shows. It names each problem it finds
on stderr, one per line, and exits 1 when it finds any. The Checks workflow (.github/workflows/checks.yml) runs it on
the checkout, and check-consent-test.py proves each check on a tree of its own that breaks it.

Usage: check-consent.py [ROOT]

ROOT is the folder GitHub Pages serves, site/ by default. The check serves it on 127.0.0.1, answers a path it does not
hold with 404.html, as GitHub Pages does, and points the browser's harmflow.com there, so the pages run on the site's
own host. No request leaves the machine: Google's tag is answered with a stand-in that records what the site asks it
to send, and sets the two cookies the real tag sets, on .harmflow.com as it does, so no Analytics property is needed.

Needs Playwright for Python and its Chromium: pip install playwright, then python3 -m playwright install chromium.
"""

import functools
import http.server
import json
import os
import sys
import threading
from urllib.parse import urlsplit

# The path the check requests to reach the 404 page.
MISSING_PATH = "/no-such-page/"

# Google's tag, the only request to another host a page may make, and only after Accept.
TAG_HOST = "www.googletagmanager.com"

# The events the site may send besides the page view, which the tag's configuration sends on its own.
CTA_CLICK = "cta_click"
PAGE_NOT_FOUND = "page_not_found"

# The site's host, which the browser resolves to the check's own server.
SITE_HOST = "harmflow.com"

# The stand-in for Google's tag: it records every command the page pushes to the data layer, the ones pushed before it
# loaded and the ones after, and sets a _ga and a _ga_<container> cookie on the site's registrable domain, as the real
# tag does by default.
TAG_STAND_IN = """
(function () {
  var layer = window.dataLayer = window.dataLayer || [];
  var calls = window.__analyticsCalls = [];
  function record(args) { calls.push(JSON.parse(JSON.stringify(Array.prototype.slice.call(args)))); }
  layer.forEach(record);
  var push = layer.push;
  layer.push = function (args) { record(args); return push.apply(layer, arguments); };
  document.cookie = "_ga=GA1.1.1234567890.1234567890; path=/; domain=.harmflow.com";
  document.cookie = "_ga_CHECK=GS1.1.1234567890.1.0.1234567890.0.0.0; path=/; domain=.harmflow.com";
})();
"""

# The computed styles that make one button stand out from another.
PROMINENCE = (
    "font-family", "font-size", "font-weight", "color", "background-color", "border-top-width", "border-top-style",
    "border-top-color", "border-radius", "padding-top", "padding-left", "min-width", "text-decoration-line",
)


class Handler(http.server.SimpleHTTPRequestHandler):
    """Serves ROOT as GitHub Pages does: a path it does not hold answers 404 with 404.html."""

    def send_error(self, code, message=None, explain=None):
        page = os.path.join(self.directory, "404.html")
        if code != 404 or not os.path.isfile(page):
            return super().send_error(code, message, explain)
        with open(page, "rb") as f:
            body = f.read()
        self.send_response(404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def log_message(self, *args):
        pass


def serve(root):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=root))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def page_paths(root):
    """The path every page of the tree is served at, and the missing path the 404 page answers."""
    paths = []
    for directory, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in sorted(files):
            rel = os.path.relpath(os.path.join(directory, name), root).replace(os.sep, "/")
            if name == "index.html":
                paths.append("/" + rel[: -len("index.html")])
            elif name.endswith(".html") and rel != "404.html":
                paths.append("/" + rel)
    return sorted(paths) + [MISSING_PATH]


class Browser:
    """One headless Chromium, with a context per visitor; every request outside the site is recorded and answered here."""

    def __init__(self, playwright, port):
        self.browser = playwright.chromium.launch(args=["--host-resolver-rules=MAP %s 127.0.0.1" % SITE_HOST])
        self.origin = "http://%s:%d" % (SITE_HOST, port)
        self.host = urlsplit(self.origin).netloc
        # The same server, for requests made outside the browser, which do not follow its host rules.
        self.direct = "http://127.0.0.1:%d" % port

    def visitor(self, javascript=True):
        context = self.browser.new_context(java_script_enabled=javascript)
        context.outside = []  # (the page's path, the URL it requested)

        def route(r):
            url = r.request.url
            parts = urlsplit(url)
            if parts.netloc == self.host:
                return r.continue_()
            frame = r.request.frame
            context.outside.append((urlsplit(frame.url).path if frame and frame.url else "?", url))
            if parts.netloc == TAG_HOST and parts.path == "/gtag/js":
                return r.fulfill(status=200, content_type="text/javascript", body=TAG_STAND_IN)
            if r.request.is_navigation_request():
                # A link out of the site, such as the call to action: 204 keeps the browser on the page.
                return r.fulfill(status=204, body="")
            return r.abort()

        context.route("**/*", route)
        return context

    def close(self):
        self.browser.close()


def analytics_cookies(context):
    return sorted(c["name"] for c in context.cookies() if c["name"] == "_ga" or c["name"].startswith("_ga_"))


def calls_of(page):
    return page.evaluate("window.__analyticsCalls || []")


def tag_ran(page):
    """Whether Google's tag, the stand-in, loaded and recorded a command within five seconds."""
    try:
        page.wait_for_function("(window.__analyticsCalls || []).length > 0", timeout=5000)
        return True
    except Exception:
        return False


def banner_shown(page):
    banner = page.locator("[data-consent-banner]")
    return banner.count() > 0 and banner.first.is_visible()


def open_page(context, origin, path):
    page = context.new_page()
    page.goto(origin + path, wait_until="load")
    return page


def check_calls(path, calls, allowed_events):
    """The commands the page asked the tag to run: only the configuration, with Google signals and ad personalization
    off and no user identifier, and the allowed events."""
    problems = []
    for call in calls:
        command = call[0] if call else None
        if command in ("consent", "js"):
            continue
        if command == "config":
            options = call[2] if len(call) > 2 and isinstance(call[2], dict) else {}
            if options.get("allow_google_signals") is not False:
                problems.append("measured: %s configures the tag without turning Google signals off" % path)
            if options.get("allow_ad_personalization_signals") is not False:
                problems.append("measured: %s configures the tag without turning ad personalization off" % path)
            if "user_id" in options:
                problems.append("measured: %s sets a user identifier of its own" % path)
            continue
        if command == "event" and len(call) > 1 and call[1] in allowed_events:
            continue
        problems.append("measured: %s sends %s, which the site does not measure" % (path, json.dumps(call)))
    return problems


def check_no_choice(browser, paths):
    """Every page, in a browser with no choice made: the banner, its two buttons of equal weight, the footer's link,
    and no request outside the site nor analytics cookie."""
    problems = []
    for path in paths:
        context = browser.visitor()
        page = open_page(context, browser.origin, path)
        if not banner_shown(page):
            problems.append("banner: %s shows no banner with no choice made" % path)
        else:
            buttons = page.locator("[data-consent-banner] button")
            labels = [buttons.nth(i).inner_text().strip() for i in range(buttons.count())]
            if labels != ["Accept", "Reject"]:
                problems.append("banner: %s offers %s, not Accept and Reject" % (path, labels))
            else:
                looks = [
                    buttons.nth(i).evaluate(
                        "(b, names) => [b.className, b.hasAttribute('autofocus')]"
                        ".concat(names.map(n => getComputedStyle(b).getPropertyValue(n)))",
                        list(PROMINENCE),
                    )
                    for i in range(2)
                ]
                if looks[0] != looks[1]:
                    problems.append("banner: %s: Accept and Reject differ in prominence: %s | %s" % (path, *looks))
                if page.evaluate("document.activeElement && document.activeElement.tagName") == "BUTTON":
                    problems.append("banner: %s preselects a choice by focusing a button" % path)
        if page.locator('footer a[data-consent-choice][href="/privacy/#withdraw"]').count() != 1:
            problems.append("withdraw: %s has no footer link that reopens the choice and leads to /privacy/#withdraw" % path)
        for source, url in context.outside:
            problems.append("before consent: %s requests %s with no choice made" % (path, url))
        for name in analytics_cookies(context):
            problems.append("before consent: %s sets the analytics cookie %s with no choice made" % (path, name))
        context.close()
    return problems


def check_reject(browser, paths):
    """One visitor who rejects on the first page: no banner again, on a reload or on any page, and nothing requested
    outside the site nor any analytics cookie."""
    problems = []
    context = browser.visitor()
    page = open_page(context, browser.origin, paths[0])
    if not banner_shown(page):
        context.close()
        return ["banner: %s shows no banner to reject" % paths[0]]
    page.click("[data-consent-banner] button[data-consent=denied]")
    if banner_shown(page):
        problems.append("banner: %s still shows the banner after Reject" % paths[0])
    page.reload(wait_until="load")
    if banner_shown(page):
        problems.append("banner: %s shows the banner again after a reload, once rejected" % paths[0])
    for path in paths:
        page.goto(browser.origin + path, wait_until="load")
        if banner_shown(page):
            problems.append("banner: %s shows the banner again, once rejected" % path)
    for source, url in context.outside:
        problems.append("after Reject: %s requests %s" % (source, url))
    for name in analytics_cookies(context):
        problems.append("after Reject: the analytics cookie %s is set" % name)
    context.close()
    return problems


def check_accept_and_withdraw(browser, paths):
    """One visitor who accepts on the landing page: the tag on every page from then on, only the three kinds of event,
    the call to action's click measured, and the 404 page's visit; then withdrawal through the footer's link, after
    which nothing is measured and no analytics cookie remains."""
    problems = []
    context = browser.visitor()
    page = open_page(context, browser.origin, "/")
    if not banner_shown(page):
        context.close()
        return ["banner: / shows no banner to accept"]
    page.click("[data-consent-banner] button[data-consent=granted]")
    if not tag_ran(page):
        problems.append("after Accept: / does not load Google's tag")
    if banner_shown(page):
        problems.append("banner: / still shows the banner after Accept")
    calls = calls_of(page)
    problems += check_calls("/", calls, ())
    if not any(c[:1] == ["config"] for c in calls):
        problems.append("measured: / after Accept configures no tag, so no page view is measured")
    cta = page.locator("main a.cta")
    if cta.count() == 0:
        problems.append("measured: / has no primary call to action (main a.cta) to measure")
    else:
        before = len(calls_of(page))
        cta.first.click()
        page.wait_for_timeout(300)
        clicks = [c for c in calls_of(page)[before:] if c[:2] == ["event", CTA_CLICK]]
        if len(clicks) != 1:
            problems.append("measured: a click on /'s call to action sends %d %s events, not one" % (len(clicks), CTA_CLICK))
        problems += check_calls("/", calls_of(page)[before:], (CTA_CLICK,))
    for path in paths:
        page.goto(browser.origin + path, wait_until="load")
        if banner_shown(page):
            problems.append("banner: %s shows the banner again, once accepted" % path)
        if not tag_ran(page):
            problems.append("after Accept: %s does not load Google's tag" % path)
            continue
        calls = calls_of(page)
        expected = (PAGE_NOT_FOUND,) if path == MISSING_PATH else ()
        problems += check_calls(path, calls, expected)
        if path == MISSING_PATH and ["event", PAGE_NOT_FOUND] not in [c[:2] for c in calls]:
            problems.append("measured: the 404 page, at %s, sends no %s event" % (path, PAGE_NOT_FOUND))
    if not analytics_cookies(context):
        problems.append("after Accept: the stand-in tag set no analytics cookie, so withdrawal cannot be proven")

    # Withdraw, from the footer of the privacy policy.
    page.goto(browser.origin + "/privacy/", wait_until="load")
    if not tag_ran(page):
        problems.append("withdraw: /privacy/ does not load Google's tag after Accept, so there is nothing to withdraw")
        context.close()
        return problems
    page.click("footer a[data-consent-choice]")
    if not banner_shown(page):
        problems.append("withdraw: the footer's link on /privacy/ does not reopen the choice")
        context.close()
        return problems
    tag_requests = len(context.outside)
    with page.expect_navigation(wait_until="load", timeout=5000):
        page.click("[data-consent-banner] button[data-consent=denied]")
    for name in analytics_cookies(context):
        problems.append("withdraw: the analytics cookie %s remains after withdrawing" % name)
    for path in ["/privacy/"] + paths:
        if path != "/privacy/":
            page.goto(browser.origin + path, wait_until="load")
        if banner_shown(page):
            problems.append("withdraw: %s shows the banner again after withdrawing" % path)
        if calls_of(page):
            problems.append("withdraw: %s still measures after withdrawing: %s" % (path, json.dumps(calls_of(page))))
    for source, url in context.outside[tag_requests:]:
        problems.append("withdraw: %s requests %s after withdrawing" % (source, url))
    context.close()
    return problems


def check_without_javascript(browser, paths):
    """Every page with JavaScript disabled: its content shows, its links into the site answer, and no banner shows."""
    problems = []
    context = browser.visitor(javascript=False)
    for path in paths:
        page = open_page(context, browser.origin, path)
        main = page.locator("main")
        if main.count() == 0 or not main.first.is_visible() or not main.first.inner_text().strip():
            problems.append("without JavaScript: %s shows no content" % path)
        if banner_shown(page):
            problems.append("without JavaScript: %s shows the banner" % path)
        hrefs = page.eval_on_selector_all("a[href^='/']", "links => links.map(a => a.getAttribute('href'))")
        for href in sorted(set(hrefs)):
            response = context.request.get(browser.direct + href.split("#")[0])
            if response.status != 200:
                problems.append("without JavaScript: %s links to %s, which answers %d" % (path, href, response.status))
        page.close()
    for source, url in context.outside:
        problems.append("without JavaScript: %s requests %s" % (source, url))
    context.close()
    return problems


def main(argv):
    args = argv[1:]
    if len(args) > 1:
        print("usage: check-consent.py [ROOT]", file=sys.stderr)
        return 2
    root = os.path.abspath(args[0] if args else "site")
    if not os.path.isdir(root):
        print("check-consent: %s is not a directory" % root, file=sys.stderr)
        return 2
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "check-consent: needs Playwright for Python: pip install playwright, then python3 -m playwright install "
            "chromium",
            file=sys.stderr,
        )
        return 2
    paths = page_paths(root)
    server = serve(root)
    problems = []
    try:
        with sync_playwright() as playwright:
            browser = Browser(playwright, server.server_address[1])
            try:
                problems += check_no_choice(browser, paths)
                problems += check_reject(browser, paths)
                problems += check_accept_and_withdraw(browser, paths)
                problems += check_without_javascript(browser, paths)
            finally:
                browser.close()
    finally:
        server.shutdown()
    for problem in problems:
        print("check-consent: " + problem, file=sys.stderr)
    if problems:
        print("check-consent: %d problems" % len(problems), file=sys.stderr)
        return 1
    print("check-consent: ok: %d paths, with no choice, after Reject, after Accept and withdrawal, and without "
          "JavaScript" % len(paths))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
