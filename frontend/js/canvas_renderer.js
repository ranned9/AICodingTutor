class CanvasRenderer {
    constructor(canvas) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.dpr = window.devicePixelRatio || 1;
        this._setupCanvas();
        this.prevFrameCount = 0;
        this.animProgress = 1;
        this.animType = null;
        this.currentSnapshot = null;
        this.animDuration = 400;
        this.scrollOffsets = { globals: 0, stack: 0, heap: 0 };
        this.contentHeights = { globals: 0, stack: 0, heap: 0 };
        this._lastLayout = null;
        this._dragState = null;
        this._resizeObserver = null;
        this._collapsedNodes = new Set();
        this._nodeHitAreas = [];
        this._pointerAnchors = [];
        this._heapAnchors = [];
        this._initWheel();
        this._initDrag();
        this._initClick();
        this._observeSize();
    }

    _initWheel() {
        this.canvas.addEventListener('wheel', (e) => {
            if (!this.currentSnapshot || !this._lastLayout) return;
            const rect = this.canvas.getBoundingClientRect();
            const mx = e.clientX - rect.left;
            const my = e.clientY - rect.top;
            const layout = this._lastLayout;
            let zone = null;
            if (mx >= layout.globals.x && mx <= layout.globals.x + layout.globals.w &&
                my >= layout.globals.y && my <= layout.globals.y + layout.globals.h) {
                zone = 'globals';
            } else if (mx >= layout.stack.x && mx <= layout.stack.x + layout.stack.w &&
                       my >= layout.stack.y && my <= layout.stack.y + layout.stack.h) {
                zone = 'stack';
            } else if (mx >= layout.heap.x && mx <= layout.heap.x + layout.heap.w &&
                       my >= layout.heap.y && my <= layout.heap.y + layout.heap.h) {
                zone = 'heap';
            }
            if (!zone) return;
            e.preventDefault();
            const viewH = layout[zone].h - 30;
            const contentH = this.contentHeights[zone];
            if (contentH <= viewH) return;
            const delta = e.deltaY > 0 ? 30 : -30;
            this.scrollOffsets[zone] = Math.max(0, Math.min(contentH - viewH, this.scrollOffsets[zone] + delta));
            this._draw();
        }, { passive: false });
    }

    _initDrag() {
        this.canvas.addEventListener('pointerdown', (e) => {
            if (!this.currentSnapshot || !this._lastLayout) return;
            const rect = this.canvas.getBoundingClientRect();
            const mx = (e.clientX - rect.left) * this.width / rect.width;
            const my = (e.clientY - rect.top) * this.height / rect.height;
            const layout = this._lastLayout;
            for (const zone of ['globals', 'stack', 'heap']) {
                const area = layout[zone];
                const viewH = area.h - 30;
                const contentH = this.contentHeights[zone];
                if (contentH <= viewH) continue;
                const barH = Math.max(20, viewH * viewH / contentH);
                const barY = area.y + 25 + (this.scrollOffsets[zone] / (contentH - viewH)) * (viewH - barH);
                const barX = area.x + area.w - 14;
                if (mx >= barX - 5 && mx <= barX + 14 && my >= barY - 6 && my <= barY + barH + 6) {
                    this._dragState = { zone, barH, viewH, contentH, startMy: my, startOffset: this.scrollOffsets[zone] };
                    this.canvas.style.cursor = 'grabbing';
                    this.canvas.setPointerCapture(e.pointerId);
                    e.preventDefault();
                    return;
                }
            }
        });

        this.canvas.addEventListener('pointermove', (e) => {
            if (!this._dragState) return;
            const rect = this.canvas.getBoundingClientRect();
            const my = (e.clientY - rect.top) * this.height / rect.height;
            const ds = this._dragState;
            const dy = my - ds.startMy;
            const scrollRange = ds.contentH - ds.viewH;
            const barRange = ds.viewH - ds.barH;
            if (barRange <= 0) return;
            const newOffset = ds.startOffset + (dy / barRange) * scrollRange;
            this.scrollOffsets[ds.zone] = Math.max(0, Math.min(scrollRange, newOffset));
            this._draw();
        });

        const endDrag = () => {
            if (this._dragState) {
                this._dragState = null;
                this.canvas.style.cursor = '';
            }
        };
        this.canvas.addEventListener('pointerup', endDrag);
        this.canvas.addEventListener('pointercancel', endDrag);
        this.canvas.addEventListener('lostpointercapture', endDrag);
    }

    _initClick() {
        this.canvas.addEventListener('click', (e) => {
            if (!this.currentSnapshot || !this._nodeHitAreas.length) return;
            const rect = this.canvas.getBoundingClientRect();
            const mx = (e.clientX - rect.left) * this.width / rect.width;
            const my = (e.clientY - rect.top) * this.height / rect.height;
            for (const hit of this._nodeHitAreas) {
                if (mx >= hit.x && mx <= hit.x + hit.w &&
                    my >= hit.y && my <= hit.y + hit.h) {
                    if (hit.collapsible) {
                        if (this._collapsedNodes.has(hit.path)) {
                            this._collapsedNodes.delete(hit.path);
                        } else {
                            this._collapsedNodes.add(hit.path);
                        }
                        this._draw();
                    }
                    return;
                }
            }
        });
    }

    _setupCanvas() {
        const rect = this.canvas.getBoundingClientRect();
        const width = Math.max(1, Math.round(rect.width || this.canvas.clientWidth || 600));
        const height = Math.max(1, Math.round(rect.height || this.canvas.clientHeight || 500));
        this._resizeCanvas(width, height);
    }

    _resizeCanvas(width, height) {
        this.width = Math.max(1, Math.round(width));
        this.height = Math.max(1, Math.round(height));
        const pixelWidth = Math.round(this.width * this.dpr);
        const pixelHeight = Math.round(this.height * this.dpr);
        if (this.canvas.width !== pixelWidth || this.canvas.height !== pixelHeight) {
            this.canvas.width = pixelWidth;
            this.canvas.height = pixelHeight;
        }
        this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
        this._draw();
    }

    _observeSize() {
        if (typeof ResizeObserver === 'undefined') return;
        this._resizeObserver = new ResizeObserver((entries) => {
            const rect = entries[0]?.contentRect;
            if (!rect || rect.width <= 0 || rect.height <= 0) return;
            if (Math.round(rect.width) !== this.width || Math.round(rect.height) !== this.height) {
                this._resizeCanvas(rect.width, rect.height);
            }
        });
        this._resizeObserver.observe(this.canvas);
    }

    render(snapshot) {
        const frameCount = snapshot ? (snapshot.stack_frames || []).length : 0;

        if (frameCount > this.prevFrameCount) {
            this.animType = 'push';
            this.animProgress = 0;
        } else if (frameCount < this.prevFrameCount) {
            this.animType = 'pop';
            this.animProgress = 0;
        } else {
            this.animType = null;
            this.animProgress = 1;
        }

        this.prevFrameCount = frameCount;
        this.currentSnapshot = snapshot;

        if (this.animType && this.animProgress < 1) {
            this._animate();
        } else {
            this._draw();
        }
    }

    _animate() {
        const startTime = performance.now();
        const animate = (now) => {
            const elapsed = now - startTime;
            this.animProgress = Math.min(1, elapsed / this.animDuration);
            this._draw();
            if (this.animProgress < 1) {
                requestAnimationFrame(animate);
            } else {
                this.animType = null;
            }
        };
        requestAnimationFrame(animate);
    }

    _draw() {
        this.ctx.clearRect(0, 0, this.width, this.height);
        const snapshot = this.currentSnapshot;
        if (!snapshot) {
            this._drawEmpty();
            return;
        }
        try {
            const layout = this._calcLayout();
            this._lastLayout = layout;
            this._drawGlobals(layout.globals, snapshot.globals || []);
            this._drawStack(layout.stack, snapshot.stack_frames || []);
            this._drawHeap(layout.heap, snapshot.heap_objects || []);
            this._drawPointers(layout.pointers, snapshot.pointers || [], layout);
            this._clampScroll(layout);
        } catch (e) {
            this._drawError(snapshot, e);
        }
    }

    _drawEmpty() {
        this.ctx.fillStyle = '#999';
        this.ctx.font = '14px sans-serif';
        this.ctx.textAlign = 'center';
        this.ctx.fillText('请执行调试以查看内存可视化', this.width / 2, this.height / 2);
    }

    _drawError(snapshot, error) {
        this.ctx.fillStyle = '#f44336';
        this.ctx.font = '13px sans-serif';
        this.ctx.textAlign = 'left';
        this.ctx.fillText('可视化渲染异常，已切换为数据视图', 10, 20);
        this.ctx.fillStyle = '#666';
        this.ctx.font = '11px monospace';
        const json = JSON.stringify(snapshot, null, 2);
        const lines = json.split('\n');
        lines.forEach((line, i) => {
            if (i * 14 + 40 < this.height) {
                this.ctx.fillText(line.substring(0, 80), 10, 40 + i * 14);
            }
        });
    }

    _calcLayout() {
        const snap = this.currentSnapshot || {};
        const globals = snap.globals || [];
        const frames = snap.stack_frames || [];
        const heaps = snap.heap_objects || [];

        const globalsContent = globals.length * 18 + 10;
        const globalsH = Math.min(globalsContent + 30, 130);

        let stackContent = 30;
        frames.forEach(frame => {
            const varTree = frame.variable_tree || [];
            if (varTree.length > 0) {
                stackContent += 26 + this._countTreeNodes(varTree) * 18 + 4;
            } else {
                stackContent += 26 + this._localTreeRows(frame.locals || []).length * 18 + 4;
            }
        });
        const heapContent = 30 + heaps.length * 28;

        this.contentHeights = { globals: globalsContent, stack: stackContent, heap: heapContent };

        const remainingH = this.height - globalsH - 20;
        const stackY = 10 + globalsH + 10;

        return {
            globals: { x: 10, y: 10, w: this.width - 20, h: globalsH },
            stack: { x: 10, y: stackY, w: (this.width - 30) / 2, h: remainingH },
            heap: { x: 20 + (this.width - 30) / 2, y: stackY, w: (this.width - 30) / 2, h: remainingH },
            pointers: { x: 10, y: stackY, w: this.width - 20, h: remainingH },
        };
    }

    _drawSectionTitle(area, title, color) {
        this.ctx.fillStyle = color || '#333';
        this.ctx.font = 'bold 13px sans-serif';
        this.ctx.textAlign = 'left';
        this.ctx.fillText(title, area.x + 5, area.y + 15);
        this.ctx.strokeStyle = '#ddd';
        this.ctx.lineWidth = 1;
        this.ctx.strokeRect(area.x, area.y, area.w, area.h);
    }

    _drawGlobals(area, globals) {
        this._drawSectionTitle(area, `全局变量 (${globals.length})`, '#1976d2');
        this.ctx.save();
        this.ctx.beginPath();
        this.ctx.rect(area.x, area.y + 25, area.w, area.h - 25);
        this.ctx.clip();
        this.ctx.font = '12px monospace';
        this.ctx.fillStyle = '#555';
        const startY = area.y + 35;
        const offset = this.scrollOffsets.globals;
        globals.forEach((g, i) => {
            const y = startY + i * 18 - offset;
            if (y > area.y + area.h - 5 || y < area.y + 25) return;
            const text = `${g.name}: ${g.type} = ${g.value} @ ${g.address}`;
            this.ctx.fillText(text.substring(0, 60), area.x + 10, y);
        });
        this.contentHeights.globals = globals.length * 18 + 10;
        this.ctx.restore();
        this._drawScrollbar(area, this.scrollOffsets.globals, this.contentHeights.globals, area.h - 30, 'globals');
    }

    _drawStack(area, frames) {
        const completed = Boolean(this.currentSnapshot && this.currentSnapshot.is_complete);
        const title = frames.length === 0 && completed
            ? '栈区（程序已结束）'
            : `栈区 (${frames.length}帧)`;
        this._drawSectionTitle(area, title, '#388e3c');
        const easing = 1 - Math.pow(1 - this.animProgress, 3);
        const offset = this.scrollOffsets.stack;
        this.ctx.save();
        this.ctx.beginPath();
        this.ctx.rect(area.x, area.y + 25, area.w, area.h - 25);
        this.ctx.clip();
        this._nodeHitAreas = [];
        this._pointerAnchors = [];
        let y = area.y + 30;
        let totalContent = 30;
        if (frames.length === 0) {
            this.ctx.fillStyle = '#7b8794';
            this.ctx.font = '12px sans-serif';
            this.ctx.fillText(
                completed ? '程序已结束，无活动栈帧' : '暂无栈帧数据',
                area.x + 12, y + 16
            );
            totalContent += 24;
        }
        frames.forEach((frame, idx) => {
            const isLast = idx === frames.length - 1;
            let offsetY = 0;
            let alpha = 1;

            if (this.animType === 'push' && isLast) {
                offsetY = -30 * (1 - easing);
                alpha = easing;
            }

            const drawY = y + offsetY - offset;
            if (drawY <= area.y + area.h - 10 && drawY >= area.y + 20) {
                this.ctx.globalAlpha = alpha;
                this.ctx.fillStyle = isLast && this.animType === 'push' ? '#c8e6c9' : '#e8f5e9';
                this.ctx.fillRect(area.x + 5, drawY, area.w - 10, 22);
                this.ctx.strokeStyle = isLast && this.animType === 'push' ? '#4caf50' : '#a5d6a7';
                this.ctx.lineWidth = isLast && this.animType === 'push' ? 2 : 1;
                this.ctx.strokeRect(area.x + 5, drawY, area.w - 10, 22);
                this.ctx.fillStyle = '#2e7d32';
                this.ctx.font = 'bold 12px monospace';
                const label = `${frame.function}(${frame.args || ''})`;
                this.ctx.fillText(label.substring(0, 45), area.x + 10, drawY + 16);
                this.ctx.globalAlpha = 1;
            }
            y += 26;
            totalContent += 26;

            const varTree = frame.variable_tree || [];
            if (varTree.length > 0) {
                const result = this._drawVariableTree(varTree, area, y, offset, 0, '');
                y += result.height;
                totalContent += result.height;
            } else {
                this._localTreeRows(frame.locals || []).forEach((row) => {
                    const lvY = y - offset;
                    if (lvY <= area.y + area.h - 10 && lvY >= area.y + 20) {
                        if (row.kind === 'group') {
                            this.ctx.fillStyle = '#eef4fb';
                            this.ctx.fillRect(area.x + 8, lvY, area.w - 26, 18);
                            this.ctx.fillStyle = '#365b7d';
                            this.ctx.font = 'bold 11px monospace';
                            this.ctx.fillText(`▾ ${row.name}`, area.x + 12, lvY + 13);
                        } else {
                            const value = row.value === 'uninitialized' ? '未初始化' : row.value;
                            this.ctx.fillStyle = row.value === 'uninitialized' ? '#8a94a3' : '#555';
                            this.ctx.font = '11px monospace';
                            const branch = row.last ? '└─' : '├─';
                            const text = `   ${branch} ${row.name}: ${row.type} = ${value}`;
                            this.ctx.fillText(text.substring(0, 50), area.x + 10, lvY + 14);
                        }
                    }
                    y += 18;
                    totalContent += 18;
                });
            }
            y += 4;
            totalContent += 4;
        });
        this.contentHeights.stack = totalContent;
        this.ctx.restore();
        this._drawScrollbar(area, this.scrollOffsets.stack, this.contentHeights.stack, area.h - 30, 'stack');
    }

    _drawVariableTree(nodes, area, startY, offset, depth, parentPath) {
        let y = startY;
        let height = 0;
        const indent = depth * 14;
        nodes.forEach((node) => {
            const path = parentPath ? `${parentPath}.${node.name}` : node.name;
            const hasChildren = node.children && node.children.length > 0;
            const isCollapsed = this._collapsedNodes.has(path);
            const drawY = y - offset;
            if (drawY <= area.y + area.h - 10 && drawY >= area.y + 20) {
                const x = area.x + 10 + indent;
                if (hasChildren) {
                    this._nodeHitAreas.push({
                        x: x, y: drawY, w: area.w - indent - 20, h: 18,
                        path: path, collapsible: true,
                    });
                    this.ctx.fillStyle = '#eef4fb';
                    this.ctx.fillRect(x, drawY, area.w - indent - 20, 18);
                    this.ctx.fillStyle = '#365b7d';
                    this.ctx.font = 'bold 11px monospace';
                    const icon = isCollapsed ? '▸' : '▾';
                    this.ctx.fillText(`${icon} ${node.name}`, x + 4, drawY + 13);
                    if (node.type) {
                        this.ctx.fillStyle = '#888';
                        this.ctx.font = '10px monospace';
                        this.ctx.fillText(node.type, x + 4 + node.name.length * 7 + 16, drawY + 13);
                    }
                    // Expanded aggregates show their children below; drawing the
                    // aggregate value on top of its name/type caused text overlap.
                } else {
                    this.ctx.fillStyle = node.available === false ? '#8a94a3' : '#555';
                    this.ctx.font = '11px monospace';
                    const prefix = depth > 0 ? (depth === 1 ? '├─' : '│  ├─') : '';
                    const value = node.available === false ? (node.unavailable_reason || '不可用') : (node.value || '');
                    const text = `${prefix} ${node.name}: ${node.type || ''} = ${value}`;
                    this.ctx.fillText(text.substring(0, 55), x, drawY + 14);
                    if (node.kind === 'pointer' && node.value) {
                        const address = node.value.match(/0x[0-9a-fA-F]+/)?.[0]?.toLowerCase();
                        if (address) {
                            this._pointerAnchors.push({
                                name: node.name,
                                address,
                                x: area.x + area.w - 7,
                                y: drawY + 9,
                            });
                        }
                    }
                }
            }
            y += 18;
            height += 18;

            if (hasChildren && !isCollapsed) {
                const childResult = this._drawVariableTree(
                    node.children, area, y, offset, depth + 1, path
                );
                y += childResult.height;
                height += childResult.height;
            }
        });
        return { height: height };
    }

    _localTreeRows(locals) {
        const groups = new Map();
        locals.forEach((local) => {
            const dot = local.name.indexOf('.');
            if (dot <= 0) return;
            const root = local.name.slice(0, dot);
            if (!groups.has(root)) groups.set(root, []);
            groups.get(root).push({ ...local, name: local.name.slice(dot + 1) });
        });

        const output = [];
        const emitted = new Set();
        locals.forEach((local) => {
            const dot = local.name.indexOf('.');
            if (dot <= 0) {
                output.push({ kind: 'variable', ...local });
                return;
            }
            const root = local.name.slice(0, dot);
            if (emitted.has(root)) return;
            emitted.add(root);
            const children = groups.get(root) || [];
            output.push({ kind: 'group', name: root });
            children.forEach((child, index) => {
                output.push({ ...child, kind: 'field', last: index === children.length - 1 });
            });
        });
        return output;
    }

    _countTreeNodes(nodes) {
        let count = 0;
        nodes.forEach(node => {
            count++;
            if (node.children && node.children.length > 0) {
                if (!this._collapsedNodes.has(node.name)) {
                    count += this._countTreeNodes(node.children);
                }
            }
        });
        return count;
    }

    _drawHeap(area, heaps) {
        this._drawSectionTitle(area, `堆区 (${heaps.length}对象)`, '#f57c00');
        const offset = this.scrollOffsets.heap;
        this.ctx.save();
        this.ctx.beginPath();
        this.ctx.rect(area.x, area.y + 25, area.w, area.h - 25);
        this.ctx.clip();
        let y = area.y + 30;
        let totalContent = 30;
        this._heapAnchors = [];
        heaps.forEach((h) => {
            const elements = h.elements || [];
            const hasContent = elements.length > 0 || (h.content && h.content.length > 0);
            const rowH = elements.length > 0 ? 24 + elements.length * 18 : (hasContent ? 44 : 24);
            const drawY = y - offset;
            const address = String(h.address || '').match(/0x[0-9a-fA-F]+/)?.[0]?.toLowerCase();
            if (address) {
                this._heapAnchors.push({ address, x: area.x + 6, y: drawY + 12 });
            }
            if (drawY <= area.y + area.h - 10 && drawY >= area.y + 20) {
                const bgColor = h.is_freed ? '#ffebee' : '#fff3e0';
                const borderColor = h.is_freed ? '#f44336' : '#ff9800';
                this.ctx.fillStyle = bgColor;
                this.ctx.fillRect(area.x + 5, drawY, area.w - 10, rowH);
                this.ctx.strokeStyle = borderColor;
                this.ctx.lineWidth = 1;
                this.ctx.strokeRect(area.x + 5, drawY, area.w - 10, rowH);
                this.ctx.fillStyle = borderColor;
                this.ctx.font = '12px monospace';
                const status = h.is_freed ? '[已释放]' : `[${h.size}B]`;
                const text = `${status} @ ${h.address}`;
                this.ctx.fillText(text.substring(0, 45), area.x + 10, drawY + 16);
                if (elements.length > 0) {
                    elements.forEach((element, index) => {
                        this.ctx.fillStyle = '#555';
                        this.ctx.font = '11px monospace';
                        const elementText = `${element.name || `[${index}]`}: ${element.type || h.element_type || ''} = ${element.value || ''}`;
                        this.ctx.fillText(elementText.substring(0, 55), area.x + 14, drawY + 34 + index * 18);
                    });
                } else if (hasContent) {
                    this.ctx.fillStyle = '#555';
                    this.ctx.font = '11px monospace';
                    const contentStr = h.content.join(', ');
                    this.ctx.fillText(`[${contentStr}]`, area.x + 10, drawY + 36);
                }
            }
            y += rowH + 4;
            totalContent += rowH + 4;
        });
        this.contentHeights.heap = totalContent;
        this.ctx.restore();
        this._drawScrollbar(area, this.scrollOffsets.heap, this.contentHeights.heap, area.h - 30, 'heap');
    }

    _drawScrollbar(area, offset, contentH, viewH, zone) {
        if (contentH <= viewH) return;
        const barH = Math.max(20, viewH * viewH / contentH);
        const barY = area.y + 25 + (offset / (contentH - viewH)) * (viewH - barH);
        const isDragging = this._dragState && this._dragState.zone === zone;
        this.ctx.fillStyle = '#eef2f7';
        this.ctx.fillRect(area.x + area.w - 14, area.y + 25, 12, viewH);
        this.ctx.fillStyle = isDragging ? 'rgba(25,118,210,0.8)' : 'rgba(80,100,125,0.42)';
        this.ctx.fillRect(area.x + area.w - 12, barY, 8, barH);
    }

    _clampScroll(layout) {
        for (const zone of ['globals', 'stack', 'heap']) {
            const viewH = layout[zone].h - 30;
            if (this.contentHeights[zone] <= viewH) {
                this.scrollOffsets[zone] = 0;
            } else {
                this.scrollOffsets[zone] = Math.min(this.scrollOffsets[zone], this.contentHeights[zone] - viewH);
            }
        }
    }

    _drawPointers(area, pointers, layout) {
        // Pointer-to-allocation relationships are conveyed by the matching
        // addresses shown in the stack and heap panels; no overlay is drawn.
    }
}
