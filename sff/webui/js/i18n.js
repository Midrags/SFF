/**
 * SteaMidra -- Web UI i18n
 * Loads translations from the backend and applies them to static and dynamic UI text.
 * Supports RTL layout for Arabic and other right-to-left languages.
 */

window.I18n = (function() {
    'use strict';

    var _translations = {};
    var _currentLang = 'en';
    var _rtlLangs = ['ar', 'he', 'fa', 'ur'];
    var _observer = null;
    var _textState = new WeakMap();
    var _attributeState = new WeakMap();

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
            _startObserver();
            if (typeof onDone === 'function') onDone();
        });
    }

    /** Translate a key, returning the original key if no translation exists. */
    function t(key) {
        return _translations[key] || key;
    }

    function _translateString(value) {
        if (typeof value !== 'string') return value;
        var match = value.match(/^(\s*)([\s\S]*?)(\s*)$/);
        var source = match ? match[2] : value;
        var translated = _translations[source];
        return translated && match ? match[1] + translated + match[3] : (translated || value);
    }

    function _translateTextNode(node) {
        var state = _textState.get(node);
        if (!state || node.nodeValue !== state.applied) {
            state = { source: node.nodeValue, applied: node.nodeValue };
        }
        var translated = _translateString(state.source);
        state.applied = translated;
        _textState.set(node, state);
        if (node.nodeValue !== translated) node.nodeValue = translated;
    }

    function _translateAttribute(el, attr) {
        if (!el.hasAttribute(attr)) return;
        var states = _attributeState.get(el) || {};
        var current = el.getAttribute(attr);
        var state = states[attr];
        if (!state || current !== state.applied) {
            state = { source: current, applied: current };
        }
        var translated = _translateString(state.source);
        state.applied = translated;
        states[attr] = state;
        _attributeState.set(el, states);
        if (current !== translated) el.setAttribute(attr, translated);
    }

    function _translateElement(el) {
        if (!el || el.nodeType !== 1) return;
        ['data-tooltip', 'title', 'placeholder', 'aria-label'].forEach(function(attr) {
            if (attr === 'placeholder' && el.hasAttribute('data-i18n-placeholder')) return;
            _translateAttribute(el, attr);
        });
        if (el.hasAttribute('data-i18n')) return;
        Array.prototype.forEach.call(el.childNodes, function(node) {
            if (node.nodeType === 3 && node.nodeValue.trim()) _translateTextNode(node);
        });
    }

    /** Apply keyed translations and exact translations for existing hardcoded UI text. */
    function _applyToDOM() {
        document.querySelectorAll('[data-i18n]').forEach(function(el) {
            var key = el.getAttribute('data-i18n');
            el.textContent = t(key);
        });
        document.querySelectorAll('[data-i18n-placeholder]').forEach(function(el) {
            var key = el.getAttribute('data-i18n-placeholder');
            el.placeholder = t(key);
        });
        document.querySelectorAll('body, body *').forEach(_translateElement);
    }

    function _startObserver() {
        if (_observer || !document.body) return;
        _observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                Array.prototype.forEach.call(mutation.addedNodes, function(node) {
                    if (node.nodeType === 3 && node.parentElement) {
                        _translateElement(node.parentElement);
                    } else if (node.nodeType === 1) {
                        _translateElement(node);
                        node.querySelectorAll('*').forEach(_translateElement);
                    }
                });
            });
        });
        _observer.observe(document.body, { childList: true, subtree: true });
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

