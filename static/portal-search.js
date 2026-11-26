(function () {
    'use strict';

    function normalize(value) {
        return (value || '').toString().trim().toLowerCase();
    }

    function updateTable(input) {
        var tableId = input.getAttribute('data-search-table');
        var table = document.getElementById(tableId);
        if (!table) return;

        var query = normalize(input.value);
        var rows = table.querySelectorAll('tbody tr');
        var visible = 0;

        rows.forEach(function (row) {
            var isPlaceholder = row.querySelector('td[colspan]');
            if (isPlaceholder) {
                row.style.display = '';
                return;
            }
            var matches = !query || normalize(row.textContent).includes(query);
            row.style.display = matches ? '' : 'none';
            if (matches) visible++;
        });

        var status = input.nextElementSibling;
        if (!status || !status.classList.contains('portal-search-status')) {
            status = document.createElement('span');
            status.className = 'portal-search-status';
            status.setAttribute('aria-live', 'polite');
            input.insertAdjacentElement('afterend', status);
        }
        status.textContent = query ? visible + ' result' + (visible === 1 ? '' : 's') : '';

        if (typeof window.onPortalTableSearch === 'function') {
            window.onPortalTableSearch(tableId, query);
        }
    }

    function initialise() {
        document.querySelectorAll('[data-portal-search]').forEach(function (input) {
            if (input.dataset.portalSearchReady) return;
            input.dataset.portalSearchReady = 'true';
            input.addEventListener('input', function () {
                updateTable(input);
            });
            updateTable(input);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialise);
    } else {
        initialise();
    }
})();
