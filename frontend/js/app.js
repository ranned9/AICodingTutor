document.addEventListener('DOMContentLoaded', () => {
    const editor = new CodeEditor(document.getElementById('codeEditor'));
    const renderer = new CanvasRenderer(document.getElementById('memoryCanvas'));
    const slider = new TimelineSlider(document.getElementById('timelineSlider'));

    let sessionId = null;
    let currentStep = 0;
    let totalSteps = 0;
    let snapshots = [];
    let isRunning = false;

    function renderSnapshot(snap) {
        renderer.render(snap);
        if (snap && snap.line) {
            editor.highlightLine(snap.line);
        } else {
            editor.clearHighlight();
        }
    }

    let autoPlayTimer = null;
    function autoPlay(snaps, onComplete) {
        if (autoPlayTimer) { clearTimeout(autoPlayTimer); autoPlayTimer = null; }
        let idx = 0;
        const delay = snaps.length > 50 ? 100 : snaps.length > 20 ? 300 : 500;
        function playNext() {
            if (idx >= snaps.length) {
                autoPlayTimer = null;
                if (onComplete) onComplete();
                return;
            }
            currentStep = idx;
            renderSnapshot(snaps[idx]);
            slider.setCurrentStep(idx);
            idx++;
            autoPlayTimer = setTimeout(playNext, delay);
        }
        playNext();
    }

    function stopAutoPlay() {
        if (autoPlayTimer) { clearTimeout(autoPlayTimer); autoPlayTimer = null; }
    }

    const toast = document.getElementById('toast');
    function showToast(msg, type = '') {
        toast.textContent = msg;
        toast.className = `toast ${type}`;
        setTimeout(() => toast.classList.add('hidden'), 3000);
    }

    async function loadCases() {
        const resp = await APIClient.listCases();
        if (resp.code === 0 && resp.data) {
            const selector = document.getElementById('caseSelector');
            resp.data.forEach(c => {
                const opt = document.createElement('option');
                opt.value = c.case_id;
                opt.textContent = `[${c.category}] ${c.title}`;
                selector.appendChild(opt);
            });
        }
    }

    document.getElementById('caseSelector').addEventListener('change', async (e) => {
        const caseId = e.target.value;
        if (!caseId) return;
        const resp = await APIClient.getCase(caseId);
        if (resp.code === 0 && resp.data) {
            editor.setCode(resp.data.code);
            showToast('案例已加载', 'success');
        } else {
            showToast(resp.message, 'error');
        }
    });

    function setRunning(running) {
        isRunning = running;
        document.getElementById('btnRun').disabled = running;
        document.getElementById('btnStop').disabled = !running;
        const mode = document.getElementById('debugMode').value;
        document.getElementById('btnStep').disabled = !running || mode !== 'step';
        document.getElementById('btnContinue').disabled = !running || mode !== 'breakpoint';
    }

    document.getElementById('btnRun').addEventListener('click', async () => {
        const code = editor.getCode();
        if (!code.trim()) {
            showToast('请先输入C代码', 'error');
            return;
        }
        const mode = document.getElementById('debugMode').value;
        const breakpoints = editor.getBreakpoints();

        setRunning(true);
        stopAutoPlay();
        snapshots = [];
        sessionId = null;
        currentStep = 0;
        totalSteps = 0;
        slider.setMeta(0, []);
        const resp = await APIClient.startDebug(code, mode, breakpoints);

        if (resp.code !== 0) {
            editor.clearErrorLine();
            if (resp.data && resp.data.snapshots && resp.data.snapshots.length > 0) {
                sessionId = resp.data.session_id;
                snapshots = resp.data.snapshots;
                totalSteps = resp.data.total_steps || snapshots.length;
                const events = snapshots.map((s, i) => ({ step: i, event: s.event }));
                slider.setMeta(totalSteps, events);
                if (resp.data.crash_line) {
                    editor.markErrorLine(resp.data.crash_line);
                }
                showToast(resp.message + '，已采集崩溃前快照', 'error');
                await autoPlay(snapshots, () => {
                    setRunning(false);
                });
            } else {
                showToast(resp.message, 'error');
                setRunning(false);
            }
            return;
        }

        sessionId = resp.data.session_id;

        if (mode === 'full') {
            snapshots = resp.data.snapshots || [];
            totalSteps = resp.data.total_steps || snapshots.length;
            const events = snapshots.map((s, i) => ({ step: i, event: s.event }));
            slider.setMeta(totalSteps, events);
            if (snapshots.length > 0) {
                showToast('正在自动播放执行过程...', '');
                await autoPlay(snapshots, () => {
                    setRunning(false);
                    showToast(`执行完成，共${totalSteps}步，可拖动滑块回溯`, 'success');
                });
            } else {
                setRunning(false);
                showToast('执行完成，无快照数据', 'success');
            }
        } else {
            const snap = resp.data.snapshot;
            if (snap) {
                renderSnapshot(snap);
                currentStep = resp.data.current_step || 0;
            }
            if (resp.data.finished) {
                setRunning(false);
                showToast('执行完成', 'success');
            }
            const metaResp = await APIClient.getSnapshotMeta(sessionId);
            if (metaResp.code === 0) {
                totalSteps = metaResp.data.total_steps;
                slider.setMeta(totalSteps, metaResp.data.events);
            }
        }
    });

    document.getElementById('btnStep').addEventListener('click', async () => {
        if (!sessionId) return;
        const resp = await APIClient.step(sessionId);
        if (resp.code !== 0) {
            showToast(resp.message, 'error');
            return;
        }
        if (resp.data.snapshot) {
            renderSnapshot(resp.data.snapshot);
            currentStep = resp.data.current_step;
            slider.setCurrentStep(currentStep);
        }
        if (resp.data.finished) {
            setRunning(false);
            showToast('执行完成', 'success');
        }
    });

    document.getElementById('btnContinue').addEventListener('click', async () => {
        if (!sessionId) return;
        const resp = await APIClient.continueExecution(sessionId);
        if (resp.code !== 0) {
            showToast(resp.message, 'error');
            return;
        }
        if (resp.data.snapshot) {
            renderSnapshot(resp.data.snapshot);
            currentStep = resp.data.current_step;
            slider.setCurrentStep(currentStep);
        }
        if (resp.data.finished) {
            setRunning(false);
            showToast('执行完成', 'success');
        }
    });

    document.getElementById('btnStop').addEventListener('click', async () => {
        stopAutoPlay();
        if (!sessionId) return;
        await APIClient.stop(sessionId);
        setRunning(false);
        showToast('已停止', 'success');
    });

    slider.onStepChange = async (step) => {
        stopAutoPlay();
        currentStep = step;
        if (snapshots.length > 0 && step < snapshots.length) {
            renderSnapshot(snapshots[step]);
        } else if (sessionId) {
            const resp = await APIClient.getSnapshot(sessionId, step);
            if (resp.code === 0 && resp.data) {
                renderSnapshot(resp.data);
            }
        }
    };

    document.getElementById('btnAsk').addEventListener('click', async () => {
        const question = document.getElementById('aiQuestion').value.trim();
        if (!question) {
            showToast('请输入您的问题', 'error');
            return;
        }
        if (!sessionId) {
            showToast('请先执行调试并选择快照节点', 'error');
            return;
        }
        const answerEl = document.getElementById('aiAnswer');
        answerEl.textContent = '正在思考...';
        const resp = await APIClient.askAI(sessionId, currentStep, question);
        if (resp.code === 0 && resp.data) {
            answerEl.textContent = resp.data.answer;
        } else {
            answerEl.textContent = resp.message;
        }
    });

    document.getElementById('aiQuestion').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            document.getElementById('btnAsk').click();
        }
    });

    loadCases();
});