/* Prevent accidental/CSRF logouts via plain GET links.
   The /logout endpoint accepts POST only; any <a href="/logout">
   click is converted into a POST form submit instead. */
(function () {
    'use strict';
    document.addEventListener('click', function (event) {
        var link = event.target.closest ? event.target.closest('a[href]') : null;
        if (!link) return;
        var href = link.getAttribute('href') || '';
        var path = href.split('?')[0];
        if (path.replace(/\/+$/, '') !== '/logout') return;
        event.preventDefault();
        var form = document.createElement('form');
        form.method = 'POST';
        form.action = href;
        document.body.appendChild(form);
        form.submit();
    }, true);
})();