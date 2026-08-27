(function () {
    document.querySelectorAll('.dashboard-container').forEach(function (container) {
        var sidebar = container.querySelector('.sidebar');
        var mainContent = container.querySelector('.main-content');
        var topBar = mainContent && mainContent.querySelector('.top-bar');

        if (!sidebar || !topBar || topBar.querySelector('.sidebar-toggle')) {
            return;
        }

        var toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.className = 'sidebar-toggle';
        toggle.setAttribute('aria-label', 'Open navigation menu');
        toggle.setAttribute('aria-expanded', 'false');
        toggle.textContent = '\u2630';
        topBar.insertBefore(toggle, topBar.firstChild);

        toggle.addEventListener('click', function (event) {
            event.stopPropagation();
            var isOpen = sidebar.classList.toggle('active');
            toggle.setAttribute('aria-expanded', String(isOpen));
        });

        sidebar.addEventListener('click', function (event) {
            if (event.target.closest('a')) {
                sidebar.classList.remove('active');
            }
        });

        document.addEventListener('click', function (event) {
            if (window.innerWidth <= 768 &&
                !sidebar.contains(event.target) &&
                !toggle.contains(event.target)) {
                sidebar.classList.remove('active');
                toggle.setAttribute('aria-expanded', 'false');
            }
        });
    });
})();
