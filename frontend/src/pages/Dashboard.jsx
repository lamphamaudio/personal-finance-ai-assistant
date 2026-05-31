import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import { getSummary } from '../api/services';
import { Doughnut, Bar } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  ArcElement,
  Tooltip as ChartTooltip,
  Legend as ChartLegend,
  CategoryScale,
  LinearScale,
  BarElement,
  Title as ChartTitle,
} from 'chart.js';

// Register ChartJS elements
ChartJS.register(
  ArcElement,
  ChartTooltip,
  ChartLegend,
  CategoryScale,
  LinearScale,
  BarElement,
  ChartTitle
);

export default function Dashboard() {
  const { currency, effectiveTheme, swrFetch } = useApp();
  const [scope, setScope] = useState(() => {
    try {
      const stored = localStorage.getItem('spectra-summary-scope');
      return ['cycle', '90d', 'ytd'].includes(stored) ? stored : 'cycle';
    } catch {
      return 'cycle';
    }
  });

  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);

  const fetchSummary = useCallback((currentScope) => {
    swrFetch(
      `summary_${currentScope}`,
      () => getSummary(currentScope),
      (result) => {
        setData(result);
        setLoading(false);
      },
      (err) => {
        console.error('Failed to load summary:', err);
        setLoading(false);
      }
    );
  }, [swrFetch]);

  useEffect(() => {
    setLoading(true);
    fetchSummary(scope);
  }, [scope, fetchSummary]);

  const handleScopeChange = (e) => {
    const newScope = e.target.value;
    setScope(newScope);
    try {
      localStorage.setItem('spectra-summary-scope', newScope);
    } catch {}
  };

  // Utilities for formatting
  const formatCurrency = (amount, customCurrency) => {
    const targetCurrency = customCurrency || currency || 'EUR';
    try {
      return new Intl.NumberFormat('vi-VN', {
        style: 'currency',
        currency: targetCurrency,
      }).format(amount);
    } catch {
      return `${amount} ${targetCurrency}`;
    }
  };

  const parseSpectraDate = (dateString) => {
    return new Date(`${dateString}T00:00:00`);
  };

  const formatSpectraDate = (dateString, options = { day: 'numeric', month: 'short', year: 'numeric' }) => {
    try {
      return parseSpectraDate(dateString).toLocaleDateString('vi-VN', options);
    } catch {
      return dateString;
    }
  };

  const formatCycleRange = (startDate, endExclusiveDate, options = { day: 'numeric', month: 'short', year: 'numeric' }) => {
    try {
      const endDate = parseSpectraDate(endExclusiveDate);
      endDate.setDate(endDate.getDate() - 1);
      return `${parseSpectraDate(startDate).toLocaleDateString('vi-VN', options)} -> ${endDate.toLocaleDateString('vi-VN', options)}`;
    } catch {
      return `${startDate} -> ${endExclusiveDate}`;
    }
  };

  // Colors & Fonts derived from style.css
  const getThemeVars = () => {
    const cssVar = (name, fallback = '') => {
      return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
    };

    return {
      fontFamily: cssVar('--font', 'Inter, sans-serif'),
      textColor: cssVar('--text', '#111827'),
      mutedColor: cssVar('--text-muted', '#6B7280'),
      gridColor: cssVar('--chart-grid', '#F1F5F9'),
      accent: cssVar('--accent', '#4F46E5'),
      palette: [
        cssVar('--accent', '#4F46E5'),
        cssVar('--positive', '#059669'),
        cssVar('--warning', '#D97706'),
        cssVar('--negative', '#DC2626'),
        cssVar('--purple', '#7C3AED'),
        '#0EA5E9',
        '#DB2777',
        '#EA580C',
        '#65A30D',
        '#0891B2',
        '#9333EA',
        '#B45309',
        '#BE123C',
        '#4B5563',
      ],
      bgElevated: cssVar('--bg-elevated', '#ffffff'),
      border: cssVar('--border', '#e5e7eb'),
    };
  };

  // Build Charts Configs
  const [chartTheme, setChartTheme] = useState(null);

  useEffect(() => {
    // Wait for the DOM to update dataset-theme
    const timer = setTimeout(() => {
      setChartTheme(getThemeVars());
    }, 50);
    return () => clearTimeout(timer);
  }, [effectiveTheme, data]);

  if (loading && !data) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
        <div className="processing-inline-card" style={{ width: '100%', maxWidth: '400px', textAlign: 'center' }}>
          <div style={{ fontSize: '24px', marginBottom: '8px' }}>📊</div>
          <h3>Đang tải dữ liệu tổng quan...</h3>
          <p className="table-cell-muted">Spectra đang truy vấn thống kê tài chính của bạn</p>
        </div>
      </div>
    );
  }

  const {
    total_spent = 0,
    total_income = 0,
    subscriptions = 0,
    uncategorized = 0,
    uncategorized_total = 0,
    by_category = {},
    monthly = {},
    monthly_ranges = {},
    top_merchants = [],
    scope_label = '',
    current_cycle = null,
    has_data = false,
    burn_rate = null,
    insights = [],
  } = data || {};

  const uncatDisplayValue = Number.isInteger(uncategorized_total) ? uncategorized_total : uncategorized;

  // Chart configuration
  let doughnutData = { labels: [], datasets: [] };
  let doughnutOptions = {};
  let barData = { labels: [], datasets: [] };
  let barOptions = {};

  if (chartTheme && has_data) {
    // 1. Doughnut chart (by category)
    const catLabels = Object.keys(by_category);
    const catValues = Object.values(by_category);
    
    doughnutData = {
      labels: catLabels,
      datasets: [
        {
          data: catValues,
          backgroundColor: chartTheme.palette.slice(0, catLabels.length),
          borderWidth: 2,
          borderColor: chartTheme.bgElevated,
          hoverOffset: 8,
          hoverBorderWidth: 0,
          spacing: 2,
        },
      ],
    };

    doughnutOptions = {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 600, easing: 'easeOutQuart' },
      plugins: {
        legend: {
          position: 'right',
          labels: {
            color: chartTheme.mutedColor,
            font: { family: chartTheme.fontFamily, size: 12, weight: '500' },
            padding: 14,
            usePointStyle: true,
            pointStyleWidth: 8,
          },
        },
        tooltip: {
          backgroundColor: chartTheme.bgElevated,
          titleColor: chartTheme.textColor,
          bodyColor: chartTheme.mutedColor,
          borderColor: chartTheme.border,
          borderWidth: 1,
          padding: 12,
          cornerRadius: 8,
          callbacks: {
            label: (ctx) => {
              const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
              const pct = total > 0 ? Math.round((ctx.parsed / total) * 100) : 0;
              return ` ${formatCurrency(ctx.parsed)} (${pct}%)`;
            },
          },
        },
      },
      cutout: '70%',
    };

    // 2. Bar chart (monthly trends)
    const periodKeys = Object.keys(monthly);
    const monthLabels = periodKeys.map((startDate) => {
      if (scope === 'cycle') {
        return formatSpectraDate(startDate, { day: 'numeric', month: 'short' });
      }
      return formatSpectraDate(startDate, { month: 'short', year: '2-digit' });
    });
    const monthValues = Object.values(monthly);

    barData = {
      labels: monthLabels,
      datasets: [
        {
          label: 'Chi tiêu',
          data: monthValues,
          backgroundColor: chartTheme.accent + 'CC',
          hoverBackgroundColor: chartTheme.accent,
          borderRadius: 8,
          borderSkipped: false,
          borderWidth: 0,
        },
      ],
    };

    barOptions = {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 500, easing: 'easeOutCubic' },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: chartTheme.bgElevated,
          titleColor: chartTheme.textColor,
          bodyColor: chartTheme.mutedColor,
          borderColor: chartTheme.border,
          borderWidth: 1,
          padding: 12,
          cornerRadius: 8,
          callbacks: {
            title: (context) => {
              const key = periodKeys[context[0].dataIndex];
              const range = monthly_ranges?.[key];
              if (!range) {
                return monthLabels[context[0].dataIndex];
              }
              return formatCycleRange(range.start, range.end, { day: 'numeric', month: 'short', year: 'numeric' });
            },
            label: (ctx) => ` ${formatCurrency(ctx.parsed.y)}`,
          },
        },
      },
      scales: {
        y: {
          beginAtZero: true,
          ticks: {
            color: chartTheme.mutedColor,
            font: { family: chartTheme.fontFamily, size: 11, weight: '500' },
            callback: (v) => formatCurrency(v),
          },
          grid: { color: chartTheme.gridColor, lineWidth: 1 },
          border: { display: false },
        },
        x: {
          ticks: {
            color: chartTheme.mutedColor,
            font: { family: chartTheme.fontFamily, size: 11 },
            maxRotation: 0,
          },
          grid: { display: false },
          border: { display: false },
        },
      },
    };
  }

  return (
    <div className="page-dashboard-root">
      <div className="page-header">
        <div>
          <h1 className="page-title">Tổng quan</h1>
          <p className="page-subtitle" id="subtitle">
            {!has_data ? 'Chưa có dữ liệu' : (scope_label || current_cycle?.label || 'Kỳ đã chọn')}
          </p>
        </div>
        <div className="page-header-actions">
          <Link to="/upload" className="btn btn-secondary btn-sm">Tải lên</Link>
          <Link to="/transactions" className="btn btn-secondary btn-sm">Giao dịch</Link>
        </div>
      </div>

      <div className="dashboard-controls">
        <label htmlFor="summaryScope" className="dashboard-controls-label">Kỳ</label>
        <select 
          id="summaryScope" 
          className="settings-select dashboard-scope-select"
          value={scope}
          onChange={handleScopeChange}
        >
          <option value="cycle">Chu kỳ hiện tại</option>
          <option value="90d">90 ngày gần nhất</option>
          <option value="ytd">Từ đầu năm</option>
        </select>
      </div>

      <div className="cards" id="cards">
        <div className="card">
          <div className="card-label">
            {scope === 'cycle' ? 'Chi tiêu chu kỳ' : scope === '90d' ? 'Chi tiêu 90 ngày' : 'Chi tiêu từ đầu năm'}
          </div>
          <div className="card-value negative">{formatCurrency(total_spent)}</div>
        </div>
        <div className="card">
          <div className="card-label">
            {scope === 'cycle' ? 'Thu nhập chu kỳ' : scope === '90d' ? 'Thu nhập 90 ngày' : 'Thu nhập từ đầu năm'}
          </div>
          <div className="card-value positive">{formatCurrency(total_income)}</div>
        </div>
        <div className="card">
          <div className="card-label">Định kỳ</div>
          <div className="card-value neutral">{formatCurrency(subscriptions)}</div>
        </div>
        <div className="card">
          <div className="card-label">Chưa phân loại</div>
          <div className="card-value warning">{uncatDisplayValue}</div>
        </div>
      </div>

      {scope === 'cycle' && burn_rate && has_data && (
        <div className="burn-rate" id="burnRateBox">
          <div className="burn-rate-label">Dự báo chu kỳ</div>
          <div className="burn-rate-main">
            {formatCurrency(burn_rate.projected_total)} dự kiến khi hết chu kỳ
          </div>
          <div className="burn-rate-meta">
            {formatCurrency(burn_rate.daily_spend)}/ngày · {burn_rate.elapsed_days}/{burn_rate.total_days} ngày đã qua · {burn_rate.remaining_days} ngày còn lại
          </div>
        </div>
      )}

      {insights.length > 0 && (
        <div className="insights-panel" id="insightsPanel">
          <div className="insights-panel-header">
            <h3>Tín hiệu cần chú ý</h3>
            <span className="table-cell-muted">Những thay đổi và mục nên xem lại</span>
          </div>
          <div className="insights-list" id="insightsList">
            {insights.map((item, index) => (
              <Link 
                key={index} 
                className={`insight-card insight-${item.severity || 'info'}`} 
                to={item.href || '#'}
              >
                <div className="insight-title">{item.title}</div>
                <div className="insight-detail">{item.detail}</div>
              </Link>
            ))}
          </div>
        </div>
      )}

      {!has_data && (
        <div className="empty-state" style={{ margin: '0 0 24px' }}>
          <div className="icon">📊</div>
          <h3>Bảng tổng quan đang trống</h3>
          <p>Tải file sao kê ngân hàng để xem phân tích chi tiêu</p>
          <Link to="/upload" className="btn btn-primary" style={{ marginTop: '16px' }}>
            📥 Tải giao dịch lên
          </Link>
        </div>
      )}

      {has_data && (
        <>
          <div className="charts-row">
            <div className="chart-box">
              <h3>Chi tiêu theo danh mục</h3>
              <div style={{ height: '260px', position: 'relative' }}>
                {chartTheme && <Doughnut data={doughnutData} options={doughnutOptions} />}
              </div>
            </div>
            <div className="chart-box">
              <h3>Xu hướng theo tháng</h3>
              <div style={{ height: '260px', position: 'relative' }}>
                {chartTheme && <Bar data={barData} options={barOptions} />}
              </div>
            </div>
          </div>

          <div className="charts-row">
            <div className="chart-box">
              <h3>Nơi chi nhiều nhất</h3>
              <ul className="merchant-list" id="topMerchants">
                {top_merchants.length === 0 ? (
                  <li className="empty-state">
                    <p>Chưa có chi tiêu trong kỳ này</p>
                  </li>
                ) : (
                  top_merchants.map((m, i) => (
                    <li key={i} className="merchant-item">
                      <span className="merchant-rank">{i + 1}</span>
                      <span className="merchant-name">{m.name}</span>
                      <span className="merchant-amount">{formatCurrency(m.total)}</span>
                    </li>
                  ))
                )}
              </ul>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
