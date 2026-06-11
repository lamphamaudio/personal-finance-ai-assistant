import { useState, useEffect, useCallback } from 'react';
import { useApp } from '../context/AppContext';
import { getSubscriptions } from '../api/services';

export default function Subscriptions() {
  const { currency, swrFetch } = useApp();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  
  // Sort State
  const [sortKey, setSortKey] = useState('monthly_estimate');
  const [sortDirection, setSortDirection] = useState('desc');

  const fetchSubscriptions = useCallback(() => {
    swrFetch(
      'subscriptions',
      getSubscriptions,
      (result) => {
        setData(result);
        setLoading(false);
      },
      (err) => {
        console.error('Failed to load subscriptions:', err);
        setLoading(false);
      }
    );
  }, [swrFetch]);

  useEffect(() => {
    setLoading(true);
    fetchSubscriptions();
  }, [fetchSubscriptions]);

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

  const formatSpectraDate = (dateString, options = { day: 'numeric', month: 'short', year: 'numeric' }) => {
    try {
      return new Date(`${dateString}T00:00:00`).toLocaleDateString('vi-VN', options);
    } catch {
      return dateString;
    }
  };

  const cadenceLabel = (days) => {
    if (days <= 8) return 'Hàng tuần';
    if (days <= 40) return 'Hàng tháng';
    if (days >= 300) return 'Hàng năm';
    return 'Tùy chỉnh';
  };

  const cadenceClass = (days) => {
    if (days <= 8) return 'cadence-weekly';
    if (days <= 40) return 'cadence-monthly';
    if (days >= 300) return 'cadence-yearly';
    return 'cadence-custom';
  };

  // Sorting logic
  const handleSort = (key) => {
    if (sortKey === key) {
      setSortDirection(prev => prev === 'asc' ? 'desc' : 'asc');
    } else {
      setSortKey(key);
      setSortDirection(key === 'merchant' ? 'asc' : 'desc');
    }
  };

  const getSortIndicator = (key) => {
    if (sortKey !== key) return '↕';
    return sortDirection === 'asc' ? '↑' : '↓';
  };

  const getSortedItems = (items) => {
    if (!items || !items.length) return [];
    const sorted = [...items];
    const factor = sortDirection === 'asc' ? 1 : -1;

    sorted.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      
      if (typeof av === 'number' && typeof bv === 'number') {
        return (av - bv) * factor;
      }
      return String(av || '').localeCompare(String(bv || '')) * factor;
    });

    return sorted;
  };

  const renderChangeBadge = (item) => {
    if (!item.price_change_direction) {
      return <span className="table-cell-muted">Ổn định</span>;
    }

    const sign = item.change_amount > 0 ? '+' : '';
    const cls = item.price_change_direction === 'up' ? 'warning' : 'local';
    return (
      <span className={`settings-badge ${cls}`}>
        {sign}{formatCurrency(item.change_amount)} · {sign}{item.change_pct}%
      </span>
    );
  };

  if (loading && !data) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
        <div className="processing-inline-card" style={{ width: '100%', maxWidth: '400px', textAlign: 'center' }}>
          <div style={{ fontSize: '24px', marginBottom: '8px' }}>🔁</div>
          <h3>Đang tải các khoản định kỳ...</h3>
        </div>
      </div>
    );
  }

  const {
    items = [],
    summary = { active_count: 0, monthly_estimate: 0, annual_projection: 0, in_current_cycle: 0, price_change_count: 0 },
    current_cycle = null
  } = data || {};

  const sortedItems = getSortedItems(items);

  return (
    <div className="page-subscriptions-root">
      <h1 className="page-title">Định kỳ</h1>
      <p className="page-subtitle" id="subscriptionsSubtitle">
        {current_cycle?.label || 'Danh sách khoản chi tiêu định kỳ'}
      </p>

      {/* Subscription Cards */}
      <div className="cards" id="subscriptionsCards">
        <div className="card">
          <div className="card-label">Đang hoạt động</div>
          <div className="card-value neutral">{summary.active_count}</div>
        </div>
        <div className="card">
          <div className="card-label">Ước tính hàng tháng</div>
          <div className="card-value warning">{formatCurrency(summary.monthly_estimate)}</div>
        </div>
        <div className="card">
          <div className="card-label">Dự kiến hàng năm</div>
          <div className="card-value negative">{formatCurrency(summary.annual_projection)}</div>
        </div>
        <div className="card">
          <div className="card-label">Chu kỳ này</div>
          <div className="card-value neutral">{formatCurrency(summary.in_current_cycle)}</div>
        </div>
        <div className="card">
          <div className="card-label">Thay đổi giá</div>
          <div className="card-value warning">{summary.price_change_count}</div>
        </div>
      </div>

      {summary.price_change_count > 0 && (
        <div className="inline-banner" style={{ display: 'flex', marginBottom: '24px' }}>
          <strong>Phát hiện thay đổi giá thuê bao</strong>
          <span>
            {summary.price_change_count} dịch vụ định kỳ đã thay đổi mức phí so với trung bình lịch sử chi tiêu của bạn.
          </span>
        </div>
      )}

      <div className="table-container">
        <div id="subscriptionsTableBody">
          {items.length === 0 ? (
            <div className="empty-state">
              <div className="icon">🔁</div>
              <h3>Không tìm thấy khoản định kỳ nào</h3>
              <p>Hệ thống sẽ tự động phát hiện và tổng hợp các khoản phí định kỳ khi có giao dịch liên quan.</p>
            </div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th className="sortable" onClick={() => handleSort('merchant')}>
                    Nơi giao dịch <span className="sort-indicator">{getSortIndicator('merchant')}</span>
                  </th>
                  <th className="sortable" onClick={() => handleSort('cadence_days')}>
                    Tần suất <span className="sort-indicator">{getSortIndicator('cadence_days')}</span>
                  </th>
                  <th className="sortable" onClick={() => handleSort('last_charge_date')}>
                    Lần cuối thanh toán <span className="sort-indicator">{getSortIndicator('last_charge_date')}</span>
                  </th>
                  <th className="sortable" onClick={() => handleSort('next_estimated_date')}>
                    Dự kiến tiếp theo <span className="sort-indicator">{getSortIndicator('next_estimated_date')}</span>
                  </th>
                  <th>Biến động giá</th>
                  <th className="sortable" style={{ textAlign: 'right' }} onClick={() => handleSort('monthly_estimate')}>
                    Hàng tháng <span className="sort-indicator">{getSortIndicator('monthly_estimate')}</span>
                  </th>
                  <th className="sortable" style={{ textAlign: 'right' }} onClick={() => handleSort('in_current_cycle')}>
                    Chu kỳ này <span className="sort-indicator">{getSortIndicator('in_current_cycle')}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {sortedItems.map((item, idx) => (
                  <tr key={idx}>
                    <td>{item.merchant}</td>
                    <td>
                      <span className={`cadence-badge ${cadenceClass(item.cadence_days)}`}>
                        {cadenceLabel(item.cadence_days)}
                      </span>
                      <span className="cadence-days">{item.cadence_days} ngày</span>
                    </td>
                    <td>{formatSpectraDate(item.last_charge_date)}</td>
                    <td>{formatSpectraDate(item.next_estimated_date)}</td>
                    <td>{renderChangeBadge(item)}</td>
                    <td style={{ textAlign: 'right', fontWeight: 600 }}>{formatCurrency(item.monthly_estimate)}</td>
                    <td style={{ textAlign: 'right', fontWeight: 600 }}>{formatCurrency(item.in_current_cycle)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
