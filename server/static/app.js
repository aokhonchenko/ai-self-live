let eventSource = null;
let startTime = Date.now();
let autoEnabled = false;
let nextStartTime = null;

function addLog(text, type = '') {
    const logArea = document.getElementById('logArea');
    const entry = document.createElement('div');
    entry.className = 'log-entry' + (type ? ' ' + type : '');
    const time = new Date().toLocaleTimeString('ru-RU');
    entry.textContent = `[${time}] ${text}`;
    logArea.appendChild(entry);
    logArea.scrollTop = logArea.scrollHeight;
    // Оставляем последние 1000 записей
    while (logArea.children.length > 1000) {
        logArea.removeChild(logArea.firstChild);
    }
}

function escapeHtml(text) {
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function renderInlineMarkdown(text) {
    return escapeHtml(text)
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
}

function renderMarkdown(markdown) {
    const lines = markdown.replace(/\r\n/g, '\n').split('\n');
    const html = [];
    let paragraph = [];
    let listType = null;
    let inCode = false;
    let codeLines = [];

    function flushParagraph() {
        if (paragraph.length === 0) return;
        html.push(`<p>${renderInlineMarkdown(paragraph.join(' '))}</p>`);
        paragraph = [];
    }

    function closeList() {
        if (!listType) return;
        html.push(`</${listType}>`);
        listType = null;
    }

    for (const rawLine of lines) {
        const line = rawLine.trimEnd();

        if (line.startsWith('```')) {
            if (inCode) {
                html.push(`<pre><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`);
                codeLines = [];
                inCode = false;
            } else {
                flushParagraph();
                closeList();
                inCode = true;
            }
            continue;
        }

        if (inCode) {
            codeLines.push(rawLine);
            continue;
        }

        if (line.trim() === '') {
            flushParagraph();
            closeList();
            continue;
        }

        const heading = /^(#{1,3})\s+(.+)$/.exec(line);
        if (heading) {
            flushParagraph();
            closeList();
            const level = heading[1].length;
            html.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
            continue;
        }

        const unordered = /^[-*]\s+(.+)$/.exec(line.trim());
        const ordered = /^\d+\.\s+(.+)$/.exec(line.trim());
        if (unordered || ordered) {
            flushParagraph();
            const nextType = unordered ? 'ul' : 'ol';
            if (listType !== nextType) {
                closeList();
                html.push(`<${nextType}>`);
                listType = nextType;
            }
            html.push(`<li>${renderInlineMarkdown((unordered || ordered)[1])}</li>`);
            continue;
        }

        closeList();
        paragraph.push(line.trim());
    }

    if (inCode) {
        html.push(`<pre><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`);
    }
    flushParagraph();
    closeList();
    return html.join('');
}

function setLastSessionMarkdown(markdown) {
    document.getElementById('lastSession').innerHTML = renderMarkdown(markdown);
}

function setCurrentPlanMarkdown(markdown) {
    document.getElementById('currentPlan').innerHTML = renderMarkdown(markdown);
}
function updateStatus(data) {
    const badge = document.getElementById('statusBadge');
    const statusText = document.getElementById('statusText');
    const btnStart = document.getElementById('btnStart');

    badge.className = 'status-badge';

    switch (data.status) {
        case 'idle':
            badge.classList.add('status-idle');
            statusText.textContent = 'Ожидание';
            btnStart.disabled = false;
            break;
        case 'running':
            badge.classList.add('status-running');
            statusText.textContent = 'Выполняется';
            btnStart.disabled = true;
            break;
        case 'auto':
            badge.classList.add('status-auto');
            statusText.textContent = 'Автосессия';
            btnStart.disabled = true;
            break;
    }

    if (data.auto_enabled !== undefined) {
        autoEnabled = data.auto_enabled;
        updateAutoToggle();
    }

    if (Object.prototype.hasOwnProperty.call(data, 'next_start_time')) {
        nextStartTime = data.next_start_time;
        updateNextStartTimer();
    }

    if (data.session_count !== undefined) {
        document.getElementById('sessionCount').textContent = data.session_count;
    }

    if (data.last_run_time) {
        document.getElementById('lastRunTime').textContent = data.last_run_time.split(' ')[1] || data.last_run_time;
    }
}

function updateAutoToggle() {
    const toggle = document.getElementById('autoToggle');
    const label = document.getElementById('autoLabel');
    if (autoEnabled) {
        toggle.classList.add('active');
        label.textContent = 'Автосессия включена';
    } else {
        toggle.classList.remove('active');
        label.textContent = 'Автосессия выключена';
    }
}

function connectSSE() {
    if (eventSource) {
        eventSource.close();
    }

    eventSource = new EventSource('/api/events');

    eventSource.onopen = () => {
        document.getElementById('connection').className = 'connection-indicator connected';
        document.getElementById('connection').querySelector('span:last-child').textContent = 'Подключено';
        addLog('Подключено к серверу', 'success');
    };

    eventSource.addEventListener('status', (e) => {
        const data = JSON.parse(e.data);
        updateStatus(data);
        if (data.message) {
            addLog(data.message, 'info');
        }
    });

    eventSource.addEventListener('session_log', (e) => {
        const data = JSON.parse(e.data);
        if (data.line !== undefined && data.line !== '') {
            addLog(data.line, 'session');
        }
    });
    eventSource.addEventListener('session_done', (e) => {
        const data = JSON.parse(e.data);
        if (data.success) {
            addLog(`Сессия #${data.count} завершена успешно`, 'success');
        } else {
            addLog(`Сессия #${data.count} завершена с ошибкой: ${data.error}`, 'error');
        }
        if (data.last_session) {
            setLastSessionMarkdown(data.last_session);
        }
        updateStatus({
            status: autoEnabled ? 'auto' : 'idle',
            session_count: data.count,
            last_run_time: data.time,
            next_start_time: data.next_start_time,
            next_start_delay_seconds: data.next_start_delay_seconds,
        });
    });

    eventSource.addEventListener('context_update', (e) => {
        const data = JSON.parse(e.data);
        // Обновить блок контекста из SSE-события (без дополнительного fetch)
        renderContextData(data);
    });

    eventSource.onerror = () => {
        document.getElementById('connection').className = 'connection-indicator disconnected';
        document.getElementById('connection').querySelector('span:last-child').textContent = 'Отключено';
        addLog('Соединение потеряно, переподключение...', 'error');
    };
}

async function startSession() {
    try {
        const resp = await fetch('/api/session/start', { method: 'POST' });
        const data = await resp.json();
        if (data.ok) {
            addLog('Запрос на запуск сессии отправлен', 'info');
        } else {
            addLog('Ошибка: ' + data.error, 'error');
        }
    } catch (e) {
        addLog('Ошибка запроса: ' + e.message, 'error');
    }
}

async function toggleAuto() {
    try {
        const resp = await fetch('/api/auto/toggle', { method: 'POST' });
        const data = await resp.json();
        if (data.ok) {
            addLog('Автосессия ' + (data.auto_enabled ? 'включена' : 'выключена'), 'info');
        }
    } catch (e) {
        addLog('Ошибка запроса: ' + e.message, 'error');
    }
}

async function loadLastSession() {
    try {
        const resp = await fetch('/api/last-session');
        const data = await resp.json();
        setLastSessionMarkdown(data.content);
    } catch (e) {
        document.getElementById('lastSession').textContent = 'Ошибка загрузки: ' + e.message;
    }
}

async function loadCurrentPlan() {
    try {
        const resp = await fetch('/api/current-plan');
        const data = await resp.json();
        setCurrentPlanMarkdown(data.content);
    } catch (e) {
        document.getElementById('currentPlan').textContent = 'Ошибка загрузки: ' + e.message;
    }
}

async function loadProjectMetrics() {
    try {
        const resp = await fetch('/api/project-metrics');
        const data = await resp.json();
        document.getElementById('metricTests').textContent = data.total_tests ?? '—';
        document.getElementById('metricCoverage').textContent = data.coverage ?? '—';
        document.getElementById('metricScripts').textContent = data.script_count ?? '—';
        document.getElementById('metricTools').textContent = data.tool_count ?? '—';
        document.getElementById('metricNoise').textContent = (data.noise_ratio ?? '—') + '%';
    } catch (e) {
        document.getElementById('metricTests').textContent = 'ошибка';
        document.getElementById('metricCoverage').textContent = 'ошибка';
        document.getElementById('metricScripts').textContent = 'ошибка';
        document.getElementById('metricTools').textContent = 'ошибка';
    }
}

const HEALTH_ICONS = { good: '✅', warning: '⚡', critical: '⚠️', error: '❌' };

/** Отрендерить данные контекста в DOM-элементы блока "Состояние контекста". */
function renderContextData(data) {
    // Здоровье
    const healthEl = document.getElementById('ctxHealth');
    healthEl.textContent = (HEALTH_ICONS[data.health] || '❓') + ' ' + (data.health_label || '—');

    // Токены, строки, вопросы
    document.getElementById('ctxTokens').textContent = data.total_tokens ?? '—';
    document.getElementById('ctxLines').textContent = data.total_lines ?? '—';
    document.getElementById('ctxQuestions').textContent = data.questions_open ?? '—';

    // Секции
    const sectionsEl = document.getElementById('ctxSections');
    if (data.sections && data.sections.length > 0) {
        let html = '';
        for (const s of data.sections) {
            if (!s.exists) {
                html += `<div class="ctx-row"><span class="ctx-icon ctx-missing">✗</span><span class="ctx-name">${s.name}</span><span class="ctx-meta ctx-missing">не найден</span></div>`;
            } else {
                const icon = s.stale ? '📅' : '✅';
                const dateStr = s.date ? s.date.slice(0, 10) : '—';
                const meta = `${s.tokens} ток. · ${s.lines} стр. · ${dateStr}`;
                html += `<div class="ctx-row"><span class="ctx-icon ${s.stale ? 'ctx-stale' : ''}">${icon}</span><span class="ctx-name">${s.name}</span><span class="ctx-meta">${meta}</span></div>`;
            }
        }
        sectionsEl.innerHTML = html;
    } else {
        sectionsEl.textContent = 'Нет данных';
    }

    // Рекомендации
    const recsEl = document.getElementById('ctxRecs');
    if (data.recommendations && data.recommendations.length > 0) {
        let html = '';
        for (const r of data.recommendations) {
            let cls = 'warn';
            if (r.includes('✅') || r.includes('Хорошо')) cls = 'good';
            if (r.includes('⚠️') || r.includes('Критично') || r.includes('Ошибка')) cls = 'bad';
            html += `<div class="ctx-rec ${cls}">${r}</div>`;
        }
        recsEl.innerHTML = html;
    } else {
        recsEl.innerHTML = '';
    }
}

async function loadContextAnalysis() {
    try {
        const resp = await fetch('/api/context-analysis');
        const data = await resp.json();
        renderContextData(data);
    } catch (e) {
        document.getElementById('ctxHealth').textContent = 'ошибка';
        document.getElementById('ctxSections').textContent = 'Ошибка загрузки: ' + e.message;
    }
}

function formatDuration(totalSeconds) {
    const seconds = Math.max(0, Math.ceil(totalSeconds));
    const min = Math.floor(seconds / 60);
    const sec = seconds % 60;
    return `${min}:${sec.toString().padStart(2, '0')}`;
}

function updateNextStartTimer() {
    const value = document.getElementById('nextStartValue');
    if (!autoEnabled) {
        value.textContent = '—';
        return;
    }
    if (!nextStartTime) {
        value.textContent = 'идёт';
        return;
    }
    const remaining = nextStartTime - Date.now() / 1000;
    value.textContent = remaining <= 0 ? 'сейчас' : formatDuration(remaining);
}

// Обновление таймеров
setInterval(() => {
    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    document.getElementById('uptimeValue').textContent = formatDuration(elapsed);
    updateNextStartTimer();
}, 1000);

// Инициализация
loadProjectMetrics();
loadCurrentPlan();
loadContextAnalysis();
loadLastSession();
connectSSE();

async function compressMemory() {
    const btn = document.getElementById('btnCompress');
    const result = document.getElementById('compressResult');
    btn.disabled = true;
    btn.textContent = '⏳ Сжатие...';
    result.textContent = '';
    try {
        const resp = await fetch('/api/compress', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ dry_run: false, keep_recent: 5 }),
        });
        const data = await resp.json();
        if (data.ok) {
            result.textContent = `✅ ${data.reduction_pct}% → ${data.compressed_lines} строк (было ${data.original_lines})`;
            result.style.color = 'var(--green)';
            addLog(`Память сжата: ${data.original_lines} → ${data.compressed_lines} строк (-${data.reduction_pct}%)`, 'success');
            // Обновить last_session после сжатия
            loadLastSession();
        } else {
            result.textContent = '❌ ' + (data.error || 'Ошибка');
            result.style.color = 'var(--red)';
            addLog('Ошибка сжатия: ' + data.error, 'error');
        }
    } catch (e) {
        result.textContent = '❌ ' + e.message;
        result.style.color = 'var(--red)';
        addLog('Ошибка запроса: ' + e.message, 'error');
    }
    btn.disabled = false;
    btn.textContent = '🗜️ Сжать память';
}
