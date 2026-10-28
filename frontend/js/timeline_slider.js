class TimelineSlider {
    constructor(container) {
        this.container = container;
        this.totalSteps = 0;
        this.currentStep = 0;
        this.events = [];
        this.onStepChange = null;
        this._render();
    }

    _render() {
        this.container.innerHTML = '';
        if (this.totalSteps === 0) {
            this.container.innerHTML = '<div style="text-align:center;color:#999;line-height:40px;">执行调试后显示时序滑块</div>';
            return;
        }

        const track = document.createElement('div');
        track.className = 'timeline-track';
        track.style.cssText = 'position:relative;height:100%;width:100%;';

        const bar = document.createElement('div');
        bar.className = 'timeline-bar';
        bar.style.cssText = 'position:absolute;top:15px;left:0;right:0;height:10px;background:#ddd;border-radius:5px;';

        const progress = document.createElement('div');
        progress.className = 'timeline-progress';
        progress.style.cssText = 'position:absolute;top:15px;left:0;height:10px;background:#2196f3;border-radius:5px;';
        this.progress = progress;

        const handle = document.createElement('div');
        handle.className = 'timeline-handle';
        handle.style.cssText = 'position:absolute;top:10px;width:20px;height:20px;background:#2196f3;border-radius:50%;cursor:pointer;transform:translateX(-50%);z-index:10;';
        this.handle = handle;

        const eventColors = {
            malloc: '#4caf50',
            free: '#f44336',
            function_call: '#2196f3',
            function_return: '#ff9800',
        };

        this.eventMarkers = [];
        this.events.forEach((e) => {
            if (e.event && e.event !== 'none') {
                const marker = document.createElement('div');
                marker.className = 'event-marker';
                const color = eventColors[e.event] || '#999';
                marker.style.cssText = `position:absolute;top:8px;width:4px;height:24px;background:${color};cursor:pointer;z-index:5;`;
                marker.title = `步骤${e.step}: ${e.event}`;
                marker.dataset.step = e.step;
                marker.addEventListener('click', (ev) => {
                    ev.stopPropagation();
                    this._gotoStep(parseInt(marker.dataset.step));
                });
                this.eventMarkers.push({ el: marker, step: e.step });
            }
        });

        track.appendChild(bar);
        track.appendChild(progress);
        this.eventMarkers.forEach(m => track.appendChild(m.el));
        track.appendChild(handle);

        this.track = track;
        this.container.appendChild(track);
        this._updatePositions();

        let isDragging = false;
        handle.addEventListener('mousedown', () => { isDragging = true; });
        document.addEventListener('mouseup', () => { isDragging = false; });
        document.addEventListener('mousemove', (e) => {
            if (isDragging) {
                const rect = track.getBoundingClientRect();
                let ratio = (e.clientX - rect.left) / rect.width;
                ratio = Math.max(0, Math.min(1, ratio));
                const step = Math.round(ratio * (this.totalSteps - 1));
                this._gotoStep(step);
            }
        });

        track.addEventListener('click', (e) => {
            if (e.target === track || e.target === bar) {
                const rect = track.getBoundingClientRect();
                let ratio = (e.clientX - rect.left) / rect.width;
                ratio = Math.max(0, Math.min(1, ratio));
                const step = Math.round(ratio * (this.totalSteps - 1));
                this._gotoStep(step);
            }
        });
    }

    _gotoStep(step) {
        step = Math.max(0, Math.min(this.totalSteps - 1, step));
        this.currentStep = step;
        this._updatePositions();
        if (this.onStepChange) this.onStepChange(step);
    }

    _updatePositions() {
        if (this.totalSteps <= 1) {
            this.handle.style.left = '0%';
            this.progress.style.width = '100%';
        } else {
            const ratio = this.currentStep / (this.totalSteps - 1);
            this.handle.style.left = `${ratio * 100}%`;
            this.progress.style.width = `${ratio * 100}%`;
        }
        this.eventMarkers.forEach(m => {
            if (this.totalSteps > 1) {
                const ratio = m.step / (this.totalSteps - 1);
                m.el.style.left = `${ratio * 100}%`;
            } else {
                m.el.style.left = '0%';
            }
        });
    }

    setMeta(totalSteps, events) {
        this.totalSteps = totalSteps;
        this.events = events || [];
        this.currentStep = 0;
        this._render();
    }

    setCurrentStep(step) {
        this.currentStep = Math.max(0, Math.min(this.totalSteps - 1, step));
        this._updatePositions();
    }
}