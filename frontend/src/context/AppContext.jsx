import { createContext, useState, useEffect, useContext, useCallback, useRef } from 'react';
import {
  getCurrentUser,
  getSettings,
  loginDemoUser,
  logout,
  updatePreferences,
} from '../api/services';

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
  const [authLoading, setAuthLoading] = useState(true);
  const [currentUser, setCurrentUser] = useState(null);
  const [toasts, setToasts] = useState([]);

  // Toast handler
  const removeToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const showToast = useCallback((message, type = 'success') => {
    const id = Date.now() + Math.random().toString(36).substr(2, 9);
    setToasts((prev) => [...prev, { id, message, type }]);
    
    // Auto-remove after 4 seconds
    setTimeout(() => {
      removeToast(id);
    }, 4000);
  }, [removeToast]);

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

  const refreshAuth = async () => {
    setAuthLoading(true);
    try {
      const data = await getCurrentUser();
      setCurrentUser(data.user);
    } catch {
      setCurrentUser(null);
    } finally {
      setAuthLoading(false);
    }
  };

  const loginAsDemoUser = async (userId) => {
    const data = await loginDemoUser(userId);
    setCurrentUser(data.user);
    showToast('Logged in');
    return data.user;
  };

  const logoutCurrentUser = async () => {
    await logout();
    setCurrentUser(null);
    showToast('Logged out');
  };

  useEffect(() => {
    refreshAuth();
    refreshPreferences();
  }, []);

  // Update theme preference
  const changeThemePreference = async (pref) => {
    if (!THEME_OPTIONS.includes(pref)) return;
    setThemePreference(pref);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, pref);
    } catch {
      // localStorage may be unavailable in restricted browser contexts.
    }

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

  const apiCacheRef = useRef({});

  const swrFetch = useCallback(async (key, fetchFn, onData, onError) => {
    // 1. Immediately return cached data if available
    const cached = apiCacheRef.current[key];
    if (cached) {
      onData(cached);
    }

    // 2. Fetch fresh data in the background
    try {
      const freshData = await fetchFn();
      const freshStr = JSON.stringify(freshData);
      const cachedStr = cached ? JSON.stringify(cached) : null;

      // 3. Only update if data has changed or was empty
      if (freshStr !== cachedStr) {
        apiCacheRef.current[key] = freshData;
        onData(freshData);
      }
    } catch (err) {
      if (onError) {
        onError(err);
      } else {
        console.error(`SWR fetch failed for key ${key}:`, err);
      }
    }
  }, []);

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
        authLoading,
        currentUser,
        refreshAuth,
        loginAsDemoUser,
        logoutCurrentUser,
        toasts,
        showToast,
        removeToast,
        swrFetch
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
