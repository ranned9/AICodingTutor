class APIClient {
    static async get(url) {
        const resp = await fetch(url);
        return resp.json();
    }

    static async post(url, body) {
        const resp = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        return resp.json();
    }

    static async listCases() {
        return this.get('/api/cases');
    }

    static async getCase(caseId) {
        return this.get(`/api/cases/${caseId}`);
    }

    static async startDebug(code, mode, breakpoints) {
        return this.post('/api/debug/start', { code, mode, breakpoints });
    }

    static async step(sessionId) {
        return this.post(`/api/debug/${sessionId}/step`);
    }

    static async continueExecution(sessionId) {
        return this.post(`/api/debug/${sessionId}/continue`);
    }

    static async stop(sessionId) {
        return this.post(`/api/debug/${sessionId}/stop`);
    }

    static async getSnapshotMeta(sessionId) {
        return this.get(`/api/debug/${sessionId}/snapshots`);
    }

    static async getSnapshot(sessionId, step) {
        return this.get(`/api/debug/${sessionId}/snapshots/${step}`);
    }

    static async askAI(sessionId, step, question) {
        return this.post(`/api/debug/${sessionId}/ask`, { step, question });
    }
}