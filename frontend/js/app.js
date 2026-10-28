document.addEventListener('DOMContentLoaded', () => {
    const editor = new CodeEditor(document.getElementById('codeEditor'));
    const renderer = new CanvasRenderer(document.getElementById('memoryCanvas'));
    const slider = new TimelineSlider(document.getElementById('timelineSlider'));

    let sessionId = null;
    let currentStep = 0;
    let totalSteps = 0;
    let snapshots = [];
    let sessionStatus = 'idle';
    let isViewingHistory = false;
    let isAutoPlaying = false;
    let playbackGeneration = 0;

    function renderSnapshot(snap) {
        renderer.render(snap);
        if (snap && snap.line) {
            editor.highlightLine(snap.line);
        } else {
            editor.clearHighlight();
        }
        if (snap) {
            const labelEl = document.getElementById('timelineLabel');
            const lineEl = document.getElementById('timelineLine');
            const stepInfoEl = document.getElementById('memStepInfo');
            const statusEl = document.getElementById('runStatus');
            if (labelEl) labelEl.textContent = `第 ${currentStep} / ${totalSteps} 步`;
            if (lineEl) lineEl.textContent = `行 ${snap.line || '—'}`;
            if (stepInfoEl) stepInfoEl.textContent = `步骤 ${currentStep}/${totalSteps}`;
            if (statusEl) {
                statusEl.textContent = sessionStatus === 'paused' ? '已暂停' :
                    sessionStatus === 'running' ? '运行中' :
                    sessionStatus === 'completed' ? '已完成' :
                    sessionStatus === 'stopped' ? '已停止' :
                    sessionStatus === 'failed' ? '运行失败' : '待运行';
                statusEl.className = `run-status status-${sessionStatus}`;
            }
        }
    }

    function showTerminalStatus(status, steps = totalSteps, stop = null) {
        if (status === 'stopped') {
            setSessionStatus('stopped');
            showToast('程序已停止', '');
        } else if (status === 'failed') {
            setSessionStatus('failed');
            const crashLine = Number(stop?.line || 0);
            if (crashLine > 0) {
                editor.markErrorLine(crashLine);
                editor.highlightLine(crashLine);
            }
            const signalText = stop?.signal ? ` (${stop.signal})` : '';
            showToast(`程序异常终止${signalText}${crashLine ? `，错误位置：第 ${crashLine} 行` : ''}`, 'error');
        } else {
            setSessionStatus('completed');
            showToast(`执行完成，共${steps}步`, 'success');
        }
    }

    let autoPlayTimer = null;
    let pendingPlaybackResolve = null;
    function autoPlay(snaps, onComplete) {
        if (autoPlayTimer) { clearTimeout(autoPlayTimer); autoPlayTimer = null; }
        let idx = 0;
        const delay = snaps.length > 50 ? 100 : snaps.length > 20 ? 300 : 500;
        isAutoPlaying = true;
        function playNext() {
            if (idx >= snaps.length) {
                autoPlayTimer = null;
                isAutoPlaying = false;
                if (onComplete) onComplete();
                return;
            }
            currentStep = idx;
            isViewingHistory = false;
            renderSnapshot(snaps[idx]);
            slider.setCurrentStep(idx);
            idx++;
            autoPlayTimer = setTimeout(playNext, delay);
        }
        playNext();
    }

    function stopAutoPlay() {
        playbackGeneration++;
        if (autoPlayTimer) { clearTimeout(autoPlayTimer); autoPlayTimer = null; }
        if (pendingPlaybackResolve) {
            pendingPlaybackResolve();
            pendingPlaybackResolve = null;
        }
        isAutoPlaying = false;
    }

    async function autoPlayLive() {
        const generation = ++playbackGeneration;
        isAutoPlaying = true;
        updateButtonStates();
        const delay = 450;
        const startedAt = Date.now();
        const maxDurationMs = 30000;

        while (generation === playbackGeneration && sessionId && sessionStatus !== 'stopped') {
            if (Date.now() - startedAt >= maxDurationMs) {
                await APIClient.stop(sessionId);
                if (generation !== playbackGeneration) break;
                setSessionStatus('stopped');
                showToast('完整执行超过 30 秒，已自动停止；程序可能存在死循环', 'error');
                break;
            }
            await new Promise((resolve) => {
                pendingPlaybackResolve = resolve;
                autoPlayTimer = setTimeout(() => {
                    autoPlayTimer = null;
                    pendingPlaybackResolve = null;
                    resolve();
                }, delay);
            });
            if (generation !== playbackGeneration || !sessionId) break;

            const resp = await APIClient.stepInto(sessionId);
            if (generation !== playbackGeneration) break;
            if (resp.code !== 0) {
                await APIClient.stop(sessionId);
                if (generation !== playbackGeneration) break;
                setSessionStatus('failed');
                showToast(resp.message || '自动执行失败', 'error');
                break;
            }

            if (resp.data.snapshot) {
                currentStep = resp.data.current_step;
                snapshots[currentStep] = resp.data.snapshot;
                totalSteps = Math.max(totalSteps, currentStep + 1);
                renderSnapshot(resp.data.snapshot);
                const metaResp = await APIClient.getSnapshotMeta(sessionId);
                if (generation !== playbackGeneration) break;
                if (metaResp.code === 0) {
                    totalSteps = metaResp.data.total_steps;
                    slider.setMeta(totalSteps, metaResp.data.events);
                }
                slider.setCurrentStep(currentStep);
            }

            if (resp.data.finished || ['completed', 'failed', 'stopped'].includes(resp.data.status)) {
                showTerminalStatus(resp.data.status, totalSteps, resp.data.stop);
                break;
            }
        }
        if (generation === playbackGeneration) {
            isAutoPlaying = false;
            autoPlayTimer = null;
            updateButtonStates();
        }
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

    function updateButtonStates() {
        const mode = document.getElementById('debugMode').value;
        const engine = document.getElementById('engineSelect').value;
        const isActive = sessionStatus === 'paused' || sessionStatus === 'running';
        const canStep = isActive && !isAutoPlaying && !isViewingHistory;

        document.getElementById('btnRun').disabled = isActive || isAutoPlaying;
        document.getElementById('btnStop').disabled = !isActive && !isAutoPlaying;
        document.getElementById('btnStep').disabled = !canStep || mode === 'full';
        document.getElementById('btnStepInto').disabled = !canStep || mode === 'full' || engine !== 'gdb';
        document.getElementById('btnContinue').disabled = !canStep || mode === 'full';

        const statusEl = document.getElementById('runStatus');
        if (statusEl) {
            const statusText = isViewingHistory ? '回看中' :
                sessionStatus === 'paused' ? '已暂停' :
                sessionStatus === 'running' ? '运行中' :
                sessionStatus === 'completed' ? '已完成' :
                sessionStatus === 'stopped' ? '已停止' :
                sessionStatus === 'failed' ? '运行失败' : '待运行';
            statusEl.textContent = statusText;
            statusEl.className = `run-status status-${isViewingHistory ? 'viewing' : sessionStatus}`;
        }
    }

    function setSessionStatus(status) {
        sessionStatus = status;
        updateButtonStates();
    }

    document.getElementById('debugMode').addEventListener('change', updateButtonStates);
    document.getElementById('engineSelect').addEventListener('change', updateButtonStates);

    document.getElementById('btnRun').addEventListener('click', async () => {
        const code = editor.getCode();
        if (!code.trim()) {
            showToast('请先输入C代码', 'error');
            return;
        }
        const mode = document.getElementById('debugMode').value;
        const engine = document.getElementById('engineSelect').value;
        const breakpoints = editor.getBreakpoints();

        editor.clearErrorLine();
        setSessionStatus('running');
        stopAutoPlay();
        snapshots = [];
        sessionId = null;
        currentStep = 0;
        totalSteps = 0;
        isViewingHistory = false;
        slider.setMeta(0, []);
        const resp = await APIClient.startDebug(code, mode, breakpoints, engine);

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
                    setSessionStatus('completed');
                });
            } else {
                showToast(resp.message, 'error');
                setSessionStatus('idle');
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
                currentStep = resp.data.current_step || 0;
                renderSnapshot(snapshots[currentStep]);
                slider.setCurrentStep(currentStep);
                if (resp.data.finished || ['completed', 'failed', 'stopped'].includes(resp.data.status)) {
                    showTerminalStatus(resp.data.status, totalSteps, resp.data.stop);
                } else {
                    setSessionStatus('running');
                    showToast('正在自动执行，可随时停止...', '');
                    await autoPlayLive();
                }
            } else {
                if (resp.data.finished || ['completed', 'failed', 'stopped'].includes(resp.data.status)) {
                    showTerminalStatus(resp.data.status, totalSteps, resp.data.stop);
                } else {
                    setSessionStatus('failed');
                    showToast('调试会话未返回快照', 'error');
                }
            }
        } else {
            const snap = resp.data.snapshot;
            if (snap) {
                renderSnapshot(snap);
                currentStep = resp.data.current_step || 0;
            }
            if (resp.data.finished) {
                showTerminalStatus(resp.data.status, totalSteps, resp.data.stop);
            } else {
                setSessionStatus('paused');
            }
            const metaResp = await APIClient.getSnapshotMeta(sessionId);
            if (metaResp.code === 0) {
                totalSteps = metaResp.data.total_steps;
                slider.setMeta(totalSteps, metaResp.data.events);
            }
            updateButtonStates();
        }
    });

    async function executeStep(apiFn) {
        if (!sessionId) return;
        const resp = await apiFn(sessionId);
        if (resp.code !== 0) {
            showToast(resp.message, 'error');
            return;
        }
        isViewingHistory = false;
        if (resp.data.snapshot) {
            currentStep = resp.data.current_step;
            snapshots[currentStep] = resp.data.snapshot;
            totalSteps = Math.max(totalSteps, currentStep + 1);
            renderSnapshot(resp.data.snapshot);
            const metaResp = await APIClient.getSnapshotMeta(sessionId);
            if (metaResp.code === 0) {
                totalSteps = metaResp.data.total_steps;
                slider.setMeta(totalSteps, metaResp.data.events);
            }
            slider.setCurrentStep(currentStep);
        }
        if (resp.data.finished) {
            showTerminalStatus(resp.data.status, totalSteps, resp.data.stop);
        } else {
            setSessionStatus('paused');
        }
    }

    document.getElementById('btnStep').addEventListener('click', () => executeStep(APIClient.step));
    document.getElementById('btnStepInto').addEventListener('click', () => executeStep(APIClient.stepInto));
    document.getElementById('btnContinue').addEventListener('click', () => executeStep(APIClient.continueExecution));

    document.getElementById('btnStop').addEventListener('click', async () => {
        stopAutoPlay();
        if (!sessionId) {
            setSessionStatus('idle');
            return;
        }
        await APIClient.stop(sessionId);
        setSessionStatus('stopped');
        showToast('已停止', 'success');
    });

    slider.onStepChange = async (step) => {
        if (sessionStatus === 'running') {
            slider.setCurrentStep(currentStep);
            showToast('自动执行中，请先停止后再回看', '');
            return;
        }
        stopAutoPlay();
        currentStep = step;
        isViewingHistory = (step < totalSteps - 1) && (sessionStatus === 'paused' || sessionStatus === 'completed');
        if (snapshots.length > 0 && step < snapshots.length) {
            renderSnapshot(snapshots[step]);
        } else if (sessionId) {
            const resp = await APIClient.getSnapshot(sessionId, step);
            if (resp.code === 0 && resp.data) {
                renderSnapshot(resp.data);
            }
        }
        updateButtonStates();
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

    (async () => {
        try {
            const resp = await APIClient.diagnose();
            if (resp.code !== 0 && resp.data && resp.data.issues) {
                const el = document.getElementById('diagWarning');
                if (el) {
                    el.textContent = '工具链诊断: ' + resp.data.issues.join('; ');
                    el.style.display = 'block';
                }
            }
        } catch (e) { }
    })();
});
