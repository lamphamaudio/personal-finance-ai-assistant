import React, { createContext, useState, useEffect, useContext } from 'react';
import { getSettings, updatePreferences } from '../api/services';

const AppContext = createContext();

const THEME_OPTIONS = ['auto', 'light', 'dark'];
const THEME_STORAGE_KEY = 'spectra-theme-preference';

export const AppProvider = ({ children }) => {
  const [themePreference, setThemePreference] = useState(() => {
    try {
      const stored = localStorage.getItem(THEME_STORAGE_KEY);
      return THEME_OPTIONS.includes(stored) ? stored : 'auto';
    } catch {
      return 'auto';
    }
  });

  const [effectiveTheme, setEffectiveTheme] = useState('light');
  const [currency, setCurrency] = useState('EUR');
  const [preferences, setPreferences] = useState(null);
  const [loading, setLoading] = useState(true);
  const [toasts, setToasts] = useState([]);

  // Toast handler
  const showToast = (message, type = 'success') => {
    const id = Date.now() + Math.random().toString(36).substr(2, 9);
    setToasts((prev) => [...prev, { id, message, type }]);
    
    // Auto-remove after 4 seconds
    setTimeout(() => {
      removeToast(id);
    }, 4000);
  };

  const removeToast = (id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  // Fetch preferences and settings
  const refreshPreferences = async () => {
    try {
      const data = await getSettings();
      setPreferences(data);
      if (data.currency) setCurrency(data.currency);
      if (data.theme_preference) {
        // If not customized in local storage, sync with server setting
        if (!localStorage.getItem(THEME_STORAGE_KEY)) {
          setThemePreference(data.theme_preference);
        }
      }
    } catch (err) {
      console.error('Failed to load system preferences:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refreshPreferences();
  }, []);

  // Update theme preference
  const changeThemePreference = async (pref) => {
    if (!THEME_OPTIONS.includes(pref)) return;
    setThemePreference(pref);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, pref);
    } catch {}

    // Optionally notify server
    try {
      await updatePreferences({ theme_preference: pref });
    } catch (err) {
      console.warn('Could not sync theme preference with backend:', err);
    }
  };

  // Calculate and apply effective theme
  useEffect(() => {
    const getSystemTheme = () => {
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    };

    const resolved = themePreference === 'auto' ? getSystemTheme() : themePreference;
    setEffectiveTheme(resolved);

    // Apply to DOM
    document.documentElement.dataset.theme = resolved;
    document.documentElement.dataset.themePreference = themePreference;

    // Listen to system changes if theme is auto
    if (themePreference === 'auto') {
      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
      const listener = (e) => {
        const newTheme = e.matches ? 'dark' : 'light';
        setEffectiveTheme(newTheme);
        document.documentElement.dataset.theme = newTheme;
      };

      mediaQuery.addEventListener('change', listener);
      return () => mediaQuery.removeEventListener('change', listener);
    }
  }, [themePreference]);

  return (
    <AppContext.Provider
      value={{
        themePreference,
        effectiveTheme,
        changeThemePreference,
        currency,
        setCurrency,
        preferences,
        refreshPreferences,
        loading,
        toasts,
        showToast,
        removeToast
      }}
    >
      {children}
    </AppContext.Provider>
  );
};

export const useApp = () => {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error('useApp must be used within an AppProvider');
  }
  return context;
};
