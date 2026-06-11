import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import {
  getTransactions,
  getCategories,
  updateTransaction,
  bulkUpdateCategory
} from '../api/services';

export default function Transactions() {
  const { currency, showToast } = useApp();
  
  // Filters & Pagination State
  const [search, setSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [uncategorizedOnly, setUncategorizedOnly] = useState(false);
  const [page, setPage] = useState(1);
  
  // Data States
  const [transactions, setTransactions] = useState([]);
  const [categories, setCategories] = useState([]);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(1);
  const [loading, setLoading] = useState(true);
  
  // Bulk selection states
  const [selectedIds, setSelectedIds] = useState([]);
  const [bulkCategory, setBulkCategory] = useState('');
  
  // Inline edit state: { txId, field, originalValue }
  const [editing, setEditing] = useState(null);
  const [editValue, setEditValue] = useState('');

  // Fetch categories
  useEffect(() => {
    const fetchCats = async () => {
      try {
        const data = await getCategories();
        setCategories(data.categories || []);
      } catch (err) {
        console.error('Failed to load categories:', err);
      }
    };
    fetchCats();
  }, []);

  // Fetch transactions (debounced for search)
  const fetchTransactions = useCallback(async () => {
    setLoading(true);
    try {
      const params = {
        page,
        per_page: 50,
        search,
        category: categoryFilter,
        date_from: dateFrom,
        date_to: dateTo,
        uncategorized_only: uncategorizedOnly,
      };
      
      const data = await getTransactions(params);
      setTransactions(data.transactions || []);
      setTotal(data.total || 0);
      setPages(data.pages || 1);
    } catch (err) {
      showToast(err.message || 'Failed to load transactions', 'error');
    } finally {
      setLoading(false);
    }
  }, [page, search, categoryFilter, dateFrom, dateTo, uncategorizedOnly, showToast]);

  // Trigger search with 300ms debounce
  useEffect(() => {
    const handler = setTimeout(() => {
      fetchTransactions();
    }, 300);
    return () => clearTimeout(handler);
  }, [search, categoryFilter, dateFrom, dateTo, uncategorizedOnly, page, fetchTransactions]);

  // Reset page when filters change
  useEffect(() => {
    setPage(1);
    setSelectedIds([]);
  }, [search, categoryFilter, dateFrom, dateTo, uncategorizedOnly]);

  const resetFilters = () => {
    setSearch('');
    setCategoryFilter('');
    setDateFrom('');
    setDateTo('');
    setUncategorizedOnly(false);
    setPage(1);
    setSelectedIds([]);
    showToast('Đã xóa tất cả bộ lọc', 'success');
  };

  const toggleUncategorizedQueue = () => {
    setUncategorizedOnly(prev => !prev);
  };

  // Inline edit logic
  const startEditing = (txId, field, currentValue) => {
    setEditing({ txId, field });
    setEditValue(currentValue);
  };

  const cancelEditing = () => {
    setEditing(null);
    setEditValue('');
  };

  const saveInlineEdit = async (txId, field) => {
    const trimmedVal = editValue.trim();
    if (!trimmedVal) {
      cancelEditing();
      return;
    }
    
    try {
      const body = {};
      body[field] = trimmedVal;
      await updateTransaction(txId, body);
      showToast(`Đã cập nhật ${field === 'category' ? 'danh mục' : 'nơi giao dịch'}`);
      
      // Update local state to avoid refetching
      setTransactions(prev => prev.map(t => {
        if (t.id === txId) {
          return { ...t, [field === 'merchant' ? 'merchant' : 'category']: trimmedVal };
        }
        return t;
      }));
    } catch (err) {
      showToast(err.message || 'Failed to save changes', 'error');
    } finally {
      cancelEditing();
    }
  };

  // Quick Category Assignment
  const applyQuickCategory = async (txId, category) => {
    if (!category) return;
    try {
      await updateTransaction(txId, { category });
      showToast('Đã cập nhật danh mục');
      setTransactions(prev => prev.map(t => {
        if (t.id === txId) {
          return { ...t, category };
        }
        return t;
      }));
    } catch (err) {
      showToast(err.message || 'Cập nhật danh mục thất bại', 'error');
    }
  };

  // Bulk Actions
  const handleCheckboxChange = (txId, checked) => {
    if (checked) {
      setSelectedIds(prev => [...prev, txId]);
    } else {
      setSelectedIds(prev => prev.filter(id => id !== txId));
    }
  };

  const toggleSelectAllVisible = () => {
    const visibleUncatIds = transactions
      .filter(t => t.category === 'Chưa phân loại')
      .map(t => t.id);
      
    if (selectedIds.length === visibleUncatIds.length) {
      setSelectedIds([]);
    } else {
      setSelectedIds(visibleUncatIds);
    }
  };

  const applyBulkCategoryAction = async () => {
    if (!selectedIds.length) {
      showToast('Hãy chọn ít nhất một giao dịch chưa phân loại', 'info');
      return;
    }
    if (!bulkCategory) {
      showToast('Hãy chọn danh mục áp dụng', 'error');
      return;
    }

    try {
      const result = await bulkUpdateCategory(selectedIds, bulkCategory, true);
      showToast(`Đã cập nhật ${result.updated} giao dịch`);
      setSelectedIds([]);
      setBulkCategory('');
      fetchTransactions();
    } catch (err) {
      showToast(err.message || 'Cập nhật hàng loạt thất bại', 'error');
    }
  };

  // UI Helpers
  const formatCurrency = (amount) => {
    try {
      return new Intl.NumberFormat('vi-VN', {
        style: 'currency',
        currency: currency || 'EUR',
      }).format(amount);
    } catch {
      return `${amount} ${currency || 'EUR'}`;
    }
  };

  const getCategoryColor = (cat) => {
    const colors = {
      'Đăng ký định kỳ': '#2EAADC', 'Ăn uống': '#D9730D',
      'Di chuyển': '#448361', 'Mua sắm': '#9B51E0', 'Du lịch': '#337EA9',
      'Sức khỏe': '#E16259', 'Bảo hiểm': '#6940A5', 'Điện nước': '#CC8E22',
      'Lương': '#0F7B6C', 'Thu nhập': '#0F7B6C', 'Giải trí': '#AD1A72',
      'Giáo dục': '#6C6C6C', 'Khác': '#D44C47', 'Tiền mặt': '#0F7B6C',
      'Hoàn tiền': '#448361', 'Chuyển khoản': '#0F7B6C',
    };
    return colors[cat] || 'var(--text-muted, #787774)';
  };

  const activeFilters = () => {
    let count = 0;
    if (search) count += 1;
    if (categoryFilter && !uncategorizedOnly) count += 1;
    if (dateFrom) count += 1;
    if (dateTo) count += 1;
    return count;
  };

  const activeFiltersCount = activeFilters();
  const allVisibleUncat = transactions.filter(t => t.category === 'Chưa phân loại');

  return (
    <div className="page-transactions-root">
      <div className="page-header">
        <div>
          <h1 className="page-title">Giao dịch</h1>
          <p className="page-subtitle" id="txSubtitle">
            {uncategorizedOnly 
              ? `Chế độ duyệt chưa phân loại — ${total} giao dịch` 
              : 'Xem, tìm kiếm và chỉnh sửa nơi giao dịch hoặc danh mục ngay trong sổ giao dịch.'}
          </p>
        </div>
        <div className="page-header-actions">
          <Link to="/upload" className="btn btn-secondary btn-sm">Tải thêm</Link>
        </div>
      </div>

      <div className="table-container">
        <div className="table-toolbar">
          <input 
            type="text" 
            placeholder="Tìm merchant..." 
            style={{ flex: 1, maxWidth: '260px' }}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select 
            value={categoryFilter} 
            onChange={(e) => setCategoryFilter(e.target.value)}
            disabled={uncategorizedOnly}
          >
            <option value="">Tất cả danh mục</option>
            {categories.map((c, i) => (
              <option key={i} value={c}>{c}</option>
            ))}
          </select>
          <input 
            type="date" 
            title="Từ ngày"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
          />
          <input 
            type="date" 
            title="Đến ngày"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
          />
          <button className="btn btn-secondary btn-sm" type="button" onClick={resetFilters}>
            Xóa bộ lọc
          </button>
          <button 
            className="btn btn-secondary btn-sm" 
            id="uncatToggleBtn" 
            type="button" 
            onClick={toggleUncategorizedQueue}
          >
            Duyệt chưa phân loại: {uncategorizedOnly ? 'BẬT' : 'TẮT'}
          </button>
        </div>

        <div className="results-summary">
          <div className="results-summary-badges">
            <span className="settings-badge local">{total} kết quả</span>
            <span className="settings-badge">
              {activeFiltersCount ? `${activeFiltersCount} bộ lọc đang bật` : 'Không có bộ lọc'}
            </span>
            {uncategorizedOnly && (
              <span className="settings-badge warning">Dọn dẹp hòm thư</span>
            )}
          </div>
          <div className="table-cell-muted">
            {uncategorizedOnly 
              ? 'Chỉ hiển thị giao dịch chưa phân loại giúp bạn dọn dẹp tài chính nhanh hơn.' 
              : activeFiltersCount 
                ? 'Đang hiển thị các giao dịch phù hợp với bộ lọc hiện tại.' 
                : 'Click trực tiếp vào nơi giao dịch hoặc danh mục để chỉnh sửa nhanh.'}
          </div>
        </div>

        {uncategorizedOnly && transactions.length > 0 && (
          <div className="uncategorized-queue">
            <div className="uncat-queue-info">
              {total} giao dịch chưa phân loại trong bộ lọc hiện tại
            </div>
            <div className="uncat-queue-actions">
              <button 
                className="btn btn-secondary btn-sm" 
                type="button" 
                onClick={toggleSelectAllVisible}
                disabled={allVisibleUncat.length === 0}
              >
                {selectedIds.length === allVisibleUncat.length && allVisibleUncat.length > 0 
                  ? 'Bỏ chọn tất cả' 
                  : 'Chọn tất cả đang hiển thị'}
              </button>
              <select 
                className="settings-select"
                value={bulkCategory}
                onChange={(e) => setBulkCategory(e.target.value)}
              >
                <option value="">Chọn danh mục...</option>
                {categories.map((c, i) => (
                  <option key={i} value={c}>{c}</option>
                ))}
              </select>
              <button 
                className="btn btn-primary btn-sm" 
                type="button" 
                onClick={applyBulkCategoryAction}
              >
                Áp dụng cho mục đã chọn
              </button>
            </div>
          </div>
        )}

        <div id="tableBody">
          {loading ? (
            <div className="empty-state">
              <div className="icon">📋</div>
              <h3>Đang tải...</h3>
            </div>
          ) : transactions.length === 0 ? (
            <div className="empty-state">
              <div className="icon">📋</div>
              <h3>{activeFiltersCount || uncategorizedOnly ? 'Không tìm thấy giao dịch' : 'Sổ giao dịch trống'}</h3>
              <p>
                {activeFiltersCount || uncategorizedOnly 
                  ? 'Thử xóa bộ lọc hoặc tắt chế độ Inbox Zero.' 
                  : 'Tải tệp sao kê ngân hàng của bạn lên để bắt đầu.'}
              </p>
              {activeFiltersCount || uncategorizedOnly ? (
                <button className="btn btn-secondary" type="button" onClick={resetFilters} style={{ marginTop: '16px' }}>
                  Xóa bộ lọc
                </button>
              ) : (
                <Link to="/upload" className="btn btn-primary" style={{ marginTop: '16px' }}>
                  📥 Tải giao dịch lên
                </Link>
              )}
            </div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th style={{ width: '40px' }}>✓</th>
                  <th>Ngày</th>
                  <th>Nơi giao dịch</th>
                  <th>Danh mục</th>
                  <th style={{ textAlign: 'right' }}>Số tiền</th>
                </tr>
              </thead>
              <tbody>
                {transactions.map((t) => {
                  const isExpense = t.amount < 0;
                  const isUncat = t.category === 'Chưa phân loại';
                  const isEditingMerchant = editing?.txId === t.id && editing?.field === 'merchant';
                  const isEditingCategory = editing?.txId === t.id && editing?.field === 'category';

                  return (
                    <tr key={t.id}>
                      <td>
                        {isUncat && (
                          <input 
                            type="checkbox" 
                            className="uncategorized-check"
                            checked={selectedIds.includes(t.id)}
                            onChange={(e) => handleCheckboxChange(t.id, e.target.checked)}
                            aria-label="Select transaction"
                          />
                        )}
                      </td>
                      <td>{t.date}</td>
                      <td>
                        {isEditingMerchant ? (
                          <input
                            className="edit-input"
                            value={editValue}
                            onChange={(e) => setEditValue(e.target.value)}
                            onBlur={() => saveInlineEdit(t.id, 'merchant')}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') saveInlineEdit(t.id, 'merchant');
                              if (e.key === 'Escape') cancelEditing();
                            }}
                            autoFocus
                          />
                        ) : (
                          <span 
                            className="editable" 
                            onClick={() => startEditing(t.id, 'merchant', t.merchant)}
                          >
                            {t.merchant}
                          </span>
                        )}
                      </td>
                      <td>
                        {isEditingCategory ? (
                          <select
                            className="settings-select preview-select"
                            value={editValue}
                            onChange={(e) => setEditValue(e.target.value)}
                            onBlur={() => saveInlineEdit(t.id, 'category')}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') saveInlineEdit(t.id, 'category');
                              if (e.key === 'Escape') cancelEditing();
                            }}
                            autoFocus
                          >
                            <option value="Chưa phân loại">Chưa phân loại</option>
                            {categories.map((c, i) => (
                              <option key={i} value={c}>{c}</option>
                            ))}
                          </select>
                        ) : (
                          <>
                            <span 
                              className={`badge ${isUncat ? 'badge-uncategorized' : ''}`}
                              onClick={() => startEditing(t.id, 'category', t.category)}
                            >
                              {!isUncat && (
                                <span 
                                  className="badge-dot" 
                                  style={{ background: getCategoryColor(t.category) }}
                                ></span>
                              )}
                              {t.category}
                            </span>
                            {isUncat && (
                              <div className="quick-category-wrap">
                                <select 
                                  className="quick-category-select" 
                                  onChange={(e) => applyQuickCategory(t.id, e.target.value)}
                                  value=""
                                >
                                  <option value="">Phân loại nhanh...</option>
                                  {categories.map((c, i) => (
                                    <option key={i} value={c}>{c}</option>
                                  ))}
                                </select>
                              </div>
                            )}
                          </>
                        )}
                      </td>
                      <td className={`amount ${isExpense ? 'expense' : 'income'}`} style={{ textAlign: 'right' }}>
                        {formatCurrency(t.amount)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {pages > 1 && (
          <div className="pagination">
            <button 
              disabled={page <= 1} 
              onClick={() => setPage(p => p - 1)}
            >
              ← Trước
            </button>
            <span className="pagination-info">Trang {page} / {pages}</span>
            <button 
              disabled={page >= pages} 
              onClick={() => setPage(p => p + 1)}
            >
              Sau →
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
