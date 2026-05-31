import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import { useBankImporter } from '../hooks/useSSE';
import { getCategoryOptions, confirmImport } from '../api/services';

export default function Upload() {
  const { currency, showToast } = useApp();
  const navigate = useNavigate();
  const importStartedRef = useRef(false);
  
  // Custom SSE Uploader hook
  const {
    uploading,
    progress,
    step,
    error,
    result,
    importBank,
    reset: resetUpload
  } = useBankImporter();

  // Review & Edit state
  const [previewData, setPreviewData] = useState([]);
  const [categories, setCategories] = useState([]);
  const [saving, setSaving] = useState(false);


  // Fetch all known category options for selects
  useEffect(() => {
    const fetchCats = async () => {
      try {
        const data = await getCategoryOptions();
        setCategories(data.categories || []);
      } catch (err) {
        console.error('Failed to load category options:', err);
      }
    };
    fetchCats();
  }, []);

  // Sync result from uploader hook with page local preview state
  useEffect(() => {
    if (result && result.transactions && previewData.length === 0) {
      setPreviewData(result.transactions);
      showToast(result.message || 'Tải lên hoàn tất, đang chuẩn bị xem trước.');
    }
  }, [result, showToast, previewData.length]);

  // Show SSE error in toast
  useEffect(() => {
    if (error) {
      showToast(error, 'error');
    }
  }, [error, showToast]);

  const cancelPreview = () => {
    setPreviewData([]);
    resetUpload();
    importStartedRef.current = true;
  };

  // Inline edit handlers
  const updatePreviewField = (index, field, value) => {
    setPreviewData(prev => prev.map((item, idx) => {
      if (idx !== index) return item;
      
      const updated = { ...item, [field]: value };
      if (field === 'category') {
        updated.needs_review = value === 'Chưa phân loại';
      }
      return updated;
    }));
  };

  const toggleLearning = (index, checked) => {
    updatePreviewField(index, 'apply_to_future', checked);
  };

  const applyCategorySuggestion = (index, suggestedCat) => {
    updatePreviewField(index, 'category', suggestedCat);
  };

  // Propagate to similar rows in this batch
  const handleApplyToSimilar = (index) => {
    const source = previewData[index];
    if (!source) return;

    const normalizeText = (val) => String(val || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
    const originalKey = normalizeText(source.original_description || source.merchant);
    const merchantTokens = normalizeText(source.merchant).split(' ').filter(token => token.length >= 3);
    const merchantKey = merchantTokens[0] || normalizeText(source.merchant);

    let updatedCount = 0;

    setPreviewData(prev => prev.map((item) => {
      const itemOriginal = normalizeText(item.original_description || item.merchant);
      const itemMerchant = normalizeText(item.merchant);
      const isSimilar = itemOriginal === originalKey
        || (merchantKey && itemOriginal.includes(merchantKey))
        || (merchantKey && itemMerchant.includes(merchantKey));

      if (!isSimilar) return item;

      updatedCount += 1;
      return {
        ...item,
        merchant: source.merchant,
        category: source.category,
        apply_to_future: source.apply_to_future,
        needs_review: source.category === 'Chưa phân loại'
      };
    }));

    showToast(`Đã áp dụng chỉnh sửa cho ${updatedCount} dòng giao dịch tương tự`);
  };

  const handleConfirmImport = async () => {
    setSaving(true);
    try {
      const res = await confirmImport(previewData);
      showToast(res.message || 'Đã lưu giao dịch thành công!');
      setTimeout(() => {
        navigate('/transactions');
      }, 1500);
    } catch (err) {
      showToast(err.message || 'Lưu giao dịch thất bại', 'error');
      setSaving(false);
    }
  };

  // Helper formatting functions
  const formatCurrency = (amount, cur) => {
    try {
      return new Intl.NumberFormat('vi-VN', {
        style: 'currency',
        currency: cur || currency || 'EUR',
      }).format(amount);
    } catch {
      return `${amount} ${cur || currency || 'EUR'}`;
    }
  };

  const classificationSourceLabel = (source) => {
    switch (source) {
      case 'hybrid': return 'Keyword fallback';
      case 'fallback': return 'Needs review';
      case 'ml': return 'ML';
      case 'fuzzy': return 'Similar merchant';
      case 'exact': return 'Nơi giao dịch memory';
      default: return 'Review';
    }
  };

  const confidenceLabel = (score) => {
    if (typeof score !== 'number' || Number.isNaN(score)) return '';
    return `${Math.round(score * 100)}%`;
  };

  const needsReviewCount = previewData.filter(item => item.needs_review).length;
  const learningCount = previewData.filter(item => item.apply_to_future !== false).length;

  return (
    <div className="page-upload-root">
      <div className="page-header">
        <div>
          <h1 className="page-title">Tải lên</h1>
          <p className="page-subtitle">Nhập tệp sao kê CSV, PDF hoặc OFX, duyệt các gợi ý phân loại từ AI và lưu vào lịch sử.</p>
        </div>
        <div className="page-header-actions">
          <Link to="/transactions" className="btn btn-secondary btn-sm">Giao dịch</Link>
          <Link to="/settings" className="btn btn-secondary btn-sm">Cài đặt</Link>
        </div>
      </div>

      {previewData.length === 0 && (
        <section className="workflow-steps" aria-label="Bank import workflow">
          <article className="workflow-step">
            <span className="workflow-step-number">1</span>
            <div>
              <h3>Nhập từ Bank Simulator</h3>
              <p>Spectra tự động lấy dữ liệu giao dịch từ Bank Simulator theo tài khoản ngân hàng đang kết nối.</p>
            </div>
          </article>
          <article className="workflow-step">
            <span className="workflow-step-number">2</span>
            <div>
              <h3>Duyệt gợi ý từ AI</h3>
              <p>Kiểm tra và tinh chỉnh nhanh nơi giao dịch, danh mục chi tiêu được phân loại tự động bởi trí tuệ nhân tạo.</p>
            </div>
          </article>
          <article className="workflow-step">
            <span className="workflow-step-number">3</span>
            <div>
              <h3>Lưu & Huấn luyện</h3>
              <p>Lưu giao dịch vào lịch sử. Spectra sẽ ghi nhớ các phản hồi để tự động phân loại chính xác hơn trong tương lai.</p>
            </div>
          </article>
        </section>
      )}

      {previewData.length === 0 && !uploading && (
        <div className="upload-zone" id="uploadZone">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"
            strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.4, marginBottom: '12px' }}>
            <path d="M3 6h18" />
            <path d="M3 12h18" />
            <path d="M3 18h18" />
            <path d="M7 6v12" />
          </svg>
          <h3>Nhập giao dịch từ Bank Simulator</h3>
          <p>Bấm nút bên dưới để đồng bộ và tải các giao dịch mới nhất từ tài khoản ngân hàng của bạn.</p>
          <button className="btn btn-primary" type="button" onClick={importBank}>
            Tải các giao dịch mới
          </button>
        </div>
      )}

      {/* Uploading progress screen */}
      {uploading && (
        <div className="processing-inline-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '8px' }}>
            <span style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-muted)' }}>{step}</span>
            <span style={{ fontSize: '13px', fontWeight: 600, fontVariantNumeric: 'tabular-nums', color: 'var(--accent)' }}>
              {progress}%
            </span>
          </div>
          <div style={{ height: '6px', background: 'var(--bg-subtle)', borderRadius: '99px', overflow: 'hidden' }}>
            <div 
              style={{ height: '100%', width: `${progress}%`, background: 'var(--accent)', borderRadius: '99px', transition: 'width 0.25s ease' }}
            ></div>
          </div>
        </div>
      )}

      {/* Review Mode Panel */}
      {previewData.length > 0 && (
        <div className="preview-section visible" id="previewSection">
          <div className="preview-toolbar">
            <div>
              <h2 style={{ fontSize: '18px', fontWeight: 600 }}>Duyệt giao dịch trước khi lưu</h2>
              <div className="preview-meta">
                <span className="settings-badge local">{previewData.length} dòng giao dịch</span>
                {needsReviewCount > 0 && (
                  <span className="settings-badge warning">{needsReviewCount} dòng cần phân loại</span>
                )}
                <span className="settings-badge">{learningCount} mục sẽ được học</span>
              </div>
            </div>
            <div className="page-header-actions">
              <button className="btn btn-secondary" type="button" onClick={cancelPreview} disabled={saving}>
                Hủy
              </button>
              <button 
                className="btn btn-success" 
                id="confirmBtn" 
                onClick={handleConfirmImport}
                disabled={saving}
                style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                  strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                {saving ? 'Đang lưu...' : 'Xác nhận & Lưu'}
              </button>
            </div>
          </div>

          <div className="inline-banner">
            <strong>Chế độ duyệt trước khi nhập</strong>
            <span>Bạn có thể tinh chỉnh nhanh tên và danh mục trực tiếp. Bấm “Apply to similar” để áp dụng hàng loạt các dòng giống nhau. Hãy bật checkbox “Learn” để huấn luyện AI chính xác hơn cho lần sau.</span>
          </div>

          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Ngày</th>
                  <th>Nơi giao dịch</th>
                  <th>Danh mục gợi ý</th>
                  <th>Định kỳ</th>
                  <th>Learn</th>
                  <th style={{ textAlign: 'right' }}>Số tiền</th>
                  <th style={{ textAlign: 'right' }}>Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {previewData.map((t, index) => {
                  const isExpense = t.amount < 0;
                  const isUncat = t.category === 'Chưa phân loại';

                  // AI Suggestions layout
                  const sourceText = classificationSourceLabel(t.classification_source);
                  const confidenceText = confidenceLabel(t.category_confidence);
                  const suggestions = Array.isArray(t.category_suggestions)
                    ? t.category_suggestions.filter(item => item && item.category && item.category !== t.category).slice(0, 3)
                    : [];

                  return (
                    <tr key={t.id}>
                      <td>{t.date}</td>
                      <td>
                        <input
                          className="settings-input preview-input"
                          value={t.merchant}
                          onChange={(e) => updatePreviewField(index, 'merchant', e.target.value)}
                          aria-label="Merchant name"
                        />
                        <div className="table-cell-muted preview-raw">{t.original_description || '—'}</div>
                      </td>
                      <td>
                        <select 
                          className="settings-select preview-select"
                          value={t.category}
                          onChange={(e) => updatePreviewField(index, 'category', e.target.value)}
                          aria-label="Select category"
                        >
                          <option value="Chưa phân loại">Chưa phân loại</option>
                          {categories.map((c, i) => (
                            <option key={i} value={c}>{c}</option>
                          ))}
                        </select>
                        
                        {/* Suggestion Chips */}
                        {t.needs_review && (
                          <div className="preview-review-block" style={{ marginTop: '4px' }}>
                            <span className="settings-badge warning">
                              {sourceText}{confidenceText ? ` · ${confidenceText}` : ''}
                            </span>
                            {suggestions.length > 0 && (
                              <div className="preview-suggestions" style={{ display: 'flex', gap: '4px', marginTop: '4px' }}>
                                {suggestions.map((item, sIdx) => (
                                  <button
                                    key={sIdx}
                                    className="btn btn-secondary btn-sm preview-suggestion-btn"
                                    type="button"
                                    onClick={() => applyCategorySuggestion(index, item.category)}
                                  >
                                    {item.category}{item.score != null ? ` · ${Math.round(Number(item.score) * 100)}%` : ''}
                                  </button>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </td>
                      <td>
                        {t.recurring ? (
                          <select 
                            className="settings-select preview-select"
                            value={t.recurring}
                            onChange={(e) => updatePreviewField(index, 'recurring', e.target.value)}
                            aria-label="Select cadence"
                          >
                            <option value="">Không định kỳ</option>
                            <option value="Đăng ký định kỳ">Đăng ký định kỳ</option>
                            <option value="Thu nhập định kỳ">Thu nhập định kỳ</option>
                            {t.recurring !== 'Đăng ký định kỳ' && t.recurring !== 'Thu nhập định kỳ' && (
                              <option value={t.recurring}>{t.recurring}</option>
                            )}
                          </select>
                        ) : (
                          <div className="table-cell-muted" style={{ padding: '6px 10px' }}>—</div>
                        )}
                      </td>
                      <td>
                        <label className="mini-checkbox" style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}>
                          <input 
                            type="checkbox" 
                            checked={t.apply_to_future !== false} 
                            onChange={(e) => toggleLearning(index, e.target.checked)}
                          />
                          <span>Learn</span>
                        </label>
                      </td>
                      <td className={`amount ${isExpense ? 'expense' : 'income'}`} style={{ textAlign: 'right', fontWeight: 600 }}>
                        {formatCurrency(t.amount, t.currency)}
                      </td>
                      <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                        <button 
                          className="btn btn-secondary btn-sm" 
                          type="button" 
                          onClick={() => handleApplyToSimilar(index)}
                        >
                          Apply to similar
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
