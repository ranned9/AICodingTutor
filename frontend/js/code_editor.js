class CodeEditor {
    constructor(container) {
        this.container = container;
        this.code = '';
        this.breakpoints = new Set();
        this.currentLine = 0;
        this.errorLine = 0;
        this.onChange = null;
        this._render();
    }

    _render() {
        this.container.innerHTML = '';
        const wrapper = document.createElement('div');
        wrapper.className = 'editor-wrapper';

        this.gutter = document.createElement('div');
        this.gutter.className = 'editor-gutter';

        this.editorArea = document.createElement('div');
        this.editorArea.className = 'editor-area';

        this.highlightLayer = document.createElement('div');
        this.highlightLayer.className = 'highlight-layer';

        this.textarea = document.createElement('textarea');
        this.textarea.className = 'editor-textarea';
        this.textarea.spellcheck = false;
        this.textarea.value = this.code;

        this.textarea.addEventListener('input', () => {
            this.code = this.textarea.value;
            if (this.errorLine > 0) {
                this.errorLine = 0;
            }
            this._updateGutter();
            if (this.onChange) this.onChange(this.code);
        });

        this.textarea.addEventListener('keydown', (e) => {
            if (e.key === 'Tab') {
                e.preventDefault();
                const start = this.textarea.selectionStart;
                const end = this.textarea.selectionEnd;
                this.textarea.value = this.textarea.value.substring(0, start) + '    ' + this.textarea.value.substring(end);
                this.textarea.selectionStart = this.textarea.selectionEnd = start + 4;
                this.code = this.textarea.value;
                this._updateGutter();
                if (this.onChange) this.onChange(this.code);
            } else if (e.key === '(' || e.key === '[' || e.key === '{') {
                e.preventDefault();
                const start = this.textarea.selectionStart;
                const end = this.textarea.selectionEnd;
                const close = e.key === '(' ? ')' : e.key === '[' ? ']' : '}';
                this.textarea.value = this.textarea.value.substring(0, start) + e.key + close + this.textarea.value.substring(end);
                this.textarea.selectionStart = this.textarea.selectionEnd = start + 1;
                this.code = this.textarea.value;
                this._updateGutter();
                if (this.onChange) this.onChange(this.code);
            }
        });

        this.textarea.addEventListener('scroll', () => {
            this.gutter.scrollTop = this.textarea.scrollTop;
            this.highlightLayer.scrollTop = this.textarea.scrollTop;
        });

        this.gutter.addEventListener('click', (e) => {
            const lineEl = e.target.closest('.gutter-line');
            if (lineEl) {
                const lineNum = parseInt(lineEl.dataset.line);
                this._toggleBreakpoint(lineNum);
            }
        });

        this.editorArea.appendChild(this.highlightLayer);
        this.editorArea.appendChild(this.textarea);
        wrapper.appendChild(this.gutter);
        wrapper.appendChild(this.editorArea);
        this.container.appendChild(wrapper);
        this._updateGutter();
    }

    _updateGutter() {
        const lines = this.code.split('\n');
        this.gutter.innerHTML = '';
        for (let i = 1; i <= lines.length; i++) {
            const lineEl = document.createElement('div');
            lineEl.className = 'gutter-line';
            if (i === this.currentLine) {
                lineEl.classList.add('current-line');
            }
            if (i === this.errorLine) {
                lineEl.classList.add('error-line');
            }
            lineEl.dataset.line = i;
            const numSpan = document.createElement('span');
            numSpan.className = 'line-number';
            numSpan.textContent = i;
            lineEl.appendChild(numSpan);
            if (this.breakpoints.has(i)) {
                const bp = document.createElement('span');
                bp.className = 'breakpoint-marker';
                bp.textContent = '●';
                lineEl.appendChild(bp);
            }
            if (i === this.errorLine) {
                const err = document.createElement('span');
                err.className = 'error-marker';
                err.textContent = '✖';
                lineEl.appendChild(err);
            } else if (i === this.currentLine) {
                const arrow = document.createElement('span');
                arrow.className = 'current-arrow';
                arrow.textContent = '▶';
                lineEl.appendChild(arrow);
            }
            this.gutter.appendChild(lineEl);
        }
        this._updateHighlight();
    }

    _updateHighlight() {
        this.highlightLayer.innerHTML = '';
        const lineHeight = 20;
        if (this.errorLine > 0) {
            const top = (this.errorLine - 1) * lineHeight;
            const bar = document.createElement('div');
            bar.className = 'highlight-bar error-bar';
            bar.style.top = top + 'px';
            this.highlightLayer.appendChild(bar);
        }
        if (this.currentLine > 0) {
            const top = (this.currentLine - 1) * lineHeight;
            const bar = document.createElement('div');
            bar.className = 'highlight-bar';
            bar.style.top = top + 'px';
            this.highlightLayer.appendChild(bar);
        }
    }

    _toggleBreakpoint(lineNum) {
        if (this.breakpoints.has(lineNum)) {
            this.breakpoints.delete(lineNum);
        } else {
            this.breakpoints.add(lineNum);
        }
        this._updateGutter();
    }

    getCode() {
        return this.code;
    }

    setCode(code) {
        this.code = code;
        this.textarea.value = code;
        this.errorLine = 0;
        this.currentLine = 0;
        this.breakpoints.clear();
        this._updateGutter();
    }

    getBreakpoints() {
        return Array.from(this.breakpoints).sort((a, b) => a - b);
    }

    clearBreakpoints() {
        this.breakpoints.clear();
        this._updateGutter();
    }

    highlightLine(line) {
        this.currentLine = line || 0;
        this._updateGutter();
    }

    clearHighlight() {
        this.currentLine = 0;
        this._updateGutter();
    }

    markErrorLine(line) {
        this.errorLine = line || 0;
        this._updateGutter();
    }

    clearErrorLine() {
        this.errorLine = 0;
        this._updateGutter();
    }
}