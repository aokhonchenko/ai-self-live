"""CSS for the generated dashboard."""

STYLE = """
        :root {
            --bg: #0d1117;
            --bg-card: #161b22;
            --bg-hover: #1c2333;
            --border: #30363d;
            --text: #e6edf3;
            --text-muted: #8b949e;
            --accent: #58a6ff;
            --accent-dim: #1f6feb;
            --green: #3fb950;
            --yellow: #d29922;
            --red: #f85149;
            --purple: #bc8cff;
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
            padding: 20px;
            max-width: 1200px;
            margin: 0 auto;
        }
        
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px 0;
            border-bottom: 1px solid var(--border);
            margin-bottom: 24px;
        }
        
        header h1 {
            font-size: 24px;
            font-weight: 600;
        }
        
        header h1 span {
            color: var(--accent);
        }
        
        .meta {
            color: var(--text-muted);
            font-size: 14px;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }
        
        .stat-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px;
            text-align: center;
        }
        
        .stat-card .value {
            font-size: 32px;
            font-weight: 700;
            color: var(--accent);
        }
        
        .stat-card .label {
            font-size: 13px;
            color: var(--text-muted);
            margin-top: 4px;
        }
        
        .stat-card.green .value { color: var(--green); }
        .stat-card.yellow .value { color: var(--yellow); }
        .stat-card.purple .value { color: var(--purple); }
        
        .grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 24px;
        }
        
        @media (max-width: 768px) {
            .grid {
                grid-template-columns: 1fr;
            }
        }
        
        .card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 8px;
            overflow: hidden;
        }
        
        .card-header {
            padding: 12px 16px;
            border-bottom: 1px solid var(--border);
            font-weight: 600;
            font-size: 14px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .card-header .icon {
            font-size: 16px;
        }
        
        .card-body {
            padding: 16px;
            font-size: 14px;
            max-height: 400px;
            overflow-y: auto;
        }
        
        .card-body.full {
            max-height: none;
        }
        
        .card-body h2 { font-size: 18px; margin: 16px 0 8px; color: var(--text); }
        .card-body h3 { font-size: 15px; margin: 14px 0 6px; color: var(--text); }
        .card-body h4 { font-size: 14px; margin: 12px 0 4px; color: var(--text-muted); }
        
        .card-body p {
            margin: 6px 0;
            color: var(--text-muted);
        }
        
        .card-body ul {
            margin: 8px 0;
            padding-left: 20px;
        }
        
        .card-body li {
            margin: 4px 0;
            color: var(--text-muted);
        }
        
        .card-body li strong {
            color: var(--text);
        }
        
        .card-body code {
            background: rgba(110, 118, 129, 0.2);
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 13px;
            font-family: 'SF Mono', 'Fira Code', monospace;
        }
        
        .card-body pre {
            background: var(--bg);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 12px;
            overflow-x: auto;
            margin: 8px 0;
        }
        
        .card-body pre code {
            background: none;
            padding: 0;
        }
        
        .card-body table {
            width: 100%;
            border-collapse: collapse;
            margin: 8px 0;
            font-size: 13px;
        }
        
        .card-body th, .card-body td {
            padding: 8px 12px;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }
        
        .card-body th {
            color: var(--text-muted);
            font-weight: 600;
        }
        
        .card-body blockquote {
            border-left: 3px solid var(--accent-dim);
            padding: 8px 12px;
            margin: 8px 0;
            background: rgba(88, 166, 255, 0.05);
            border-radius: 0 4px 4px 0;
            color: var(--text-muted);
            font-style: italic;
        }
        
        .card-body hr {
            border: none;
            border-top: 1px solid var(--border);
            margin: 12px 0;
        }
        
        .task-list {
            list-style: none;
            padding-left: 0;
        }
        
        .task-list li {
            padding: 6px 0;
            border-bottom: 1px solid rgba(48, 54, 61, 0.5);
        }
        
        .task-list li:last-child {
            border-bottom: none;
        }
        
        .task-list .done {
            color: var(--green);
            text-decoration: line-through;
            opacity: 0.7;
        }
        
        .task-list .pending {
            color: var(--text);
        }
        
        .checkbox {
            margin-right: 8px;
        }
        
        .icon-ok { color: var(--green); }
        .icon-no { color: var(--red); }
        .icon-wait { color: var(--yellow); }
        
        .full-width {
            grid-column: 1 / -1;
        }
        
        .plan-section {
            margin-bottom: 16px;
        }
        
        .plan-section h3 {
            color: var(--accent);
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 8px;
        }
        
        footer {
            text-align: center;
            padding: 20px 0;
            color: var(--text-muted);
            font-size: 12px;
            border-top: 1px solid var(--border);
            margin-top: 20px;
        }
        
        .scroll-indicator {
            position: relative;
        }
        
        .scroll-indicator::after {
            content: '↓';
            position: absolute;
            bottom: 4px;
            right: 8px;
            color: var(--text-muted);
            opacity: 0.5;
            font-size: 12px;
        }
"""
