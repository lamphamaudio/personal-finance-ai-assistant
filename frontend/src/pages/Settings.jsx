import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import {
  getSettings,
  updatePreferences,
  getCategoryRules,
  createCategoryRule,
  updateCategoryRule,
  deleteCategoryRule,
  testCategoryRule,
  getLearningSummary,
  reapplyLearning,
  resetDatabase,
  getTransactions
} from '../api/services';

export default function Settings() {
  const {
    themePreference,
    changeThemePreference,
    currency,
    setCurrency,
    showToast,
    refreshPreferences: refreshGlobalPreferences,
    currentUser,
    logoutCurrentUser
  } = useApp();

  const navigate = useNavigate();

  // App settings state
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);

  // Cycle preferences state
  const [cycleMode, setCycleMode] = useState('fixed');
  const [cycleDay, setCycleDay] = useState(1);
  const [savingCycle, setSavingCycle] = useState(false);
  const [savingCurrency, setSavingCurrency] = useState(false);
  const [selectedCurrency, setSelectedCurrency] = useState('EUR');

  // Rules state
  const [rules, setRules] = useState([]);
  const [ruleType, setRuleType] = useState('contains');
  const [rulePattern, setRulePattern] = useState('');
  const [ruleCategory, setRuleCategory] = useState('');
  const [ruleSampleText, setRuleSampleText] = useState('');
  const [ruleTestResult, setRuleTestResult] = useState(null);
  const [testingRule, setTestingRule] = useState(false);

  // Learning feedback state
  const [learningSummary, setLearningSummary] = useState(null);
  const [learningEvents, setLearningEvents] = useState([]);
  const [reapplying, setReapplying] = useState(false);

  const fetchSettings = useCallback(async () => {
    try {
      const data = await getSettings();
      setSettings(data);
      setSelectedCurrency(data.currency || 'EUR');
      setCycleMode(data.cycle_mode || 'fixed');
      setCycleDay(data.fixed_cycle_start_day || data.cycle_start_day || data.pay_day || 1);
    } catch (err) {
      console.error('Failed to load settings:', err);
    }
  }, []);

  const fetchRules = useCallback(async () => {
    try {
      const data = await getCategoryRules();
      setRules(data.rules || []);
    } catch (err) {
      console.error('Failed to load rules:', err);
    }
  }, []);

  const fetchLearning = useCallback(async () => {
    try {
      const data = await getLearningSummary();
      setLearningSummary(data.summary);
      setLearningEvents(data.events || []);
    } catch (err) {
      console.error('Failed to load learning summary:', err);
    }
  }, []);

  useEffect(() => {
    const loadAll = async () => {
      setLoading(true);
      await Promise.all([fetchSettings(), fetchRules(), fetchLearning()]);
      setLoading(false);
    };
    loadAll();
  }, [fetchSettings, fetchRules, fetchLearning]);

  const ordSuffix = (d) => {
    if (d >= 11 && d <= 13) return 'th';
    switch (d % 10) {
      case 1: return 'st';
      case 2: return 'nd';
      case 3: return 'rd';
      default: return 'th';
    }
  };

  const formatSpectraDate = (dateString, options = { day: 'numeric', month: 'short', year: 'numeric' }) => {
    try {
      return new Date(`${dateString}T00:00:00`).toLocaleDateString('vi-VN', options);
    } catch {
      return dateString;
    }
  };

  const handleCycleDayChange = (delta) => {
    setCycleDay(current => {
      const MAX_CYCLE_DAY = 28;
      const next = ((current - 1 + delta + MAX_CYCLE_DAY) % MAX_CYCLE_DAY) + 1;
      return next;
    });
  };

  const saveBaseCurrency = async () => {
    setSavingCurrency(true);
    try {
      const data = await updatePreferences({ base_currency: selectedCurrency });
      setCurrency(data.currency);
      await refreshGlobalPreferences();
      await fetchSettings();
      showToast(`Tiền tệ gốc đã đặt thành ${data.currency}`, 'success');
    } catch (err) {
      showToast(err.message || 'Cập nhật tiền tệ thất bại', 'error');
    } finally {
      setSavingCurrency(false);
    }
  };

  const saveCyclePreference = async () => {
    setSavingCycle(true);
    try {
      const payload = { cycle_mode: cycleMode };
      if (cycleMode === 'fixed') {
        payload.pay_day = cycleDay;
      }
      const data = await updatePreferences(payload);
      await fetchSettings();
      showToast(`Đã cập nhật chu kỳ tài chính: ${data.current_cycle.label}`, 'success');
    } catch (err) {
      showToast(err.message || 'Cập nhật chu kỳ thất bại', 'error');
    } finally {
      setSavingCycle(false);
    }
  };

  // Rule operations
  const handleCreateRule = async () => {
    const pattern = rulePattern.trim();
    const category = ruleCategory.trim();
    if (!pattern || !category) {
      showToast('Pattern và Category không được để trống', 'error');
      return;
    }

    try {
      await createCategoryRule({ rule_type: ruleType, pattern, category });
      setRulePattern('');
      setRuleCategory('');
      showToast('Đã thêm quy tắc phân loại mới', 'success');
      fetchRules();
    } catch (err) {
      showToast(err.message || 'Thêm quy tắc thất bại', 'error');
    }
  };

  const handleToggleRuleActive = async (ruleId, currentActive) => {
    try {
      await updateCategoryRule(ruleId, { is_active: !currentActive });
      showToast(`Đã ${!currentActive ? 'kích hoạt' : 'vô hiệu hóa'} quy tắc`, 'info');
      fetchRules();
    } catch (err) {
      showToast(err.message || 'Cập nhật quy tắc thất bại', 'error');
    }
  };

  const handleMoveRule = async (ruleId, direction) => {
    try {
      await updateCategoryRule(ruleId, { move: direction });
      fetchRules();
    } catch (err) {
      showToast(err.message || 'Thay đổi mức ưu tiên thất bại', 'error');
    }
  };

  const handleDeleteRule = async (ruleId) => {
    try {
      await deleteCategoryRule(ruleId);
      showToast('Đã xóa quy tắc phân loại', 'info');
      fetchRules();
    } catch (err) {
      showToast(err.message || 'Xóa quy tắc thất bại', 'error');
    }
  };

  const handleTestRule = async () => {
    const pattern = rulePattern.trim();
    if (!pattern) {
      showToast('Hãy nhập Pattern để chạy thử nghiệm', 'error');
      return;
    }
    
    setTestingRule(true);
    setRuleTestResult(null);
    try {
      const res = await testCategoryRule({
        rule_type: ruleType,
        pattern,
        sample_text: ruleSampleText.trim(),
      });
      setRuleTestResult(res);
    } catch (err) {
      showToast(err.message || 'Thử nghiệm quy tắc thất bại', 'error');
    } finally {
      setTestingRule(false);
    }
  };

  // Learning Loop feedback
  const handleReapplyLearning = async () => {
    setReapplying(true);
    try {
      const data = await reapplyLearning();
      showToast(`Đã cập nhật phân loại cho ${data.updated} giao dịch lịch sử`, 'success');
      await Promise.all([fetchLearning(), fetchSettings(), fetchRules()]);
    } catch (err) {
      showToast(err.message || 'Đồng bộ phản hồi học máy thất bại', 'error');
    } finally {
      setReapplying(false);
    }
  };

  // Database actions
  const handleResetDatabase = async () => {
    const typed = window.prompt('Nhập từ RESET để xác nhận xóa toàn bộ cơ sở dữ liệu.');
    if (typed !== 'RESET') {
      showToast('Đã hủy yêu cầu đặt lại', 'info');
      return;
    }

    try {
      await resetDatabase('RESET');
      showToast('Đã đặt lại toàn bộ cơ sở dữ liệu về trạng thái ban đầu');
      await refreshGlobalPreferences();
      await fetchSettings();
      setTimeout(() => {
        navigate('/transactions');
      }, 600);
    } catch (err) {
      showToast(err.message || 'Xóa cơ sở dữ liệu thất bại', 'error');
    }
  };

  const handleExportCSV = async () => {
    try {
      let allTx = [];
      let currentPageNum = 1;
      showToast('Đang chuẩn bị dữ liệu xuất CSV...', 'info');

      while (true) {
        const data = await getTransactions({ per_page: 200, page: currentPageNum });
        allTx = allTx.concat(data.transactions);
        if (currentPageNum >= data.pages) break;
        currentPageNum++;
      }

      if (allTx.length === 0) {
        showToast('Không có giao dịch nào để xuất', 'error');
        return;
      }

      let csv = 'Ngày,Nơi giao dịch,Danh mục,Số tiền\n';
      for (const t of allTx) {
        csv += `${t.date},"${t.merchant.replace(/"/g, '""')}","${t.category.replace(/"/g, '""')}",${t.amount}\n`;
      }

      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `spectra_export_${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      showToast(`Đã xuất thành công ${allTx.length} giao dịch sang tệp CSV`);
    } catch (err) {
      showToast(err.message || 'Xuất CSV thất bại', 'error');
    }
  };

  if (loading && !settings) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
        <div className="processing-inline-card" style={{ width: '100%', maxWidth: '400px', textAlign: 'center' }}>
          <div style={{ fontSize: '24px', marginBottom: '8px' }}>⚙️</div>
          <h3>Đang tải cấu hình hệ thống...</h3>
        </div>
      </div>
    );
  }

  const requiresCurrencySetup = Boolean(settings?.requires_base_currency_setup);
  const activeRulesCount = rules.filter(r => r.is_active).length;

  return (
    <div className="page-settings-root">
      <div className="page-header">
        <div>
          <h1 className="page-title">Cài đặt</h1>
          <p className="page-subtitle">Thiết lập cấu hình chung, quản lý quy tắc tự động hóa và học máy từ AI.</p>
        </div>
        <div className="page-header-actions">
          <Link to="/upload" className="btn btn-secondary btn-sm">Tải lên</Link>
          <Link to="/transactions" className="btn btn-secondary btn-sm">Giao dịch</Link>
        </div>
      </div>

      {/* Overview Cards */}
      <section className="settings-overview" aria-label="Cài đặt overview">
        <article className={`settings-overview-card ${requiresCurrencySetup ? 'is-warning' : ''}`} id="setupStatusCard">
          <span className="settings-overview-title">Trạng thái thiết lập</span>
          <strong className="settings-overview-value">
            {requiresCurrencySetup ? 'Cần thiết lập' : 'Sẵn sàng'}
          </strong>
          <p className="settings-overview-hint">
            {requiresCurrencySetup ? 'Chọn tiền tệ gốc trước khi dùng Spectra.' : 'Cấu hình mặc định đã sẵn sàng hoạt động.'}
          </p>
          <a className="settings-overview-link" href="#settings-currency">
            {requiresCurrencySetup ? 'Chọn tiền tệ gốc' : 'Xem thiết lập'}
          </a>
        </article>

        <article className="settings-overview-card">
          <span className="settings-overview-title">Tiền tệ gốc</span>
          <strong className="settings-overview-value">{(settings?.currency || 'EUR').toUpperCase()}</strong>
          <p className="settings-overview-hint">Dùng thống nhất trên biểu đồ, ngân sách và xu hướng.</p>
          <a className="settings-overview-link" href="#settings-currency">Sửa tiền tệ</a>
        </article>

        <article className="settings-overview-card">
          <span className="settings-overview-title">Chu kỳ tài chính</span>
          <strong className="settings-overview-value">
            {cycleMode === 'last_business_day' 
              ? 'Last business day' 
              : `Ngày cố định · ${cycleDay}${ordSuffix(cycleDay)}`}
          </strong>
          <p className="settings-overview-hint">
            {settings?.current_cycle?.label 
              ? `Chu kỳ hiện tại: ${settings.current_cycle.label}` 
              : 'Used for dashboard, budgets, and trends.'}
          </p>
          <a className="settings-overview-link" href="#settings-cycle">Sửa chu kỳ</a>
        </article>

        <article className="settings-overview-card">
          <span className="settings-overview-title">Dữ liệu lưu trữ</span>
          <strong className="settings-overview-value">{(settings?.tx_count || 0).toLocaleString()} tx</strong>
          <p className="settings-overview-hint">
            {(settings?.merchant_count || 0).toLocaleString()} merchant đã học · {(settings?.feedback_count || 0).toLocaleString()} sự kiện phản hồi
          </p>
          <a className="settings-overview-link" href="#settings-database">View stats</a>
        </article>
      </section>

      <nav className="section-nav settings-nav" aria-label="Cài đặt sections">
        <a className="section-nav-link" href="#settings-setup">Setup</a>
        <a className="section-nav-link" href="#settings-automation">Automation</a>
        <a className="section-nav-link" href="#settings-environment">Environment</a>
        <a className="section-nav-link" href="#settings-danger">Danger zone</a>
      </nav>

      {/* Recommended Settings Section */}
      <section className="settings-section" id="settings-setup">
        <div className="settings-section-head">
          <div>
            <div className="settings-section-eyebrow">Khuyên dùng đầu tiên</div>
            <h2>Thiết lập & Tùy chọn</h2>
            <p>Các cấu hình cốt lõi ảnh hưởng trực tiếp đến dữ liệu và tính toán hàng ngày của Spectra.</p>
          </div>
        </div>

        {requiresCurrencySetup && (
          <div className="settings-group settings-danger-zone" id="currencySetupNotice" style={{ display: 'block' }}>
            <h3>Yêu cầu bắt buộc</h3>
            <div className="settings-row">
              <div className="settings-label">
                Đặt tiền tệ gốc của bạn
                <small>Thiết lập lần đầu: hãy chọn tiền tệ gốc phù hợp nhất với bạn trước khi bắt đầu import giao dịch.</small>
              </div>
            </div>
          </div>
        )}

        <div className="settings-group" id="settings-currency">
          <h3>Tiền tệ gốc</h3>
          <div className="settings-row">
            <div className="settings-label">
              Tiền tệ mặc định
              <small>Mọi giao dịch ngoại tệ khác sẽ được tự động quy đổi về tiền tệ này theo tỷ giá ECB tại ngày giao dịch.</small>
            </div>
            <div className="settings-control-group">
              <select 
                className="settings-select" 
                value={selectedCurrency}
                onChange={(e) => setSelectedCurrency(e.target.value)}
              >
                <option value="VND">VND (Việt Nam Đồng)</option>
                <option value="EUR">EUR</option>
                <option value="USD">USD</option>
                <option value="GBP">GBP</option>
                <option value="CHF">CHF</option>
                <option value="JPY">JPY</option>
                <option value="CAD">CAD</option>
                <option value="AUD">AUD</option>
                <option value="SEK">SEK</option>
                <option value="NOK">NOK</option>
                <option value="DKK">DKK</option>
              </select>
              <button 
                className="btn btn-primary btn-sm" 
                type="button" 
                onClick={saveBaseCurrency}
                disabled={savingCurrency}
              >
                {savingCurrency ? '...' : 'Lưu'}
              </button>
              {requiresCurrencySetup && (
                <span className="settings-badge warning">Bắt buộc</span>
              )}
            </div>
          </div>
        </div>

        <div className="settings-group" id="settings-appearance">
          <h3>Giao diện hiển thị</h3>
          <div className="settings-row">
            <div className="settings-label">
              Chế độ nền (Theme)
              <small>Auto sẽ tự chuyển theo giao diện Windows của bạn, hoặc tự ép buộc hiển thị nền Sáng / Tối.</small>
            </div>
            <div className="settings-control-group">
              <select 
                className="settings-select" 
                value={themePreference}
                onChange={(e) => changeThemePreference(e.target.value)}
              >
                <option value="auto">Tự động (Hệ thống)</option>
                <option value="light">Nền sáng</option>
                <option value="dark">Nền tối</option>
              </select>
            </div>
          </div>
        </div>

        <div className="settings-group" id="settings-cycle">
          <h3>Chu kỳ tài chính</h3>
          <div className="settings-row">
            <div className="settings-label">
              Ngày bắt đầu chu kỳ tài chính
              <small>Chọn một ngày cố định trong tháng (từ 1 đến 28, ví dụ ngày nhận lương) hoặc ngày làm việc cuối cùng hàng tháng.</small>
            </div>
            <div className="settings-control-group">
              <select 
                className="settings-select" 
                value={cycleMode}
                onChange={(e) => setCycleMode(e.target.value)}
              >
                <option value="fixed">Ngày cố định</option>
                <option value="last_business_day">Ngày làm việc cuối cùng</option>
              </select>

              {cycleMode === 'fixed' && (
                <div className="day-stepper">
                  <button className="day-stepper-btn" type="button" onClick={() => handleCycleDayChange(-1)}>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="5" y1="12" x2="19" y2="12"/></svg>
                  </button>
                  <div className="day-stepper-value">
                    <span>{cycleDay}</span><span className="day-stepper-ord">{ordSuffix(cycleDay)}</span>
                  </div>
                  <button className="day-stepper-btn" type="button" onClick={() => handleCycleDayChange(1)}>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                  </button>
                </div>
              )}

              <button 
                className="btn btn-primary btn-sm" 
                type="button" 
                onClick={saveCyclePreference}
                disabled={savingCycle}
              >
                {savingCycle ? '...' : 'Lưu'}
              </button>
            </div>
          </div>

          {settings?.current_cycle && (
            <div className="settings-row">
              <div className="settings-label">
                Thời gian chu kỳ hiện tại
                <small>Dashboard, hạn mức ngân sách và xu hướng sẽ đồng bộ trong khoảng thời gian này.</small>
              </div>
              <div className="cycle-range-display">
                <span className="cycle-range-date">{formatSpectraDate(settings.current_cycle.start)}</span>
                <svg className="cycle-range-arrow" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
                <span className="cycle-range-date">
                  {formatSpectraDate(new Date(new Date(`${settings.current_cycle.end}T00:00:00`).getTime() - 86400000).toISOString().slice(0, 10))}
                </span>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* Automation & Machine Learning Section */}
      <section className="settings-section" id="settings-automation">
        <div className="settings-section-head">
          <div>
            <div className="settings-section-eyebrow">Tính năng nâng cao</div>
            <h2>Tự động hóa & Học máy</h2>
            <p>Thiết lập quy tắc phân loại tĩnh hoặc quản lý phản hồi chỉnh sửa để AI của Spectra tự động trở nên thông minh hơn.</p>
          </div>
        </div>

        {/* Custom priority rules builder */}
        <div className="settings-group">
          <h3>Quy tắc phân loại tùy chỉnh</h3>
          <p className="settings-group-copy">
            Các quy tắc tĩnh này có độ ưu tiên cao nhất, được chạy đè lên cơ chế tự động phân loại của AI. Thêm quy tắc khi bạn muốn tự định đoạt danh mục cứng cho một số nhà cung cấp.
          </p>

          <div className="settings-row">
            <div className="settings-label">
              Thêm quy tắc mới
              <small>Khớp theo từ khóa chứa (contains) hoặc biểu thức chính quy (regex), rồi tự gán danh mục mặc định.</small>
            </div>
            <div className="settings-control-group rules-builder">
              <select className="settings-select" value={ruleType} onChange={(e) => setRuleType(e.target.value)}>
                <option value="contains">Chứa (Contains)</option>
                <option value="regex">Chính quy (Regex)</option>
              </select>
              <input 
                type="text" 
                className="settings-input" 
                placeholder="vd: grab|uber|taxi"
                value={rulePattern}
                onChange={(e) => setRulePattern(e.target.value)}
              />
              <input 
                type="text" 
                className="settings-input" 
                placeholder="Danh mục (vd: Di chuyển)"
                value={ruleCategory}
                onChange={(e) => setRuleCategory(e.target.value)}
              />
              <button className="btn btn-primary btn-sm" type="button" onClick={handleCreateRule}>
                Thêm quy tắc
              </button>
            </div>
          </div>

          <div className="settings-row">
            <div className="settings-label">
              Trạng thái quy tắc
              <small>Bật/tắt trạng thái, kéo tăng/giảm mức độ ưu tiên hoặc chạy thử nghiệm tác động.</small>
            </div>
            <div className="settings-control-group">
              <span className={`settings-badge ${activeRulesCount ? 'local' : ''}`}>
                {activeRulesCount}/{rules.length} đang bật
              </span>
            </div>
          </div>

          {/* Test Rule Impact */}
          <div className="settings-inline-panel">
            <div className="settings-inline-panel-header">Chạy thử nghiệm quy tắc của bạn</div>
            <div className="settings-control-group rules-builder" style={{ marginTop: 0 }}>
              <input 
                type="text" 
                className="settings-input" 
                placeholder="Nhập tên nhà giao dịch chạy thử" 
                value={ruleSampleText}
                onChange={(e) => setRuleSampleText(e.target.value)}
              />
              <button className="btn btn-secondary btn-sm" type="button" onClick={handleTestRule} disabled={testingRule}>
                {testingRule ? 'Đang thử...' : 'Chạy thử'}
              </button>
            </div>
            <div className="table-cell-muted" id="ruleTestResult" style={{ marginTop: '8px' }}>
              {ruleTestResult ? (
                <div>
                  <div><strong>Trùng khớp từ khóa test:</strong> {ruleTestResult.matches_sample ? '✅ Khớp' : '❌ Không khớp'}</div>
                  <div><strong>Tác động lịch sử:</strong> Đã tìm thấy {ruleTestResult.impact_count} giao dịch trùng khớp</div>
                  {ruleTestResult.examples && ruleTestResult.examples.length > 0 && (
                    <div className="rule-test-examples" style={{ marginTop: '6px', padding: '6px', background: 'var(--bg-subtle)', borderRadius: '6px' }}>
                      {ruleTestResult.examples.map((ex, i) => (
                        <div key={i} style={{ fontSize: '12px' }}>
                          <strong>{ex.merchant}</strong> · {ex.current_category} · {ex.date}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                'Nhập từ khóa và dòng text mẫu để preview tác động trước khi tạo quy tắc.'
              )}
            </div>
          </div>

          {/* Rules List Table */}
          <div id="rulesList" className="rules-list">
            {rules.length === 0 ? (
              <div className="empty-state" style={{ padding: '18px', marginTop: '8px' }}>
                <p>Chưa có quy tắc phân loại tùy chỉnh nào. Spectra vẫn đang phân loại tự động bằng AI rất tốt.</p>
              </div>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Ưu tiên</th>
                    <th>Trạng thái</th>
                    <th>Kiểu khớp</th>
                    <th>Từ khóa</th>
                    <th>Danh mục</th>
                    <th style={{ textAlign: 'right' }}>Thao tác</th>
                  </tr>
                </thead>
                <tbody>
                  {rules.map((rule) => (
                    <tr key={rule.id}>
                      <td>#{rule.priority}</td>
                      <td>
                        <label className="mini-checkbox" style={{ cursor: 'pointer' }}>
                          <input 
                            type="checkbox" 
                            checked={rule.is_active} 
                            onChange={() => handleToggleRuleActive(rule.id, rule.is_active)}
                          />
                          <span>{rule.is_active ? 'Bật' : 'Tắt'}</span>
                        </label>
                      </td>
                      <td><code>{rule.rule_type}</code></td>
                      <td><code>{rule.pattern}</code></td>
                      <td>{rule.category}</td>
                      <td style={{ textAlign: 'right' }}>
                        <button className="btn btn-secondary btn-sm" type="button" onClick={() => handleMoveRule(rule.id, 'up')} style={{ marginRight: '2px' }}>↑</button>
                        <button className="btn btn-secondary btn-sm" type="button" onClick={() => handleMoveRule(rule.id, 'down')} style={{ marginRight: '6px' }}>↓</button>
                        <button className="btn btn-secondary btn-sm" type="button" onClick={() => handleDeleteRule(rule.id)}>Xóa</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* Feedback loops learning summary */}
        <div className="settings-group">
          <h3>Trung tâm Học máy (Learning Feedback)</h3>
          <p className="settings-group-copy">
            Các lần chỉnh sửa danh mục thủ công của bạn khi Upload sẽ được lưu trữ làm dữ liệu huấn luyện cục bộ. Bạn có thể kích hoạt áp dụng lại các bài học này vào toàn bộ lịch sử giao dịch cũ bất cứ lúc nào.
          </p>

          <div className="settings-row">
            <div className="settings-label">
              Áp dụng bài học lịch sử
              <small>Kích hoạt học máy đồng bộ quét lại toàn bộ dữ liệu lịch sử để cập nhật phân loại chuẩn xác nhất.</small>
            </div>
            <div className="settings-control-group">
              <button 
                className="btn btn-secondary btn-sm" 
                type="button" 
                onClick={handleReapplyLearning}
                disabled={reapplying}
              >
                {reapplying ? 'Đang quét...' : 'Chạy học máy lịch sử'}
              </button>
            </div>
          </div>

          <div className="settings-stats-grid">
            <div className="settings-stat-card">
              <span className="settings-stat-label">Tổng phản hồi</span>
              <strong>{learningSummary?.feedback_count || 0}</strong>
            </div>
            <div className="settings-stat-card">
              <span className="settings-stat-label">Học cho tương lai</span>
              <strong>{learningSummary?.learned_future_count || 0}</strong>
            </div>
            <div className="settings-stat-card">
              <span className="settings-stat-label">Dòng ghi đè</span>
              <strong>{learningSummary?.override_count || 0}</strong>
            </div>
            <div className="settings-stat-card">
              <span className="settings-stat-label">Chưa phân loại</span>
              <strong>{learningSummary?.uncategorized_count || 0}</strong>
            </div>
          </div>

          {/* Recent feedback loops table */}
          <div id="learningList" className="rules-list">
            {learningEvents.length === 0 ? (
              <div className="empty-state" style={{ padding: '18px', marginTop: '8px' }}>
                <p>Chưa có phản hồi học tập nào được lưu trữ.</p>
              </div>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Thời gian</th>
                    <th>Nơi giao dịch</th>
                    <th>Danh mục phản hồi</th>
                    <th>Nguồn sửa</th>
                    <th>Phạm vi áp dụng</th>
                  </tr>
                </thead>
                <tbody>
                  {learningEvents.slice(0, 10).map((event, idx) => (
                    <tr key={idx}>
                      <td>{formatSpectraDate(event.created_at.replace('T', ' ').slice(0, 10))}</td>
                      <td>{event.clean_name}</td>
                      <td>{event.category}</td>
                      <td><code>{event.source}</code></td>
                      <td>
                        {event.apply_to_future 
                          ? <span className="settings-badge local">Lâu dài (Học AI)</span> 
                          : <span className="settings-badge">Chỉ lần này</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </section>

      {/* Environment Variables & Local Stats Context Section */}
      <section className="settings-section" id="settings-environment">
        <div className="settings-section-head">
          <div>
            <div className="settings-section-eyebrow">Dữ liệu môi trường</div>
            <h2>Môi trường & Hệ thống</h2>
            <p>Xem thông tin hệ thống đang kết nối, tệp cấu hình và xuất sao lưu dữ liệu của bạn.</p>
          </div>
        </div>

        <div className="settings-group">
          <h3>Công cụ AI & Tích hợp</h3>
          <div className="settings-row">
            <div className="settings-label">
              AI Categorization Engine
              <small>Được thiết lập thông qua biến môi trường <code>AI_PROVIDER</code> trong file .env (local, openai, gemini).</small>
            </div>
            <span className={`settings-badge ${settings?.provider === 'local' ? 'local' : 'cloud'}`}>
              {settings?.provider === 'local' 
                ? 'Học máy Offline (Cục bộ)' 
                : settings?.provider === 'gemini' 
                  ? 'Gemini Cloud AI' 
                  : 'OpenAI Cloud AI'}
            </span>
          </div>

          <div className="settings-row">
            <div className="settings-label">
              Kết nối Google Sheets
              <small>Tự động sao lưu và đồng bộ hai chiều sang bảng tính Google Sheets khi cấu hình SPREADSHEET_ID.</small>
            </div>
            <span className={`settings-badge ${settings?.sheets_connected ? 'local' : ''}`}>
              {settings?.sheets_connected ? 'Đang kết nối' : 'Chưa cấu hình'}
            </span>
          </div>
        </div>

        <div className="settings-group" id="settings-database">
          <h3>Thống kê Cơ sở dữ liệu</h3>
          <div className="settings-row">
            <div className="settings-label">
              Số dòng giao dịch
              <small>Tổng số giao dịch đã lưu trữ trong Supabase Postgres database.</small>
            </div>
            <div className="settings-value">{settings?.tx_count || 0}</div>
          </div>
          <div className="settings-row">
            <div className="settings-label">
              Merchant học máy
              <small>Số địa điểm giao dịch đã được AI huấn luyện phân loại danh mục thành công.</small>
            </div>
            <div className="settings-value">{settings?.merchant_count || 0}</div>
          </div>
          <div className="settings-row">
            <div className="settings-label">
              Số danh mục đang dùng
              <small>Các nhãn phân loại giao dịch đang được sử dụng trong ví của bạn.</small>
            </div>
            <div className="settings-value">{settings?.category_count || 0}</div>
          </div>
          <div className="settings-row">
            <div className="settings-label">
              Quy tắc ưu tiên
              <small>Các quy tắc phân loại thủ công đang được chạy.</small>
            </div>
            <div className="settings-value">{settings?.active_rule_count || 0}</div>
          </div>
        </div>

        <div className="settings-group">
          <h3>Sao lưu dữ liệu (Export)</h3>
          <div className="settings-row">
            <div className="settings-label">
              Xuất tệp CSV
              <small>Tải toàn bộ lịch sử sổ giao dịch hiện có về máy tính của bạn dưới dạng tệp CSV phổ thông.</small>
            </div>
            <button className="btn btn-secondary" onClick={handleExportCSV}>
              Tải CSV xuống
            </button>
          </div>
        </div>
      </section>

      {/* Danger Zone Section */}
      <section className="settings-section" id="settings-danger">
        <div className="settings-section-head">
          <div>
            <div className="settings-section-eyebrow">Khu vực nguy hiểm</div>
            <h2>Danger Zone</h2>
            <p>Các hành động có tính phá hủy dữ liệu được gom riêng tại đây để đảm bảo an toàn tối đa.</p>
          </div>
        </div>

        <div className="settings-group settings-danger-zone">
          <h3>Reset Database</h3>
          <div className="settings-row">
            <div className="settings-label">
              Xóa sạch dữ liệu cục bộ
              <small>Xóa vĩnh viễn toàn bộ giao dịch, lịch sử học máy của AI, hạn mức ngân sách và các cài đặt chu kỳ.</small>
            </div>
            <button className="btn btn-danger" type="button" onClick={handleResetDatabase}>
              Xóa sạch DB
            </button>
          </div>
        </div>
      </section>

      <section className="settings-section" id="settings-account">
        <div className="settings-section-head">
          <div>
            <div className="settings-section-eyebrow">Tai khoan</div>
            <h2>Phien dang nhap</h2>
            <p>Quan ly phien Spectra dang ket noi voi Bank Simulator.</p>
          </div>
        </div>

        <div className="settings-group">
          <div className="settings-row">
            <div className="settings-label">
              <span>Signed in</span><strong>{currentUser?.persona_type || 'Demo user'}</strong>
              {currentUser?.bank_name && (
                <small>{currentUser.bank_name} - {currentUser.account_number}</small>
              )}
            </div>
            <div className="settings-control-group">
              <a className="btn btn-secondary" href="/sso/bank">
                Open Bank Simulator
              </a>
              <button className="btn btn-secondary" type="button" onClick={logoutCurrentUser}>
                Logout
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
