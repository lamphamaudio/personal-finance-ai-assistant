import { api } from './client';

export const getCurrentUser = () =>
  api.get('/api/auth/me');

export const getDemoUsers = () =>
  api.get('/api/auth/demo-users');

export const loginDemoUser = (userId) =>
  api.post('/api/auth/login', { user_id: userId });

export const logout = () =>
  api.post('/api/auth/logout', {});

export const getSummary = (scope = 'cycle') => 
  api.get(`/api/summary?scope=${encodeURIComponent(scope)}`);

export const getTransactions = (params = {}) => {
  const query = new URLSearchParams();
  if (params.page) query.append('page', params.page);
  if (params.per_page) query.append('per_page', params.per_page);
  if (params.category) query.append('category', params.category);
  if (params.uncategorized_only) query.append('uncategorized_only', params.uncategorized_only);
  if (params.search) query.append('search', params.search);
  if (params.date_from) query.append('date_from', params.date_from);
  if (params.date_to) query.append('date_to', params.date_to);
  const qStr = query.toString();
  return api.get(`/api/transactions${qStr ? `?${qStr}` : ''}`);
};

export const updateTransaction = (txId, data) => 
  api.patch(`/api/transactions/${txId}`, data);

export const bulkUpdateCategory = (ids, category, applyToFuture = true) => 
  api.post('/api/transactions/bulk-category', { ids, category, apply_to_future: applyToFuture });

export const getCategories = () => 
  api.get('/api/categories');

export const getCategoryOptions = () => 
  api.get('/api/categories/options');

export const getSettings = () => 
  api.get('/api/settings');

export const updatePreferences = (data) => 
  api.patch('/api/settings/preferences', data);

export const getCategoryRules = () => 
  api.get('/api/settings/rules');

export const createCategoryRule = (rule) => 
  api.post('/api/settings/rules', rule);

export const updateCategoryRule = (ruleId, data) => 
  api.patch(`/api/settings/rules/${ruleId}`, data);

export const deleteCategoryRule = (ruleId) => 
  api.delete(`/api/settings/rules/${ruleId}`);

export const testCategoryRule = (data) => 
  api.post('/api/settings/rules/test', data);

export const getLearningSummary = () => 
  api.get('/api/settings/learning');

export const reapplyLearning = () => 
  api.post('/api/settings/learning/reapply');

export const resetDatabase = (confirmToken) => 
  api.post('/api/settings/reset-db', { confirm: confirmToken });

export const confirmImport = (transactions) => 
  api.post('/api/confirm', { transactions });

export const getBudget = () => 
  api.get('/api/budget');

export const updateBudgetLimit = (category, limit) => 
  api.patch(`/api/budget/${encodeURIComponent(category)}`, { limit });

export const getTrends = () => 
  api.get('/api/trends');

export const getSubscriptions = () => 
  api.get('/api/subscriptions');

export const uploadFileRaw = (file) => {
  const formData = new FormData();
  formData.append('file', file);
  return fetch('/api/upload', {
    method: 'POST',
    body: formData,
  });
};

export const importBankRaw = () => (
  fetch('/api/import-bank', {
    method: 'POST',
  })
);
