import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import { getBudget, updateBudgetLimit } from '../api/services';

export default function Budget() {
  const { currency, showToast } = useApp();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  // Edit State: { category, value }
  const [editing, setEditing] = useState(null);
  const [editValue, setEditValue] = useState('');

  const fetchBudget = async () => {
    setLoading(true);
    try {
      const result = await getBudget();
      setData(result);
    } catch (err) {
      console.error('Failed to load budget data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBudget();
  }, []);

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

  const handleEditStart = (category, currentLimit) => {
    setEditing(category);
    setEditValue(currentLimit !== null ? currentLimit.toString() : '');
  };

  const handleEditCancel = () => {
    setEditing(null);
    setEditValue('');
  };

  const handleEditSave = async (category) => {
    const val = parseFloat(editValue);
    if (isNaN(val) || val < 0) {
      handleEditCancel();
      return;
    }

    try {
      await updateBudgetLimit(category, val);
      showToast(`Hạn mức cho ${category} đã đặt thành ${formatCurrency(val)}`, 'success');
      
      // Update local state to avoid refetching
      setData(prev => {
        if (!prev) return prev;
        
        const updatedItems = prev.items.map(item => {
          if (item.category === category) {
            const spent = item.spent;
            const limit = val;
            let pct = null;
            let status = 'none';

            if (limit > 0) {
              pct = Math.round((spent / limit) * 100 * 10) / 10;
              status = pct >= 100 ? 'red' : pct >= 80 ? 'yellow' : 'green';
            }

            return { ...item, limit, pct, status };
          }
          return item;
        });

        // Recompute summary
        const on_track = updatedItems.filter(i => i.status === 'green').length;
        const over = updatedItems.filter(i => i.status === 'red').length;
        const no_limit = updatedItems.filter(i => i.status === 'none').length;

        return {
          ...prev,
          items: updatedItems,
          summary: { on_track, over, no_limit }
        };
      });
    } catch (err) {
      showToast(err.message || 'Cập nhật hạn mức thất bại', 'error');
    } finally {
      handleEditCancel();
    }
  };

  if (loading && !data) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
        <div className="processing-inline-card" style={{ width: '100%', maxWidth: '400px', textAlign: 'center' }}>
          <div style={{ fontSize: '24px', marginBottom: '8px' }}>⏳</div>
          <h3>Đang tải dữ liệu ngân sách...</h3>
        </div>
      </div>
    );
  }

  const {
    current_cycle = null,
    items = [],
    summary = { on_track: 0, over: 0, no_limit: 0 }
  } = data || {};

  return (
    <div className="page-budget-root">
      <h1 className="page-title">Ngân sách</h1>
      <p className="page-subtitle" id="budgetSubtitle">
        {current_cycle?.label || 'Hạn mức chi tiêu hàng tháng'}
      </p>

      {/* Summary stats */}
      <div className="cards" id="budgetSummary">
        <div className="card">
          <div className="card-label">Trong hạn mức</div>
          <div className="card-value positive">{summary.on_track}</div>
        </div>
        <div className="card">
          <div className="card-label">Vượt ngân sách</div>
          <div className="card-value negative">{summary.over}</div>
        </div>
        <div className="card">
          <div className="card-label">Chưa đặt hạn mức</div>
          <div className="card-value neutral">{summary.no_limit}</div>
        </div>
      </div>

      {/* Grid of cards */}
      <div className="budget-grid" id="budgetGrid">
        {items.length === 0 ? (
          <div className="empty-state">
            <div className="icon">💰</div>
            <h3>Chưa có dữ liệu chi tiêu</h3>
            <p>Tải tệp giao dịch lên để lập ngân sách chi tiêu</p>
            <Link to="/upload" className="btn btn-primary" style={{ marginTop: '16px' }}>
              📥 Tải giao dịch lên
            </Link>
          </div>
        ) : (
          items.map((item, i) => {
            const statusIcons = { green: '🟢', yellow: '🟡', red: '🔴', none: '⚪' };
            const icon = statusIcons[item.status] || '⚪';
            const pctDisplay = item.pct !== null ? `${item.pct}%` : '—';
            const barPct = item.pct !== null ? Math.min(item.pct, 100) : 0;
            const isEditing = editing === item.category;

            return (
              <div 
                key={item.category} 
                className="budget-card" 
                style={{ animationDelay: `${i * 0.05}s` }}
              >
                <div className="budget-card-header">
                  <span className="budget-category">{item.category}</span>
                  <span className="budget-status-icon">{icon}</span>
                </div>
                <div className="budget-amounts">
                  <span className={`budget-spent status-${item.status}`}>
                    {formatCurrency(item.spent)}
                  </span>
                  <span className="budget-sep"> / </span>
                  {isEditing ? (
                    <input
                      type="number"
                      className="edit-input"
                      style={{ width: '100px', display: 'inline-block' }}
                      value={editValue}
                      onChange={(e) => setEditValue(e.target.value)}
                      onBlur={() => handleEditSave(item.category)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleEditSave(item.category);
                        if (e.key === 'Escape') handleEditCancel();
                      }}
                      placeholder="vd: 300"
                      autoFocus
                    />
                  ) : (
                    <span 
                      className="budget-limit-display" 
                      onClick={() => handleEditStart(item.category, item.limit)}
                      title="Click để đặt hạn mức"
                      style={{ cursor: 'pointer' }}
                    >
                      {item.limit ? formatCurrency(item.limit) : 'Đặt hạn mức'}
                    </span>
                  )}
                </div>
                <div className="progress-track">
                  <div 
                    className={`progress-fill status-${item.status}`}
                    style={{ width: `${barPct}%` }}
                  ></div>
                </div>
                <div className="budget-pct">{pctDisplay}</div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
