(function () {
    "use strict";

    const COOKIE_NAME = "pa_cookie_consent";
    const CONSENT_VERSION = "2026-06-10";
    const COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 180;

    const DEFAULT_CONSENT = {
        version: CONSENT_VERSION,
        necessary: true,
        functional: false,
        analytics: false,
        marketing: false,
        decidedAt: null
    };

    function cloneDefaultConsent() {
        return Object.assign({}, DEFAULT_CONSENT);
    }

    function getCookie(name) {
        const cookieParts = document.cookie ? document.cookie.split("; ") : [];

        for (let index = 0; index < cookieParts.length; index += 1) {
            const part = cookieParts[index];
            const separatorIndex = part.indexOf("=");
            const cookieName = separatorIndex >= 0 ? part.slice(0, separatorIndex) : part;

            if (cookieName === name) {
                return separatorIndex >= 0 ? part.slice(separatorIndex + 1) : "";
            }
        }

        return null;
    }

    function setCookie(name, value, maxAgeSeconds) {
        const secureFlag = window.location.protocol === "https:" ? "; Secure" : "";

        document.cookie = name + "=" + encodeURIComponent(value) +
            "; Max-Age=" + String(maxAgeSeconds) +
            "; Path=/; SameSite=Lax" + secureFlag;
    }

    function parseConsent(rawValue) {
        if (!rawValue) {
            return null;
        }

        try {
            const parsed = JSON.parse(decodeURIComponent(rawValue));

            if (!parsed || parsed.version !== CONSENT_VERSION) {
                return null;
            }

            return Object.assign(cloneDefaultConsent(), parsed, { necessary: true });
        } catch (error) {
            return null;
        }
    }

    function readConsent() {
        return parseConsent(getCookie(COOKIE_NAME));
    }

    function saveConsent(consent) {
        const normalizedConsent = Object.assign(cloneDefaultConsent(), consent, {
            necessary: true,
            decidedAt: new Date().toISOString()
        });

        setCookie(COOKIE_NAME, JSON.stringify(normalizedConsent), COOKIE_MAX_AGE_SECONDS);
        applyConsent(normalizedConsent);
        hideBanner();
        closePreferences();

        return normalizedConsent;
    }

    function hasConsent(category) {
        const consent = readConsent();

        if (!consent) {
            return false;
        }

        return category === "necessary" || Boolean(consent[category]);
    }

    function loadDeferredEmbeds(consent) {
        const controlledElements = document.querySelectorAll("[data-cookie-category][data-cookie-src]");

        controlledElements.forEach(function (element) {
            const category = element.getAttribute("data-cookie-category");
            const source = element.getAttribute("data-cookie-src");
            const placeholderSelector = element.getAttribute("data-cookie-placeholder");
            const placeholder = placeholderSelector ? document.querySelector(placeholderSelector) : null;
            const isAllowed = category === "necessary" || Boolean(consent[category]);

            if (isAllowed && source && !element.getAttribute("src")) {
                element.setAttribute("src", source);
            }

            if (isAllowed) {
                element.removeAttribute("hidden");

                if (placeholder) {
                    placeholder.setAttribute("hidden", "hidden");
                }
            } else {
                element.setAttribute("hidden", "hidden");

                if (element.getAttribute("src")) {
                    element.removeAttribute("src");
                }

                if (placeholder) {
                    placeholder.removeAttribute("hidden");
                }
            }
        });
    }

    function updatePreferenceInputs(consent) {
        const preferences = consent || readConsent() || cloneDefaultConsent();
        const inputs = document.querySelectorAll("[data-cookie-preference]");

        inputs.forEach(function (input) {
            const category = input.getAttribute("data-cookie-preference");
            input.checked = category === "necessary" || Boolean(preferences[category]);
            input.disabled = category === "necessary";
        });
    }

    function applyConsent(consent) {
        const normalizedConsent = Object.assign(cloneDefaultConsent(), consent || {}, {
            necessary: true
        });

        document.documentElement.classList.toggle(
            "cookie-functional-accepted",
            Boolean(normalizedConsent.functional)
        );
        document.documentElement.classList.toggle(
            "cookie-analytics-accepted",
            Boolean(normalizedConsent.analytics)
        );
        document.documentElement.classList.toggle(
            "cookie-marketing-accepted",
            Boolean(normalizedConsent.marketing)
        );

        loadDeferredEmbeds(normalizedConsent);
        updatePreferenceInputs(normalizedConsent);

        window.dispatchEvent(
            new CustomEvent("paCookieConsentChanged", {
                detail: normalizedConsent
            })
        );
    }

    function showBanner() {
        const banner = document.getElementById("cookie-consent-banner");

        if (banner) {
            banner.removeAttribute("hidden");
        }
    }

    function hideBanner() {
        const banner = document.getElementById("cookie-consent-banner");

        if (banner) {
            banner.setAttribute("hidden", "hidden");
        }
    }

    function openPreferences() {
        const panel = document.getElementById("cookie-preferences-panel");
        const backdrop = document.getElementById("cookie-preferences-backdrop");

        updatePreferenceInputs();

        if (backdrop) {
            backdrop.removeAttribute("hidden");
        }

        if (panel) {
            panel.removeAttribute("hidden");
            panel.setAttribute("aria-modal", "true");

            const firstInput = panel.querySelector("input:not([disabled]), button");

            if (firstInput) {
                firstInput.focus();
            }
        }
    }

    function closePreferences() {
        const panel = document.getElementById("cookie-preferences-panel");
        const backdrop = document.getElementById("cookie-preferences-backdrop");

        if (panel) {
            panel.setAttribute("hidden", "hidden");
            panel.removeAttribute("aria-modal");
        }

        if (backdrop) {
            backdrop.setAttribute("hidden", "hidden");
        }
    }

    function collectPreferenceConsent() {
        const consent = cloneDefaultConsent();
        const inputs = document.querySelectorAll("[data-cookie-preference]");

        inputs.forEach(function (input) {
            const category = input.getAttribute("data-cookie-preference");

            if (category !== "necessary") {
                consent[category] = Boolean(input.checked);
            }
        });

        return consent;
    }

    function bindActions() {
        document.addEventListener("click", function (event) {
            const actionElement = event.target.closest("[data-cookie-action]");

            if (!actionElement) {
                return;
            }

            const action = actionElement.getAttribute("data-cookie-action");

            if (action === "accept-all") {
                saveConsent({
                    functional: true,
                    analytics: true,
                    marketing: true
                });
            }

            if (action === "reject-optional") {
                saveConsent({
                    functional: false,
                    analytics: false,
                    marketing: false
                });
            }

            if (action === "open-preferences") {
                openPreferences();
            }

            if (action === "close-preferences") {
                closePreferences();
            }

            if (action === "save-preferences") {
                saveConsent(collectPreferenceConsent());
            }
        });

        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape") {
                closePreferences();
            }
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        const storedConsent = readConsent();

        bindActions();
        applyConsent(storedConsent || cloneDefaultConsent());

        if (!storedConsent) {
            showBanner();
        }
    });

    window.paCookieConsent = {
        get: readConsent,
        hasConsent: hasConsent,
        openPreferences: openPreferences,
        save: saveConsent
    };
}());
