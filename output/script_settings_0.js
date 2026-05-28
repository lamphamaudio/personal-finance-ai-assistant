
        const SERVER_THEME_PREFERENCE = "light";
        const THEME_STORAGE_KEY = 'spectra-theme-preference';
        const THEME_OPTIONS = ['auto', 'light', 'dark'];

        function safeReadStoredThemePreference() {
            try {
                const value = localStorage.getItem(THEME_STORAGE_KEY);
                return THEME_OPTIONS.includes(value) ? value : null;
            } catch (_err) {
                return null;
            }
        }

        function safeStoreThemePreference(preference) {
            try {
                localStorage.setItem(THEME_STORAGE_KEY, preference);
            } catch (_err) {
                // Ignore storage failures (private mode, disabled storage, etc.)
            }
        }

        function getThemePreference() {
            if (window.__spectraTheme?.preference && THEME_OPTIONS.includes(window.__spectraTheme.preference)) {
                return window.__spectraTheme.preference;
            }

            const stored = safeReadStoredThemePreference();
            if (stored) {
                return stored;
            }

            return THEME_OPTIONS.includes(SERVER_THEME_PREFERENCE) ? SERVER_THEME_PREFERENCE : 'auto';
        }

        function getSystemTheme() {
            return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
        }

        function resolveTheme(preference = getThemePreference()) {
            return preference === 'auto' ? getSystemTheme() : preference;
        }

        function applyTheme(preference = getThemePreference()) {
            const effectiveTheme = resolveTheme(preference);
            document.documentElement.dataset.theme = effectiveTheme;
            document.documentElement.dataset.themePreference = preference;
            window.__spectraTheme = { preference, effectiveTheme };
            return window.__spectraTheme;
        }

        applyTheme(getThemePreference());
    