import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import { getTrends } from '../api/services';
import { Bar } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip as ChartTooltip,
  Legend as ChartLegend,
} from 'chart.js';

ChartJS.register(CategoryScale, LinearScale, BarElement, ChartTooltip, ChartLegend);

export default function Trends() {
  const { currency, effectiveTheme } = useApp();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedYear, setSelectedYear] = useState('');

  const fetchTrends = async () => {
    setLoading(true);
    try {
      const result = await getTrends();
      setData(result);
      if (result.years && result.years.length > 0) {
        setSelectedYear(result.years[result.years.length - 1]);
      }
    } catch (err) {
      console.error('Failed to load trends:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTrends();
  }, []);

  // Theme variable readers
  const getTrendTheme = () => {
    const cssVar = (name, fallback = '') => {
      return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
    };

    const alphaColor = (color, alpha) => {
      if (!color) return color;
      if (color.startsWith('#')) {
        let hex = color.slice(1);
        if (hex.length === 3) {
          hex = hex.split('').map((char) => char + char).join('');
        }
        const red = parseInt(hex.slice(0, 2), 16);
        const green = parseInt(hex.slice(2, 4), 16);
        const blue = parseInt(hex.slice(4, 6), 16);
        return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
      }
      return color;
    };

    return {
      fontFamily: cssVar('--font', 'Inter, sans-serif'),
      textColor: cssVar('--text', '#111827'),
      mutedColor: cssVar('--text-muted', '#787774'),
      gridColor: cssVar('--chart-grid', '#F1F1EF'),
      incomeFill: alphaColor(cssVar('--positive', '#0F7B6C'), 0.75),
      expenseFill: alphaColor(cssVar('--negative', '#E03E3E'), 0.75),
      palette: [
        cssVar('--accent', '#2EAADC'),
        cssVar('--positive', '#0F7B6C'),
        cssVar('--warning', '#D9730D'),
        cssVar('--negative', '#E03E3E'),
        cssVar('--purple', '#9B51E0'),
        '#6940A5',
        '#AD1A72',
        '#E16259',
        '#CC8E22',
        '#448361',
      ],
      bgElevated: cssVar('--bg-elevated', '#ffffff'),
      border: cssVar('--border', '#e5e7eb'),
    };
  };

  const [chartTheme, setChartTheme] = useState(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      setChartTheme(getTrendTheme());
    }, 50);
    return () => clearTimeout(timer);
  }, [effectiveTheme, data, selectedYear]);

  // Helpers
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

  const formatPeriodTick = (periodStart) => {
    return formatSpectraDate(periodStart, { day: 'numeric', month: 'short' });
  };

  const formatCycleRange = (startDate, endExclusiveDate) => {
    try {
      const start = new Date(`${startDate}T00:00:00`);
      const end = new Date(`${endExclusiveDate}T00:00:00`);
      end.setDate(end.getDate() - 1);
      return `${start.toLocaleDateString('vi-VN', { day: 'numeric', month: 'short' })} -> ${end.toLocaleDateString('vi-VN', { day: 'numeric', month: 'short', year: 'numeric' })}`;
    } catch {
      return `${startDate} -> ${endExclusiveDate}`;
    }
  };

  if (loading && !data) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
        <div className="processing-inline-card" style={{ width: '100%', maxWidth: '400px', textAlign: 'center' }}>
          <div style={{ fontSize: '24px', marginBottom: '8px' }}>📊</div>
          <h3>Đang tải phân tích xu hướng...</h3>
        </div>
      </div>
    );
  }

  const { years = [], by_year = {}, period_series = [] } = data || {};
  const yearData = by_year[selectedYear];

  // Chart setup
  let monthlyChartData = { labels: [], datasets: [] };
  let monthlyChartOptions = {};
  let categoryChartData = { labels: [], datasets: [] };
  let categoryChartOptions = {};

  if (chartTheme && yearData) {
    // 1. Monthly dual-bar chart (Income vs Expense)
    const series = period_series.filter((m) => m.period_start.startsWith(selectedYear));
    const monthlyLabels = series.map((m) => formatPeriodTick(m.period_start));

    monthlyChartData = {
      labels: monthlyLabels,
      datasets: [
        {
          label: 'Thu nhập',
          data: series.map((m) => m.income),
          backgroundColor: chartTheme.incomeFill,
          borderRadius: 6,
          borderSkipped: false,
        },
        {
          label: 'Chi tiêu',
          data: series.map((m) => m.expenses),
          backgroundColor: chartTheme.expenseFill,
          borderRadius: 6,
          borderSkipped: false,
        },
      ],
    };

    monthlyChartOptions = {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 600, easing: 'easeOutQuart' },
      plugins: {
        legend: {
          labels: {
            color: chartTheme.mutedColor,
            font: { family: chartTheme.fontFamily, size: 12 },
            usePointStyle: true,
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
            title: (ctx) => formatCycleRange(series[ctx[0].dataIndex].period_start, series[ctx[0].dataIndex].period_end),
            label: (ctx) => ` ${ctx.dataset.label}: ${formatCurrency(ctx.raw)}`,
          },
        },
      },
      scales: {
        y: {
          beginAtZero: true,
          ticks: {
            color: chartTheme.mutedColor,
            font: { family: chartTheme.fontFamily, size: 11 },
            callback: (v) => formatCurrency(v),
          },
          grid: { color: chartTheme.gridColor },
          border: { display: false },
        },
        x: {
          ticks: {
            color: chartTheme.mutedColor,
            font: { family: chartTheme.fontFamily, size: 11 },
          },
          grid: { display: false },
          border: { display: false },
        },
      },
    };

    // 2. Horizontal Category bar chart
    const cats = yearData.by_category || {};
    const catLabels = Object.keys(cats);
    const catValues = Object.values(cats);

    categoryChartData = {
      labels: catLabels,
      datasets: [
        {
          label: 'Chi tiêu',
          data: catValues,
          backgroundColor: chartTheme.palette.slice(0, catLabels.length),
          borderRadius: 6,
          borderSkipped: false,
        },
      ],
    };

    categoryChartOptions = {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 700, easing: 'easeOutQuart' },
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
            label: (ctx) => ` Chi tiêu: ${formatCurrency(ctx.raw)}`,
          },
        },
      },
      scales: {
        x: {
          beginAtZero: true,
          ticks: {
            color: chartTheme.mutedColor,
            font: { family: chartTheme.fontFamily, size: 11 },
            callback: (v) => formatCurrency(v),
          },
          grid: { color: chartTheme.gridColor },
          border: { display: false },
        },
        y: {
          ticks: {
            color: chartTheme.mutedColor,
            font: { family: chartTheme.fontFamily, size: 12 },
          },
          grid: { display: false },
          border: { display: false },
        },
      },
    };
  }

  return (
    <div className="page-trends-root">
      <h1 className="page-title">Xu hướng</h1>
      <p className="page-subtitle">So sánh tài chính hàng năm theo chu kỳ chi tiêu</p>

      {years.length === 0 ? (
        <div className="empty-state">
          <div className="icon">📈</div>
          <h3>Chưa có dữ liệu xu hướng</h3>
          <p>Tải tệp giao dịch lên để trực quan hóa lịch sử chi tiêu</p>
          <Link to="/upload" className="btn btn-primary" style={{ marginTop: '16px' }}>
            📥 Tải giao dịch lên
          </Link>
        </div>
      ) : (
        <>
          {/* Year Tabs */}
          <div className="year-tabs" id="yearTabs">
            {years.map((y) => (
              <button
                key={y}
                className={`year-tab ${selectedYear === y ? 'active' : ''}`}
                onClick={() => setSelectedYear(y)}
              >
                {y}
              </button>
            ))}
          </div>

          {/* Stat Cards */}
          {yearData && (
            <div className="cards" id="yearCards">
              <div className="card">
                <div className="card-label">Dòng tiền ròng</div>
                <div className={`card-value ${yearData.net >= 0 ? 'positive' : 'negative'}`}>
                  {formatCurrency(yearData.net)}
                </div>
              </div>
              <div className="card">
                <div className="card-label">Tỷ lệ tiết kiệm (Savings Rate)</div>
                <div className="card-value neutral">{yearData.savings_rate}%</div>
              </div>
              <div className="card">
                <div className="card-label">Tổng thu nhập</div>
                <div className="card-value positive">{formatCurrency(yearData.income)}</div>
              </div>
              <div className="card">
                <div className="card-label">Tổng chi tiêu</div>
                <div className="card-value negative">{formatCurrency(yearData.expenses)}</div>
              </div>
            </div>
          )}

          {/* Charts Row - Monthly */}
          <div className="charts-row">
            <div className="chart-box" style={{ gridColumn: '1 / -1' }}>
              <h3>Thu nhập và chi tiêu · Hàng tháng</h3>
              <div style={{ height: '240px', position: 'relative' }}>
                {chartTheme && yearData && <Bar data={monthlyChartData} options={monthlyChartOptions} />}
              </div>
            </div>
          </div>

          {/* Charts Row - Category Spending */}
          {yearData && Object.keys(yearData.by_category || {}).length > 0 && (
            <div className="charts-row">
              <div className="chart-box" style={{ gridColumn: '1 / -1' }}>
                <h3>Các danh mục chi tiêu nhiều nhất</h3>
                <div style={{ height: '300px', position: 'relative' }}>
                  {chartTheme && <Bar data={categoryChartData} options={categoryChartOptions} />}
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
