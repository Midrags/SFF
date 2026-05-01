/**
 * SteaMidra — Hover Tooltip System
 * Attaches tooltips to any element with data-tooltip attribute.
 */

window.Tooltips = (function() {
    'use strict';

    var _tooltip = null;
    var _showTimeout = null;
    var SHOW_DELAY = 600;

    function init() {
        _tooltip = document.createElement('div');
        _tooltip.className = 'tooltip-popup';
        _tooltip.style.cssText =
            'position:fixed;background:var(--sidebar-bg);border:1px solid var(--border);' +
            'color:var(--fg);font-size:12px;padding:6px 10px;border-radius:6px;' +
            'max-width:280px;pointer-events:none;opacity:0;transition:opacity 0.15s;' +
            'z-index:9999;box-shadow:0 4px 12px rgba(0,0,0,0.3);line-height:1.4;';
        document.body.appendChild(_tooltip);

        document.addEventListener('mouseover', _onMouseOver);
        document.addEventListener('mouseout', _onMouseOut);
    }

    function _onMouseOver(e) {
        var el = e.target.closest('[data-tooltip]');
        if (!el) return;

        var text = el.getAttribute('data-tooltip');
        if (!text) return;

        clearTimeout(_showTimeout);
        _showTimeout = setTimeout(function() {
            _tooltip.textContent = text;
            _tooltip.style.opacity = '1';
            _positionTooltip(el);
        }, SHOW_DELAY);
    }

    function _onMouseOut(e) {
        var el = e.target.closest('[data-tooltip]');
        if (!el) return;
        clearTimeout(_showTimeout);
        _tooltip.style.opacity = '0';
    }

    function _positionTooltip(el) {
        var rect = el.getBoundingClientRect();
        var tw = _tooltip.offsetWidth;
        var th = _tooltip.offsetHeight;

        var left = rect.left + (rect.width / 2) - (tw / 2);
        var top = rect.bottom + 8;

        // Keep within viewport
        if (left < 8) left = 8;
        if (left + tw > window.innerWidth - 8) left = window.innerWidth - tw - 8;
        if (top + th > window.innerHeight - 8) {
            top = rect.top - th - 8;
        }

        _tooltip.style.left = left + 'px';
        _tooltip.style.top = top + 'px';
    }

    return { init: init };
})();
