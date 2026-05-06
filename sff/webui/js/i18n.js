/**
 * SteaMidra -- Web UI i18n
 * Loads translations from the backend and applies them to [data-i18n] elements.
 * Supports RTL layout for Arabic and other right-to-left languages.
 */

window.I18n = (function() {
    'use strict';

    var _translations = {};
    var _currentLang = 'en';
    var _rtlLangs = ['ar', 'he', 'fa', 'ur'];

    /**
     * Load translations for the given language code and apply them to the DOM.
     * Falls back to English if the language file is missing on the backend.
     * @param {string} lang  Language code (e.g. 'en', 'ar', 'de').
     * @param {Function} [onDone]  Optional callback called after the DOM is updated.
     */
    function applyLanguage(lang, onDone) {
        if (!lang || lang === 'Auto') lang = 'en';
        _currentLang = lang;

        Bridge.callWithCallback('get_webui_translations', lang, function(json) {
            try {
                _translations = JSON.parse(json || '{}');
            } catch(e) {
                _translations = {};
            }
            _applyToDOM();
            _setDirection(lang);
            if (typeof onDone === 'function') onDone();
        });
    }

    /** Translate a key, returning the original key if no translation exists. */
    function t(key) {
        return _translations[key] || key;
    }

    /** Walk all [data-i18n] elements and replace their textContent. */
    function _applyToDOM() {
        document.querySelectorAll('[data-i18n]').forEach(function(el) {
            var key = el.getAttribute('data-i18n');
            var val = _translations[key];
            if (val) el.textContent = val;
        });
        document.querySelectorAll('[data-i18n-placeholder]').forEach(function(el) {
            var key = el.getAttribute('data-i18n-placeholder');
            var val = _translations[key];
            if (val) el.placeholder = val;
        });
    }

    /** Set the document direction and lang attribute. */
    function _setDirection(lang) {
        var isRTL = _rtlLangs.indexOf(lang) !== -1;
        document.documentElement.setAttribute('dir', isRTL ? 'rtl' : 'ltr');
        document.documentElement.setAttribute('lang', lang);
    }

    return {
        applyLanguage: applyLanguage,
        t: t
    };
})();
