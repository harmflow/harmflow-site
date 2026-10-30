/* The analytics consent and the analytics, the only JavaScript of the site: every page's content and navigation work
   without it, and without it no banner shows and nothing is measured.

   On a visitor's first page a banner asks for consent to Google Analytics 4, with Accept and Reject of equal weight.
   The choice is kept in the browser's localStorage, never in a cookie, and the banner does not show again. Until the
   kept choice is Accept, the page loads nothing from Google and sets no analytics cookie: Google's tag is added to the
   page only after Accept. Once it is, it measures three kinds of event and nothing else — the page views, the clicks
   on the landing page's primary call to action, and the visits to the 404 page — with no user identifier of the
   site's own, and with Google signals and ad personalization off.

   The footer's analytics link reopens the choice; without JavaScript it leads to the privacy policy's part on
   withdrawing. Rejecting after an Accept stops the measurement, removes the analytics cookies, and reloads the page,
   so the tag already loaded sends nothing more.

   .github/scripts/check-consent.py proves each of these in a browser. */
(function () {
  "use strict";

  // The site's Google Analytics 4 property, which belongs to a HarmFlow account. The one account-linked identifier
  // the repository holds, and only here.
  var MEASUREMENT_ID = "G-XXXXXXXXXX";

  var STORAGE_KEY = "harmflow.analytics-consent";
  var GRANTED = "granted";
  var DENIED = "denied";

  // The events the site sends besides the page view, which the tag's configuration sends on its own.
  var CTA_CLICK = "cta_click";
  var PAGE_NOT_FOUND = "page_not_found";

  var started = false;
  var banner = null;

  function storedChoice() {
    try {
      return window.localStorage.getItem(STORAGE_KEY);
    } catch (e) {
      return null;
    }
  }

  function storeChoice(choice) {
    try {
      window.localStorage.setItem(STORAGE_KEY, choice);
    } catch (e) {
      // Storage refused, as in some private windows: the choice holds for this page only, and the banner asks again.
    }
  }

  function gtag() {
    window.dataLayer.push(arguments);
  }

  // Google's tag, added only after Accept. Consent Mode is set too, for the tag's own reading, but it is not what
  // keeps Google out before consent: the tag is simply not on the page until then.
  function startAnalytics() {
    if (started) {
      return;
    }
    started = true;
    window["ga-disable-" + MEASUREMENT_ID] = false;
    window.dataLayer = window.dataLayer || [];
    gtag("consent", "default", {
      ad_storage: "denied",
      ad_user_data: "denied",
      ad_personalization: "denied",
      analytics_storage: "granted"
    });
    gtag("js", new Date());
    gtag("config", MEASUREMENT_ID, {
      allow_google_signals: false,
      allow_ad_personalization_signals: false
    });
    if (document.body && document.body.getAttribute("data-page") === "not-found") {
      gtag("event", PAGE_NOT_FOUND);
    }
    var tag = document.createElement("script");
    tag.async = true;
    tag.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(MEASUREMENT_ID);
    document.head.appendChild(tag);
  }

  // Every _ga and _ga_<container> cookie, expired on each domain the tag may have set it on: the page's host, and the
  // site's registrable domain with a leading dot, which is the tag's default.
  function removeAnalyticsCookies() {
    var host = window.location.hostname;
    var labels = host.split(".");
    var domains = ["", host, "." + host];
    if (labels.length > 2) {
      domains.push("." + labels.slice(-2).join("."));
    }
    document.cookie.split(";").forEach(function (cookie) {
      var name = cookie.split("=")[0].trim();
      if (!/^_ga(_|$)/.test(name)) {
        return;
      }
      domains.forEach(function (domain) {
        document.cookie = name + "=; Max-Age=0; path=/" + (domain ? "; domain=" + domain : "");
      });
    });
  }

  function withdraw() {
    window["ga-disable-" + MEASUREMENT_ID] = true;
    removeAnalyticsCookies();
    window.location.reload();
  }

  function choose(choice) {
    var before = storedChoice();
    storeChoice(choice);
    hideBanner();
    if (choice === GRANTED) {
      startAnalytics();
    } else if (started || before === GRANTED) {
      withdraw();
    }
  }

  function buildBanner() {
    var region = document.createElement("section");
    region.className = "consent";
    region.setAttribute("data-consent-banner", "");
    region.setAttribute("aria-label", "Analytics consent");
    region.tabIndex = -1;

    var text = document.createElement("p");
    text.appendChild(
      document.createTextNode(
        "May HarmFlow measure your visit with Google Analytics? It counts the pages you view, the clicks on the main " +
          "call to action, and the visits to missing pages, and sets Google's cookies only if you accept. "
      )
    );
    var policy = document.createElement("a");
    policy.href = "/privacy/#analytics";
    policy.textContent = "Privacy policy";
    text.appendChild(policy);
    region.appendChild(text);

    // Accept and Reject are the same button, with the same class and no preselection: neither one is the default.
    var actions = document.createElement("div");
    actions.className = "consent-actions";
    [
      [GRANTED, "Accept"],
      [DENIED, "Reject"]
    ].forEach(function (option) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "consent-button";
      button.setAttribute("data-consent", option[0]);
      button.textContent = option[1];
      button.addEventListener("click", function () {
        choose(option[0]);
      });
      actions.appendChild(button);
    });
    region.appendChild(actions);
    return region;
  }

  function showBanner(focus) {
    if (!banner) {
      banner = buildBanner();
      document.body.appendChild(banner);
    }
    banner.hidden = false;
    if (focus) {
      banner.focus();
    }
  }

  function hideBanner() {
    if (banner) {
      banner.hidden = true;
    }
  }

  function onClick(event) {
    var link = event.target.closest && event.target.closest("a");
    if (!link) {
      return;
    }
    if (link.hasAttribute("data-consent-choice")) {
      event.preventDefault();
      showBanner(true);
    } else if (started && link.classList.contains("cta")) {
      // The click leaves the page, so the event goes as a beacon, which the browser sends after the page is gone.
      gtag("event", CTA_CLICK, { transport_type: "beacon" });
    }
  }

  function init() {
    document.addEventListener("click", onClick);
    var choice = storedChoice();
    if (choice === GRANTED) {
      startAnalytics();
    } else if (choice !== DENIED) {
      showBanner(false);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
