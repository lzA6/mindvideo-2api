// /static/script.js
document.addEventListener('DOMContentLoaded', () => {
    // --- DOM 元素获取 ---
    const apiKeyInput = document.getElementById('api-key');
    const modelSelect = document.getElementById('model-select');
    const ratioSelect = document.getElementById('ratio-select');
    const promptInput = document.getElementById('prompt-input');
    const generateBtn = document.getElementById('generate-btn');
    
    const placeholder = document.getElementById('placeholder');
    const spinner = document.getElementById('spinner');
    const errorMessage = document.getElementById('error-message');
    
    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');

    const videoContainer = document.getElementById('video-container');
    const resultVideo = document.getElementById('result-video');
    const resultUrlInput = document.getElementById('result-url');
    const copyUrlBtn = document.getElementById('copy-url-btn');

    let eventSource = null;

    // --- 核心功能 ---

    async function populateModels() {
        modelSelect.innerHTML = '<option>正在加载...</option>';
        modelSelect.disabled = true;
        generateBtn.disabled = true;

        try {
            const apiKey = apiKeyInput.value.trim();
            if (!apiKey) throw new Error("请输入 API Key");

            const response = await fetch('/v1/models', {
                headers: { 'Authorization': `Bearer ${apiKey}` }
            });
            
            if (!response.ok) {
                const result = await response.json().catch(() => ({ detail: '获取模型列表失败' }));
                throw new Error(result.detail);
            }
            
            const result = await response.json();
            modelSelect.innerHTML = '';
            result.data.forEach(model => {
                const option = document.createElement('option');
                option.value = model.id;
                option.textContent = model.id;
                modelSelect.appendChild(option);
            });
            
            modelSelect.disabled = false;
            generateBtn.disabled = false;

        } catch (error) {
            showState('ERROR', { message: `模型加载失败: ${error.message}` });
            modelSelect.innerHTML = `<option>加载失败</option>`;
        }
    }

    async function handleGenerate() {
        const apiKey = apiKeyInput.value.trim();
        const prompt = promptInput.value.trim();
        const selectedModel = modelSelect.value;
        const selectedSize = ratioSelect.value;

        if (!apiKey || !prompt || !selectedModel) {
            showState('ERROR', { message: "请确保 API Key、模型和提示词都已填写。" });
            return;
        }

        generateBtn.disabled = true;
        showState('SUBMITTING');

        const payload = {
            model: selectedModel,
            prompt: prompt,
            size: selectedSize,
        };

        try {
            const response = await fetch('/v1/images/generations', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${apiKey}`
                },
                body: JSON.stringify(payload)
            });

            const result = await response.json();
            if (!response.ok) {
                throw new Error(result.detail || '提交任务失败，未知错误。');
            }
            
            startStreaming(result.task_id);

        } catch (error) {
            showState('ERROR', { message: error.message });
            generateBtn.disabled = false;
        }
    }

    function startStreaming(taskId) {
        if (eventSource) {
            eventSource.close();
        }
        
        const url = `/v1/tasks/${taskId}/stream`;
        eventSource = new EventSource(url);

        showState('STREAMING', { progress: 0, remark: '任务已提交，等待处理...' });

        eventSource.onmessage = (event) => {
            if (event.data === '[DONE]') {
                eventSource.close();
                generateBtn.disabled = false;
                return;
            }

            try {
                const data = JSON.parse(event.data);
                
                if (data.status === 'processing') {
                    showState('STREAMING', { progress: data.progress, remark: data.remark });
                } else if (data.status === 'completed') {
                    showState('COMPLETE', { url: data.url });
                    eventSource.close();
                    generateBtn.disabled = false;
                } else if (data.status === 'failed') {
                    showState('ERROR', { message: data.error || '任务处理失败' });
                    eventSource.close();
                    generateBtn.disabled = false;
                }
            } catch (e) {
                console.error("无法解析 SSE 数据:", event.data);
            }
        };

        eventSource.onerror = () => {
            showState('ERROR', { message: '与服务器的连接丢失，请重试。' });
            eventSource.close();
            generateBtn.disabled = false;
        };
    }

    // --- UI 状态管理 ---
    
    function showState(state, data = {}) {
        // 统一隐藏所有动态面板
        placeholder.classList.add('hidden');
        spinner.classList.add('hidden');
        progressContainer.classList.add('hidden');
        videoContainer.classList.add('hidden');
        errorMessage.classList.add('hidden');

        switch (state) {
            case 'IDLE':
                placeholder.textContent = '请在左侧配置参数并开始生成';
                placeholder.classList.remove('hidden');
                break;
            case 'SUBMITTING':
                placeholder.textContent = '正在提交任务...';
                spinner.classList.remove('hidden');
                placeholder.classList.remove('hidden');
                break;
            case 'STREAMING':
                progressContainer.classList.remove('hidden');
                progressBar.style.width = `${data.progress || 0}%`;
                progressText.textContent = `${data.remark || '处理中...'} (${data.progress || 0}%)`;
                break;
            case 'COMPLETE':
                videoContainer.classList.remove('hidden');
                resultVideo.src = data.url;
                resultUrlInput.value = data.url;
                break;
            case 'ERROR':
                errorMessage.textContent = `错误: ${data.message}`;
                errorMessage.classList.remove('hidden');
                break;
        }
    }

    // --- 事件监听 ---
    generateBtn.addEventListener('click', handleGenerate);
    apiKeyInput.addEventListener('change', populateModels);
    copyUrlBtn.addEventListener('click', () => {
        resultUrlInput.select();
        document.execCommand('copy');
        copyUrlBtn.textContent = '已复制!';
        setTimeout(() => { copyUrlBtn.textContent = '复制链接'; }, 2000);
    });

    // --- 初始化 ---
    showState('IDLE');
    populateModels();
});
