
    let settingsCategories = [];

    function escapeHtml(value) {
        return String(value ?? '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#39;');
    }

    function ordSuffix(d) {
        if (d >= 11 && d <= 13) return 'th';
        switch (d % 10) {
            case 1: return 'st';
            case 2: return 'nd';
            case 3: return 'rd';
            default: return 'th';
        }
    }

    function formatCycleOverview(settings) {
        if ((settings.cycle_mode || 'fixed') === 'last_business_day') {
            return 'Last business day';
        }
        const day = settings.fixed_cycle_start_day || settings.cycle_start_day || settings.pay_day || 1;
        return `Fixed day · ${day}${ordSuffix(day)}`;
    }

    function updateSettingsOverview(settings) {
        const requiresCurrencySetup = Boolean(settings.requires_base_currency_setup);
        const setupCard = document.getElementById('setupStatusCard');
        const setupValue = document.getElementById('setupStatusValue');
        const setupHint = document.getElementById('setupStatusHint');
        const setupAction = document.getElementById('setupStatusAction');
        const currencyValue = document.getElementById('overviewCurrencyValue');
        const currencyHint = document.getElementById('overviewCurrencyHint');
        const cycleValue = document.getElementById('overviewCycleValue');
        const cycleHint = document.getElementById('overviewCycleHint');
        const dataValue = document.getElementById('overviewDataValue');
        const dataHint = document.getElementById('overviewDataHint');

        if (setupCard) {
            setupCard.classList.toggle('is-warning', requiresCurrencySetup);
        }
        if (setupValue) {
            setupValue.textContent = requiresCurrencySetup ? 'Cần thiết lập' : 'Sẵn sàng';
        }
        if (setupHint) {
            setupHint.textContent = requiresCurrencySetup
                ? 'Chọn tiền tệ gốc trước khi dùng Spectra.'
                : 'Core preferences are configured and ready to use.';
        }
        if (setupAction) {
            setupAction.textContent = requiresCurrencySetup ? 'Chọn tiền tệ gốc' : 'Xem thiết lập';
            setupAction.setAttribute('href', requiresCurrencySetup ? '#settings-currency' : '#settings-setup');
        }

        if (currencyValue) {
            currencyValue.textContent = String(settings.currency || '—').toUpperCase();
        }
        if (currencyHint) {
            currencyHint.textContent = requiresCurrencySetup
                ? 'Bắt buộc before the first real workflow.'
                : 'Used across charts, budgets, and trends.';
        }

        if (cycleValue) {
            cycleValue.textContent = formatCycleOverview(settings);
        }
        if (cycleHint) {
            cycleHint.textContent = settings.current_cycle?.label
                ? `Chu kỳ hiện tại: ${settings.current_cycle.label}`
                : 'Used for dashboard, budgets, and trends.';
        }

        if (dataValue) {
            dataValue.textContent = `${Number(settings.tx_count || 0).toLocaleString()} tx`;
        }
        if (dataHint) {
            const merchantCount = Number(settings.merchant_count || 0).toLocaleString();
            const feedbackCount = Number(settings.feedback_count || 0).toLocaleString();
            dataHint.textContent = `${merchantCount} learned merchants · ${feedbackCount} feedback events`;
        }
    }

    function getCycleDayValue() {
        return parseInt(document.getElementById('cycleStartDay').value, 10) || 1;
    }

    function getCycleModeValue() {
        return document.getElementById('cycleMode')?.value || 'fixed';
    }

    const MAX_CYCLE_DAY = 28;

    function setCycleDayValue(day) {
        const clamped = Math.max(1, Math.min(MAX_CYCLE_DAY, day));
        document.getElementById('cycleStartDay').value = String(clamped);
        document.getElementById('cycleStartDayNum').textContent = String(clamped);
        document.getElementById('cycleStartDayOrd').textContent = ordSuffix(clamped);
    }

    function adjustCycleDayStep(delta) {
        const current = getCycleDayValue();
        // Wrap: dec from 1 -> 28, inc from 28 -> 1
        const next = ((current - 1 + delta + MAX_CYCLE_DAY) % MAX_CYCLE_DAY) + 1;
        setCycleDayValue(next);
    }

    function setCycleModeValue(mode) {
        const normalized = mode === 'last_business_day' ? 'last_business_day' : 'fixed';
        const select = document.getElementById('cycleMode');
        if (select) {
            select.value = normalized;
        }
        updateCycleModeUI();
    }

    function updateCycleModeUI() {
        const mode = getCycleModeValue();
        const stepper = document.getElementById('cycleFixedDayStepper');
        if (stepper) {
            stepper.style.display = mode === 'fixed' ? '' : 'none';
        }
    }

    function updateThemePreferenceUI(state = window.SpectraTheme?.getState()) {
        const select = document.getElementById('themePreference');
        const badge = document.getElementById('themeStatus');
        if (!select || !badge || !state) {
            return;
        }

        select.value = state.preference;

        if (state.preference === 'auto') {
            badge.textContent = `Auto · System ${state.effectiveTheme === 'dark' ? 'Dark' : 'Light'}`;
        } else {
            badge.textContent = state.effectiveTheme === 'dark' ? 'Dark' : 'Light';
        }

        badge.className = `settings-badge ${state.effectiveTheme === 'dark' ? 'theme-dark' : 'theme-light'}`;
    }

    function initThemePreference() {
        const select = document.getElementById('themePreference');
        if (!select || !window.SpectraTheme) {
            return;
        }

        updateThemePreferenceUI(window.SpectraTheme.getState());

        select.addEventListener('change', async event => {
            const target = event.target;
            const nextPreference = target.value;
            target.disabled = true;

            const immediateState = window.SpectraTheme.setPreference(nextPreference);
            updateThemePreferenceUI(immediateState);

            try {
                const res = await fetch('/api/settings/preferences', {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ theme_preference: nextPreference }),
                });
                const data = await res.json();
                if (!res.ok || !data.ok) {
                    throw new Error(data.error || 'Theme update failed');
                }

                const state = window.SpectraTheme.setPreference(data.theme_preference);
                updateThemePreferenceUI(state);
                showToast(`Theme đã đặt thành ${data.theme_preference[0].toUpperCase()}${data.theme_preference.slice(1)}`, 'info');
            } catch (err) {
                showToast('Theme applied locally. Failed to save preference on server.', 'error');
            } finally {
                target.disabled = false;
            }
        });

        window.addEventListener('spectra-theme-change', event => {
            updateThemePreferenceUI(event.detail || window.SpectraTheme.getState());
        });
    }

    function updateCycleUI(settings) {
        setCycleModeValue(settings.cycle_mode || 'fixed');
        setCycleDayValue(settings.fixed_cycle_start_day || settings.cycle_start_day || settings.pay_day || 1);
        const cycle = settings.current_cycle;
        if (cycle) {
            const startFmt = formatSpectraDate(cycle.start, { day: 'numeric', month: 'short', year: 'numeric' });
            // end is exclusive — subtract 1 day for display
            const endExclusive = parseSpectraDate(cycle.end);
            endExclusive.setDate(endExclusive.getDate() - 1);
            const endFmt = endExclusive.toLocaleDateString('en', { day: 'numeric', month: 'short', year: 'numeric' });
            const startEl = document.getElementById('cycleRangeStart');
            const endEl = document.getElementById('cycleRangeEnd');
            if (startEl) startEl.textContent = startFmt;
            if (endEl) endEl.textContent = endFmt;
        }
    }

    async function saveCyclePreference() {
        const button = document.getElementById('saveCycleBtn');
        if (!button) return;

        button.disabled = true;
        const previousLabel = button.textContent;
        button.textContent = '...';

        try {
            const mode = getCycleModeValue();
            const payload = { cycle_mode: mode };
            if (mode === 'fixed') {
                payload.pay_day = getCycleDayValue();
            }

            const res = await fetch('/api/settings/preferences', {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await res.json();
            if (!res.ok || !data.ok) {
                throw new Error(data.error || 'Chu kỳ tài chính update failed');
            }

            updateCycleUI(data);
            showToast(`Đã cập nhật chu kỳ: ${data.current_cycle.label}`);
        } catch (err) {
            showToast(err.message || 'Chu kỳ tài chính update failed', 'error');
        } finally {
            button.disabled = false;
            button.textContent = previousLabel;
        }
    }

    async function saveBaseCurrency() {
        const select = document.getElementById('baseCurrencySelect');
        const button = document.getElementById('saveCurrencyBtn');
        if (!select || !button) {
            return;
        }

        button.disabled = true;
        const previousLabel = button.textContent;
        button.textContent = '...';

        try {
            const res = await fetch('/api/settings/preferences', {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ base_currency: select.value }),
            });
            const data = await res.json();
            if (!res.ok || !data.ok) {
                throw new Error(data.error || 'Tiền tệ update failed');
            }

            await loadSettings();
            showToast(`Tiền tệ gốc đã đặt thành ${data.currency}`);
        } catch (err) {
            showToast(err.message || 'Tiền tệ update failed', 'error');
        } finally {
            button.disabled = false;
            button.textContent = previousLabel;
        }
    }

    function renderRules(rules) {
        const container = document.getElementById('rulesList');
        const summaryBadge = document.getElementById('rulesSummaryBadge');
        if (summaryBadge) {
            const active = (rules || []).filter(rule => rule.is_active).length;
            summaryBadge.textContent = `${active}/${(rules || []).length} active`;
            summaryBadge.className = `settings-badge ${active ? 'local' : ''}`;
        }

        if (!rules || rules.length === 0) {
            container.innerHTML = `
                <div class="empty-state" style="padding: 18px; margin-top: 8px;">
                    <p>No custom rules yet — Spectra already categorizes transactions automatically using built-in intelligence. Add a rule above to override or refine any category.</p>
                </div>
            `;
            return;
        }

        const rows = rules.map(rule => `
            <tr>
                <td>#${rule.priority}</td>
                <td>
                    <label class="mini-checkbox">
                        <input type="checkbox" ${rule.is_active ? 'checked' : ''} onchange="toggleRuleActive(${rule.id}, this.checked)">
                        <span>${rule.is_active ? 'On' : 'Off'}</span>
                    </label>
                </td>
                <td><code>${rule.rule_type}</code></td>
                <td><code>${escapeHtml(rule.pattern)}</code></td>
                <td>${rule.category}</td>
                <td style="text-align:right;">
                    <button class="btn btn-secondary btn-sm" type="button" onclick="moveRule(${rule.id}, 'up')">↑</button>
                    <button class="btn btn-secondary btn-sm" type="button" onclick="moveRule(${rule.id}, 'down')">↓</button>
                    <button class="btn btn-secondary btn-sm" onclick="deleteRule(${rule.id})">Delete</button>
                </td>
            </tr>
        `).join('');

        container.innerHTML = `
            <table>
                <thead>
                    <tr>
                        <th>Priority</th>
                        <th>Đang hoạt động</th>
                        <th>Type</th>
                        <th>Pattern</th>
                        <th>Danh mục</th>
                        <th style="text-align:right;">Action</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        `;
    }

    async function loadRules() {
        const res = await fetch('/api/settings/rules');
        const data = await res.json();
        renderRules(data.rules || []);
    }

    async function toggleRuleActive(ruleId, nextState) {
        const res = await fetch(`/api/settings/rules/${ruleId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_active: nextState }),
        });
        const data = await res.json();
        if (!res.ok || !data.ok) {
            showToast(data.error || 'Rule update failed', 'error');
            await loadRules();
            return;
        }

        showToast(`Rule ${nextState ? 'enabled' : 'disabled'}`, 'info');
        await loadRules();
    }

    async function moveRule(ruleId, direction) {
        const res = await fetch(`/api/settings/rules/${ruleId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ move: direction }),
        });
        const data = await res.json();
        if (!res.ok || !data.ok) {
            showToast(data.error || 'Rule reorder failed', 'error');
            return;
        }

        await loadRules();
    }

    async function createRule() {
        const ruleType = document.getElementById('ruleType').value;
        const pattern = document.getElementById('rulePattern').value.trim();
        const category = document.getElementById('ruleCategory').value.trim();

        if (!pattern || !category) {
            showToast('Pattern and category are required', 'error');
            return;
        }

        const res = await fetch('/api/settings/rules', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rule_type: ruleType, pattern, category }),
        });
        const data = await res.json();
        if (!res.ok || !data.ok) {
            showToast(data.error || 'Rule creation failed', 'error');
            return;
        }

        if (category && !settingsCategories.includes(category)) {
            settingsCategories.push(category);
            syncCategoryHints();
        }

        document.getElementById('rulePattern').value = '';
        document.getElementById('ruleCategory').value = '';
        showToast('Rule added');
        await loadRules();
    }

    async function deleteRule(ruleId) {
        const res = await fetch(`/api/settings/rules/${ruleId}`, { method: 'DELETE' });
        const data = await res.json();
        if (!res.ok || !data.ok) {
            showToast(data.error || 'Delete failed', 'error');
            return;
        }

        showToast('Rule deleted', 'info');
        await loadRules();
    }

    async function testRule() {
        const ruleType = document.getElementById('ruleType').value;
        const pattern = document.getElementById('rulePattern').value.trim();
        const sampleText = document.getElementById('ruleSampleText').value.trim();
        const output = document.getElementById('ruleTestResult');

        if (!pattern) {
            output.textContent = 'Enter a pattern first.';
            return;
        }

        const res = await fetch('/api/settings/rules/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rule_type: ruleType, pattern, sample_text: sampleText }),
        });
        const data = await res.json();
        if (!res.ok || !data.ok) {
            output.textContent = data.error || 'Rule test failed';
            showToast(data.error || 'Rule test failed', 'error');
            return;
        }

        const exampleHtml = (data.examples || []).map(example =>
            `<div><strong>${escapeHtml(example.merchant)}</strong> · ${escapeHtml(example.current_category)} · ${escapeHtml(example.date)}</div>`
        ).join('');
        output.innerHTML = `
            <div><strong>Sample match:</strong> ${data.matches_sample ? 'Yes' : 'No'}</div>
            <div><strong>Historical impact:</strong> ${data.impact_count} transaction(s)</div>
            ${exampleHtml ? `<div class="rule-test-examples">${exampleHtml}</div>` : ''}
        `;
    }

    function renderLearning(events) {
        const container = document.getElementById('learningList');
        if (!events || events.length === 0) {
            container.innerHTML = `
                <div class="empty-state" style="padding: 18px; margin-top: 8px;">
                    <p>No learning feedback recorded yet.</p>
                </div>
            `;
            return;
        }

        const rows = events.map(event => `
            <tr>
                <td>${escapeHtml(event.created_at.replace('T', ' ').slice(0, 16))}</td>
                <td>${escapeHtml(event.clean_name)}</td>
                <td>${escapeHtml(event.category)}</td>
                <td>${escapeHtml(event.source)}</td>
                <td>${event.apply_to_future ? '<span class="settings-badge local">Future</span>' : '<span class="settings-badge">Only this time</span>'}</td>
            </tr>
        `).join('');

        container.innerHTML = `
            <table>
                <thead>
                    <tr>
                        <th>When</th>
                        <th>Nơi giao dịch</th>
                        <th>Danh mục</th>
                        <th>Source</th>
                        <th>Scope</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        `;
    }

    async function loadLearning() {
        const res = await fetch('/api/settings/learning');
        const data = await res.json();
        if (!res.ok) {
            showToast(data.error || 'Learning summary failed', 'error');
            return;
        }

        renderLearning(data.events || []);
        document.getElementById('feedbackCount').textContent = (data.summary?.feedback_count || 0).toLocaleString();
        document.getElementById('futureLearningCount').textContent = (data.summary?.learned_future_count || 0).toLocaleString();
        document.getElementById('overrideCount').textContent = (data.summary?.override_count || 0).toLocaleString();
        document.getElementById('learningUncategorizedCount').textContent = (data.summary?.uncategorized_count || 0).toLocaleString();
    }

    async function reapplyLearning() {
        const res = await fetch('/api/settings/learning/reapply', { method: 'POST' });
        const data = await res.json();
        if (!res.ok || !data.ok) {
            showToast(data.error || 'Reapply failed', 'error');
            return;
        }

        showToast(`Updated ${data.updated} historical transaction(s)`);
        await Promise.all([loadLearning(), loadSettings(), loadRules()]);
    }

    function syncCategoryHints() {
        const datalist = document.getElementById('categoryHints');
        if (!datalist) {
            return;
        }
        datalist.innerHTML = settingsCategories
            .slice()
            .sort((a, b) => a.localeCompare(b))
            .map(cat => `<option value="${cat}"></option>`)
            .join('');
    }

    async function loadCategoryHints() {
        const res = await fetch('/api/categories');
        const data = await res.json();
        settingsCategories = Array.isArray(data.categories) ? data.categories : [];
        syncCategoryHints();
    }

    async function loadSettings() {
        try {
            const res = await fetch('/api/settings');
            const s = await res.json();

            if (window.SpectraTheme) {
                const state = window.SpectraTheme.setPreference(s.theme_preference || 'auto');
                updateThemePreferenceUI(state);
            }
            updateCycleUI(s);
            updateSettingsOverview(s);

            // Provider badge
            const provEl = document.getElementById('provider');
            const provLabels = { local: 'Local · offline', openai: 'OpenAI', gemini: 'Gemini' };
            provEl.textContent = provLabels[s.provider] || s.provider;
            provEl.className = `settings-badge ${s.provider === 'local' ? 'local' : 'cloud'}`;

            // Sheets status
            const sheetsEl = document.getElementById('sheetsStatus');
            sheetsEl.textContent = s.sheets_connected ? 'Connected' : 'Not configured';
            sheetsEl.className = `settings-badge ${s.sheets_connected ? 'local' : ''}`;

            // Tiền tệ
            const currencySelect = document.getElementById('baseCurrencySelect');
            if (currencySelect) {
                const available = Array.from(currencySelect.options).map(opt => opt.value);
                const normalizedTiền tệ = String(s.currency || 'EUR').toUpperCase();
                if (!available.includes(normalizedTiền tệ)) {
                    const custom = document.createElement('option');
                    custom.value = normalizedTiền tệ;
                    custom.textContent = normalizedTiền tệ;
                    currencySelect.appendChild(custom);
                }
                currencySelect.value = normalizedTiền tệ;
            }

            const requiresCurrencySetup = Boolean(s.requires_base_currency_setup);
            const currencyNotice = document.getElementById('currencySetupNotice');
            const currencyBadge = document.getElementById('currencySetupBadge');
            if (currencyNotice) {
                currencyNotice.style.display = requiresCurrencySetup ? '' : 'none';
            }
            if (currencyBadge) {
                currencyBadge.style.display = requiresCurrencySetup ? '' : 'none';
            }

            // DB stats
            document.getElementById('txCount').textContent = s.tx_count.toLocaleString();
            document.getElementById('merchantCount').textContent = s.merchant_count.toLocaleString();
            document.getElementById('categoryCount').textContent = s.category_count.toLocaleString();
            document.getElementById('activeRuleCount').textContent = (s.active_rule_count || 0).toLocaleString();
        } catch (err) {
            console.error('Cài đặt load error:', err);
        }
    }

    async function exportCSV() {
        try {
            // Fetch ALL transactions (paginate through)
            let allTx = [];
            let page = 1;
            while (true) {
                const res = await fetch(`/api/transactions?per_page=200&page=${page}`);
                const data = await res.json();
                allTx = allTx.concat(data.transactions);
                if (page >= data.pages) break;
                page++;
            }

            if (allTx.length === 0) {
                showToast('No transactions to export', 'error');
                return;
            }

            let csv = 'Ngày,Nơi giao dịch,Danh mục,Số tiền\n';
            for (const t of allTx) {
                csv += `${t.date},"${t.merchant}","${t.category}",${t.amount}\n`;
            }

            const blob = new Blob([csv], { type: 'text/csv' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `spectra_export_${new Date().toISOString().slice(0, 10)}.csv`;
            a.click();
            URL.revokeObjectURL(url);
            showToast(`Exported ${allTx.length} transactions`);
        } catch (err) {
            showToast('Export failed', 'error');
        }
    }

    async function resetDatabase() {
        const typed = window.prompt('Type RESET to permanently clear your local database.');
        if (typed !== 'RESET') {
            showToast('Reset cancelled', 'info');
            return;
        }

        const btn = document.getElementById('resetDbBtn');
        btn.disabled = true;
        const oldLabel = btn.textContent;
        btn.textContent = 'Resetting...';

        try {
            const res = await fetch('/api/settings/reset-db', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ confirm: 'RESET' }),
            });

            const data = await res.json();
            if (!res.ok || !data.ok) {
                showToast(data.error || 'Reset failed', 'error');
                return;
            }

            showToast('Database reset complete');
            await loadSettings();
            setTimeout(() => {
                window.location.href = '/transactions';
            }, 600);
        } catch (err) {
            showToast('Reset failed', 'error');
        } finally {
            btn.disabled = false;
            btn.textContent = oldLabel;
        }
    }

    setCycleDayValue(1);
    setCycleModeValue('fixed');
    initThemePreference();
    loadCategoryHints();
    loadRules();
    loadLearning();
    loadSettings();

    if (new URLSearchParams(window.location.search).get('setup') === 'currency') {
        showToast('First setup: choose your base currency to continue', 'info');
    }
