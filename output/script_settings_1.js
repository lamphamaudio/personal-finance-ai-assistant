
        let defaultCurrency = null; // initially §null§ and will be populated when needed using `loadCurrency`
        // Promise<string|undefined>
        async function loadCurrency() {
            if (!defaultCurrency) {
                const response = await fetch('/api/settings');
                defaultCurrency = (await response.json())['currency'];
            }
            return defaultCurrency;
        }

        const themeMediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

        function emitThemeChange(detail) {
            window.dispatchEvent(new Tùy chỉnhEvent('spectra-theme-change', { detail }));
        }

        function syncThemeSelects() {
            const preference = getThemePreference();
            document.querySelectorAll('[data-theme-select]').forEach(select => {
                if (select.value !== preference) {
                    select.value = preference;
                }
            });
        }

        function setThemePreference(preference) {
            const normalized = THEME_OPTIONS.includes(preference) ? preference : 'auto';
            const detail = applyTheme(normalized);
            safeStoreThemePreference(normalized);
            syncThemeSelects();
            emitThemeChange(detail);
            return detail;
        }

        const handleSystemThemeChange = () => {
            if (getThemePreference() !== 'auto') {
                return;
            }

            const detail = applyTheme('auto');
            syncThemeSelects();
            emitThemeChange(detail);
        };

        if (typeof themeMediaQuery.addEventListener === 'function') {
            themeMediaQuery.addEventListener('change', handleSystemThemeChange);
        } else if (typeof themeMediaQuery.addListener === 'function') {
            themeMediaQuery.addListener(handleSystemThemeChange);
        }

        window.SpectraTheme = {
            getPreference: getThemePreference,
            getEffectiveTheme: () => resolveTheme(getThemePreference()),
            getState: () => window.__spectraTheme || applyTheme(getThemePreference()),
            setPreference: setThemePreference,
            getCssVar: (name, fallback = '') => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback,
            syncThemeSelects,
        };

        syncThemeSelects();

        function parseSpectraDate(dateString) {
            return new Date(`${dateString}T00:00:00`);
        }

        function formatSpectraDate(dateString, options = { day: 'numeric', month: 'short', year: 'numeric' }) {
            return parseSpectraDate(dateString).toLocaleDateString('vi-VN', options);
        }

        function formatCycleRange(startDate, endExclusiveDate, options = { day: 'numeric', month: 'short', year: 'numeric' }) {
            const endDate = parseSpectraDate(endExclusiveDate);
            endDate.setDate(endDate.getDate() - 1);
            return `${parseSpectraDate(startDate).toLocaleDateString('vi-VN', options)} -> ${endDate.toLocaleDateString('vi-VN', options)}`;
        }

        function showToast(message, type = 'success') {
            const container = document.getElementById('toastContainer');
            const toast = document.createElement('div');
            const icons = { success: '✓', error: '×', info: 'i' };
            toast.className = `toast toast-${type}`;
            toast.innerHTML = `<span>${icons[type] || ''}</span> ${message}`;
            container.appendChild(toast);
            setTimeout(() => {
                toast.style.opacity = '0';
                toast.style.transform = 'translateX(24px)';
                toast.style.transition = '0.3s ease';
                setTimeout(() => toast.remove(), 300);
            }, 4000);
        }

        function formatCurrency(amount, currency = undefined) {
            const options = { style: 'currency', currency: currency || defaultCurrency };
            return new Intl.NumberFormat('vi-VN', options).format(amount);
        }

        function toggleSidebar() {
            document.getElementById('sidebar').classList.toggle('open');
        }

        // Close sidebar on outside click (mobile)
        document.addEventListener('click', e => {
            const sidebar = document.getElementById('sidebar');
            const toggle = document.getElementById('menuToggle');
            if (window.innerWidth <= 768 && sidebar.classList.contains('open')
                && !sidebar.contains(e.target) && !toggle.contains(e.target)) {
                sidebar.classList.remove('open');
            }
        });
    