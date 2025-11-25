/**
 * Family Medical LLM - Frontend Application
 * Handles WebSocket connections, chat interface, and vision features.
 */

class MedicalLLMApp {
    constructor() {
        // State
        this.ws = null;
        this.wsVision = null;
        this.connected = false;
        this.currentFamilyMemberId = null;
        this.currentSessionId = null;
        this.isGenerating = false;
        this.selectedImage = null;
        this.sessions = [];
        this.draggedSession = null;
        this.messageHistory = [];  // Current session messages

        // DOM Elements
        this.elements = {
            messagesContainer: document.getElementById('messagesContainer'),
            messageInput: document.getElementById('messageInput'),
            sendBtn: document.getElementById('sendBtn'),
            statusDot: document.getElementById('statusDot'),
            statusText: document.getElementById('statusText'),
            familyMemberSelect: document.getElementById('familyMemberSelect'),
            currentMemberName: document.getElementById('currentMemberName'),
            newChatBtn: document.getElementById('newChatBtn'),
            sessionsList: document.getElementById('sessionsList'),
            sessionsContainer: document.getElementById('sessionsContainer'),
            sidebar: document.getElementById('sidebar'),
            sidebarToggle: document.getElementById('sidebarToggle'),
            uploadBtn: document.getElementById('uploadBtn'),
            visionModal: document.getElementById('visionModal'),
            closeVisionModal: document.getElementById('closeVisionModal'),
            dropZone: document.getElementById('dropZone'),
            imageInput: document.getElementById('imageInput'),
            imagePreview: document.getElementById('imagePreview'),
            visionPrompt: document.getElementById('visionPrompt'),
            analyzeBtn: document.getElementById('analyzeBtn'),
            takePhotoBtn: document.getElementById('takePhotoBtn'),
            cameraContainer: document.getElementById('cameraContainer'),
            cameraVideo: document.getElementById('cameraVideo'),
            captureBtn: document.getElementById('captureBtn'),
            cancelCameraBtn: document.getElementById('cancelCameraBtn'),
            captureCanvas: document.getElementById('captureCanvas'),
        };

        this.cameraStream = null;

        this.init();
    }

    init() {
        this.bindEvents();
        this.connectWebSocket();
        this.loadFamilyMembers();
        this.restoreSidebarState();
    }

    // ==========================================================================
    // Event Bindings
    // ==========================================================================

    bindEvents() {
        // Send message
        this.elements.sendBtn.addEventListener('click', () => this.sendMessage());
        this.elements.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // Auto-resize textarea
        this.elements.messageInput.addEventListener('input', () => {
            this.elements.messageInput.style.height = 'auto';
            this.elements.messageInput.style.height =
                Math.min(this.elements.messageInput.scrollHeight, 200) + 'px';
        });

        // Family member selection
        this.elements.familyMemberSelect.addEventListener('change', (e) => {
            this.selectFamilyMember(e.target.value);
        });

        // New chat
        this.elements.newChatBtn.addEventListener('click', () => this.startNewChat());

        // Sidebar toggle
        this.elements.sidebarToggle.addEventListener('click', () => this.toggleSidebar());

        // Vision modal
        this.elements.uploadBtn.addEventListener('click', () => this.openVisionModal());
        this.elements.closeVisionModal.addEventListener('click', () => this.closeVisionModal());
        this.elements.visionModal.addEventListener('click', (e) => {
            if (e.target === this.elements.visionModal) this.closeVisionModal();
        });

        // Image upload
        this.elements.dropZone.addEventListener('click', () => {
            this.elements.imageInput.click();
        });
        this.elements.imageInput.addEventListener('change', (e) => {
            if (e.target.files[0]) this.handleImageSelect(e.target.files[0]);
        });

        // Drag and drop
        this.elements.dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            this.elements.dropZone.classList.add('dragover');
        });
        this.elements.dropZone.addEventListener('dragleave', () => {
            this.elements.dropZone.classList.remove('dragover');
        });
        this.elements.dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            this.elements.dropZone.classList.remove('dragover');
            if (e.dataTransfer.files[0]) {
                this.handleImageSelect(e.dataTransfer.files[0]);
            }
        });

        // Analyze image
        this.elements.analyzeBtn.addEventListener('click', () => this.analyzeImage());

        // Camera controls
        this.elements.takePhotoBtn.addEventListener('click', () => this.startCamera());
        this.elements.captureBtn.addEventListener('click', () => this.capturePhoto());
        this.elements.cancelCameraBtn.addEventListener('click', () => this.stopCamera());
    }

    // ==========================================================================
    // WebSocket Management
    // ==========================================================================

    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host || 'localhost:8000';

        // Chat WebSocket
        this.ws = new WebSocket(`${protocol}//${host}/ws/chat`);

        this.ws.onopen = () => {
            this.connected = true;
            this.updateConnectionStatus(true);
            console.log('Chat WebSocket connected');
        };

        this.ws.onclose = () => {
            this.connected = false;
            this.updateConnectionStatus(false);
            console.log('Chat WebSocket disconnected');
            // Attempt reconnection after 3 seconds
            setTimeout(() => this.connectWebSocket(), 3000);
        };

        this.ws.onerror = (error) => {
            console.error('Chat WebSocket error:', error);
        };

        this.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleChatMessage(data);
        };

    }

    connectVisionWebSocket() {
        return new Promise((resolve, reject) => {
            // If already connected, resolve immediately
            if (this.wsVision && this.wsVision.readyState === WebSocket.OPEN) {
                resolve();
                return;
            }

            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const host = window.location.host || 'localhost:8000';

            this.wsVision = new WebSocket(`${protocol}//${host}/ws/vision`);

            this.wsVision.onopen = () => {
                console.log('Vision WebSocket connected');
                resolve();
            };

            this.wsVision.onclose = () => {
                console.log('Vision WebSocket disconnected');
                // Don't auto-reconnect - will reconnect when needed
            };

            this.wsVision.onerror = (error) => {
                console.error('Vision WebSocket error:', error);
                reject(error);
            };

            this.wsVision.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.handleVisionMessage(data);
            };
        });
    }

    updateConnectionStatus(connected) {
        this.elements.statusDot.classList.toggle('connected', connected);
        this.elements.statusText.textContent = connected ? 'Connected' : 'Disconnected';
    }

    // ==========================================================================
    // Chat Functionality
    // ==========================================================================

    async sendMessage() {
        const message = this.elements.messageInput.value.trim();
        if (!message || this.isGenerating || !this.connected) return;

        // Check if family member is selected
        if (!this.currentFamilyMemberId) {
            this.addSystemMessage('Please select a family member from the sidebar first.');
            return;
        }

        // Create session if none exists
        if (!this.currentSessionId) {
            const session = await this.createSession();
            if (!session) {
                this.addSystemMessage('Failed to create chat session. Please try again.');
                return;
            }
        }

        // Add user message to UI
        this.addMessage('user', message);
        this.elements.messageInput.value = '';
        this.elements.messageInput.style.height = 'auto';

        // Save user message to database
        await this.saveMessage('user', message);

        // Track if this is the first real message (for title generation)
        const isFirstMessage = this.messageHistory.filter(m => m.role === 'user').length === 0;
        this.messageHistory.push({ role: 'user', content: message });

        // Build conversation history for context (last 10 exchanges max)
        const recentHistory = this.messageHistory.slice(-20);  // Last 20 messages (10 exchanges)

        // Send to WebSocket with history
        this.ws.send(JSON.stringify({
            type: 'chat',
            message: message,
            family_member_id: this.currentFamilyMemberId,
            session_id: this.currentSessionId,
            history: recentHistory,
        }));

        // Show typing indicator
        this.isGenerating = true;
        this.showTypingIndicator();

        // Generate title after first exchange
        if (isFirstMessage) {
            this._pendingTitleGeneration = true;
        }
    }

    handleChatMessage(data) {
        switch (data.type) {
            case 'token':
                this.updateStreamingMessage(data.full);
                break;
            case 'done':
                this.finalizeStreamingMessage(data.content, data.model);
                this.isGenerating = false;

                // Save assistant message to database
                this.saveMessage('assistant', data.content, data.model);
                this.messageHistory.push({ role: 'assistant', content: data.content });

                // Generate title after first exchange
                if (this._pendingTitleGeneration) {
                    this._pendingTitleGeneration = false;
                    setTimeout(() => this.generateSessionTitle(), 500);
                }

                // Refresh session list to show updated preview
                this.loadSessions();
                break;
            case 'error':
                this.hideTypingIndicator();
                this.addSystemMessage(`Error: ${data.content}`);
                this.isGenerating = false;
                break;
            case 'context':
                // RAG context received - could display sources
                console.log('RAG context:', data.content);
                break;
        }
    }

    addMessage(role, content, meta = null) {
        const messageEl = document.createElement('div');
        messageEl.className = `message ${role}`;

        const avatar = role === 'user' ? '👤' : 'AI';
        const avatarClass = role === 'user' ? '' : '';

        messageEl.innerHTML = `
            <div class="message-avatar">${avatar}</div>
            <div class="message-content">
                <div class="message-bubble">${this.escapeHtml(content)}</div>
                ${meta ? `<div class="message-meta">${meta}</div>` : ''}
            </div>
        `;

        this.elements.messagesContainer.appendChild(messageEl);
        this.scrollToBottom();
    }

    addSystemMessage(content) {
        const messageEl = document.createElement('div');
        messageEl.className = 'message assistant';
        messageEl.innerHTML = `
            <div class="message-avatar">!</div>
            <div class="message-content">
                <div class="message-bubble" style="background: var(--warning); color: #000;">
                    ${this.escapeHtml(content)}
                </div>
            </div>
        `;
        this.elements.messagesContainer.appendChild(messageEl);
        this.scrollToBottom();
    }

    showTypingIndicator() {
        const indicator = document.createElement('div');
        indicator.id = 'typingIndicator';
        indicator.className = 'message assistant';
        indicator.innerHTML = `
            <div class="message-avatar">AI</div>
            <div class="message-content">
                <div class="message-bubble" id="streamingContent">
                    <div class="typing-indicator">
                        <span></span><span></span><span></span>
                    </div>
                </div>
            </div>
        `;
        this.elements.messagesContainer.appendChild(indicator);
        this.scrollToBottom();
    }

    hideTypingIndicator() {
        const indicator = document.getElementById('typingIndicator');
        if (indicator) indicator.remove();
    }

    updateStreamingMessage(content) {
        const streamingEl = document.getElementById('streamingContent');
        if (streamingEl) {
            streamingEl.innerHTML = this.escapeHtml(content);
            this.scrollToBottom();
        }
    }

    finalizeStreamingMessage(content, model) {
        this.hideTypingIndicator();
        this.addMessage('assistant', content, model ? `Model: ${model}` : null);
    }

    async startNewChat() {
        // Clear messages
        this.elements.messagesContainer.innerHTML = '';
        this.currentSessionId = null;
        this.messageHistory = [];

        // Create a new session
        const session = await this.createSession();
        if (session) {
            this.currentSessionId = session.id;
        }

        // Add welcome message
        const welcomeMsg = `Hello! I'm ready to help with health questions for ${
            this.elements.familyMemberSelect.selectedOptions[0]?.text || 'your family'
        }. What would you like to know?`;

        this.addMessage('assistant', welcomeMsg);

        // Update header
        this.elements.currentMemberName.textContent = 'New Chat';

        // Update session list UI
        this.renderSessions();
    }

    // ==========================================================================
    // Vision Functionality
    // ==========================================================================

    openVisionModal() {
        this.elements.visionModal.classList.add('active');
        this.selectedImage = null;
        this.elements.imagePreview.style.display = 'none';
        this.elements.dropZone.style.display = 'block';
        this.elements.takePhotoBtn.style.display = 'block';
        this.elements.cameraContainer.style.display = 'none';
        this.elements.visionPrompt.value = '';
        // Make sure camera is stopped
        this.stopCamera();
    }

    closeVisionModal() {
        this.elements.visionModal.classList.remove('active');
        // Stop camera if it's running
        this.stopCamera();
    }

    handleImageSelect(file) {
        if (!file.type.startsWith('image/')) {
            alert('Please select an image file');
            return;
        }

        const reader = new FileReader();
        reader.onload = (e) => {
            this.selectedImage = e.target.result.split(',')[1]; // Base64 without prefix
            this.elements.imagePreview.src = e.target.result;
            this.elements.imagePreview.style.display = 'block';
            this.elements.dropZone.style.display = 'none';
        };
        reader.readAsDataURL(file);
    }

    async analyzeImage() {
        if (!this.selectedImage) {
            alert('Please select an image first');
            return;
        }

        const prompt = this.elements.visionPrompt.value.trim() ||
            'Analyze this medical image. If it\'s a prescription, extract medication names and dosages. If it\'s a lab result, identify any values outside normal ranges.';

        // Close modal
        this.closeVisionModal();

        // Add user message with image indicator
        this.addMessage('user', `[Image uploaded] ${prompt}`);

        // Show typing indicator
        this.isGenerating = true;
        this.showTypingIndicator();

        try {
            // Connect vision WebSocket if not already connected
            await this.connectVisionWebSocket();

            // Send to vision WebSocket
            this.wsVision.send(JSON.stringify({
                type: 'vision',
                image_b64: this.selectedImage,
                prompt: prompt,
                family_member_id: this.currentFamilyMemberId,
            }));
        } catch (error) {
            console.error('Failed to connect vision WebSocket:', error);
            this.hideTypingIndicator();
            this.isGenerating = false;
            this.addMessage('assistant', 'Sorry, I could not connect to the vision service. Please try again.');
        }
    }

    handleVisionMessage(data) {
        // Same handling as chat
        this.handleChatMessage(data);
    }

    async startCamera() {
        try {
            // Request camera access
            this.cameraStream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode: 'environment' } // Prefer back camera on mobile
            });

            // Show camera container and hide upload zone
            this.elements.cameraContainer.style.display = 'block';
            this.elements.dropZone.style.display = 'none';
            this.elements.takePhotoBtn.style.display = 'none';
            this.elements.imagePreview.style.display = 'none';

            // Set video stream
            this.elements.cameraVideo.srcObject = this.cameraStream;
        } catch (error) {
            console.error('Failed to access camera:', error);
            alert('Could not access camera. Please make sure you have granted camera permissions.');
        }
    }

    stopCamera() {
        // Stop all video tracks
        if (this.cameraStream) {
            this.cameraStream.getTracks().forEach(track => track.stop());
            this.cameraStream = null;
        }

        // Reset UI
        this.elements.cameraContainer.style.display = 'none';
        this.elements.dropZone.style.display = 'block';
        this.elements.takePhotoBtn.style.display = 'block';
        this.elements.cameraVideo.srcObject = null;
    }

    capturePhoto() {
        const video = this.elements.cameraVideo;
        const canvas = this.elements.captureCanvas;
        const context = canvas.getContext('2d');

        // Set canvas dimensions to match video
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;

        // Draw video frame to canvas
        context.drawImage(video, 0, 0, canvas.width, canvas.height);

        // Convert to base64
        const imageDataUrl = canvas.toDataURL('image/jpeg', 0.9);
        this.selectedImage = imageDataUrl.split(',')[1]; // Base64 without prefix

        // Show preview
        this.elements.imagePreview.src = imageDataUrl;
        this.elements.imagePreview.style.display = 'block';

        // Stop camera and hide camera UI
        this.stopCamera();
    }

    // ==========================================================================
    // Family Member Management
    // ==========================================================================

    async loadFamilyMembers() {
        try {
            const response = await fetch('/api/family/members');
            const members = await response.json();

            this.elements.familyMemberSelect.innerHTML = '';

            // Filter out Demo User to get only real family members
            const realMembers = members.filter(m => m.id !== 'demo');

            // Add real family members FIRST
            realMembers.forEach((member) => {
                const option = document.createElement('option');
                option.value = member.id;
                option.textContent = `${member.name} (${member.role})`;
                this.elements.familyMemberSelect.appendChild(option);
            });

            // Add Demo User at the END
            const demoOption = document.createElement('option');
            demoOption.value = 'demo';
            demoOption.textContent = 'Demo User (demo)';
            this.elements.familyMemberSelect.appendChild(demoOption);

            // Auto-select priority: 1) Primary member from settings (if real user), 2) First real user (self role), 3) First non-demo member
            let selectedMemberId = 'demo'; // Fallback to Demo User
            let shouldSaveSettings = false;

            // Check settings for primary member
            const settings = JSON.parse(localStorage.getItem('myaViewSettings') || '{}');
            const savedPrimary = settings.primary_member_id;

            // If saved primary is demo or empty, or if it's a real user that exists, use it
            if (savedPrimary && savedPrimary !== 'demo' && savedPrimary !== '') {
                // Verify the primary member still exists
                const primaryExists = realMembers.find(m => m.id === savedPrimary);
                if (primaryExists) {
                    selectedMemberId = savedPrimary;
                } else if (realMembers.length > 0) {
                    // Primary member was deleted, default to first real user
                    const selfMember = realMembers.find(m => m.role === 'self');
                    const defaultMember = selfMember || realMembers[0];
                    selectedMemberId = defaultMember.id;
                    shouldSaveSettings = true;
                }
            } else if (realMembers.length > 0) {
                // No primary set OR primary is demo - default to first real user with "self" role, or first real member
                const selfMember = realMembers.find(m => m.role === 'self');
                const defaultMember = selfMember || realMembers[0];
                selectedMemberId = defaultMember.id;
                shouldSaveSettings = true;
            }

            // Save the default selection to localStorage if this is first time or primary was deleted or was demo
            if (shouldSaveSettings) {
                settings.primary_member_id = selectedMemberId;
                localStorage.setItem('myaViewSettings', JSON.stringify(settings));
                console.log('Saved primary member to localStorage:', selectedMemberId);
            }

            this.elements.familyMemberSelect.value = selectedMemberId;
            this.selectFamilyMember(selectedMemberId);
        } catch (error) {
            console.error('Failed to load family members:', error);
            // Add demo option on error
            const demoOption = document.createElement('option');
            demoOption.value = 'demo';
            demoOption.textContent = 'Demo User (demo)';
            this.elements.familyMemberSelect.appendChild(demoOption);
            this.elements.familyMemberSelect.value = 'demo';
            this.selectFamilyMember('demo');
        }
    }

    selectFamilyMember(memberId) {
        this.currentFamilyMemberId = memberId;
        const selectedOption = this.elements.familyMemberSelect.selectedOptions[0];
        this.elements.currentMemberName.textContent = selectedOption?.text || 'Select a family member';

        // Load sessions for this member
        if (memberId) {
            this.loadSessions();
        }
    }

    // ==========================================================================
    // Session Management
    // ==========================================================================

    async loadSessions() {
        try {
            const url = this.currentFamilyMemberId && this.currentFamilyMemberId !== 'demo'
                ? `/api/chat/sessions?family_member_id=${this.currentFamilyMemberId}`
                : '/api/chat/sessions';
            const response = await fetch(url);
            this.sessions = await response.json();
            this.renderSessions();

            // If no current session, start a new chat
            if (!this.currentSessionId && this.sessions.length === 0) {
                this.startNewChat();
            } else if (this.sessions.length > 0 && !this.currentSessionId) {
                // Load the most recent session
                this.loadSession(this.sessions[0].id);
            }
        } catch (error) {
            console.error('Failed to load sessions:', error);
            this.sessions = [];
            this.renderSessions();
        }
    }

    renderSessions() {
        if (!this.elements.sessionsContainer) return;

        this.elements.sessionsContainer.innerHTML = '';

        this.sessions.forEach((session) => {
            const item = document.createElement('div');
            item.className = `session-item${session.id === this.currentSessionId ? ' active' : ''}${session.is_pinned ? ' pinned' : ''}`;
            item.dataset.sessionId = session.id;
            item.draggable = true;

            const timeAgo = this.formatTimeAgo(new Date(session.updated_at));

            item.innerHTML = `
                <div class="session-title">${this.escapeHtml(session.title || 'New Chat')}</div>
                <div class="session-preview">${this.escapeHtml(session.last_message || '')}</div>
                <div class="session-meta">
                    <span>${timeAgo}</span>
                    <div class="session-actions">
                        <button class="session-action-btn" data-action="edit" title="Edit title">✏️</button>
                        <button class="session-action-btn" data-action="pin" title="${session.is_pinned ? 'Unpin' : 'Pin'}">📌</button>
                        <button class="session-action-btn" data-action="delete" title="Delete">🗑️</button>
                    </div>
                </div>
            `;

            // Click to load session
            item.addEventListener('click', (e) => {
                if (!e.target.closest('.session-action-btn')) {
                    this.loadSession(session.id);
                }
            });

            // Action buttons
            item.querySelectorAll('.session-action-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const action = btn.dataset.action;
                    if (action === 'edit') this.editSessionTitle(session.id);
                    if (action === 'pin') this.togglePinSession(session.id);
                    if (action === 'delete') this.deleteSession(session.id);
                });
            });

            // Drag events
            item.addEventListener('dragstart', (e) => {
                this.draggedSession = session.id;
                item.classList.add('dragging');
            });

            item.addEventListener('dragend', () => {
                item.classList.remove('dragging');
                this.draggedSession = null;
            });

            item.addEventListener('dragover', (e) => {
                e.preventDefault();
                if (this.draggedSession && this.draggedSession !== session.id) {
                    item.classList.add('drag-over');
                }
            });

            item.addEventListener('dragleave', () => {
                item.classList.remove('drag-over');
            });

            item.addEventListener('drop', (e) => {
                e.preventDefault();
                item.classList.remove('drag-over');
                if (this.draggedSession && this.draggedSession !== session.id) {
                    this.reorderSessions(this.draggedSession, session.id);
                }
            });

            this.elements.sessionsContainer.appendChild(item);
        });
    }

    async loadSession(sessionId) {
        this.currentSessionId = sessionId;

        // Update active state in UI
        document.querySelectorAll('.session-item').forEach(item => {
            item.classList.toggle('active', item.dataset.sessionId === sessionId);
        });

        // Load messages
        try {
            const response = await fetch(`/api/chat/sessions/${sessionId}/messages`);
            const messages = await response.json();

            // Clear and render messages
            this.elements.messagesContainer.innerHTML = '';
            messages.forEach(msg => {
                this.addMessage(msg.role, msg.content, msg.model_used ? `Model: ${msg.model_used}` : null);
            });

            this.messageHistory = messages;

            // Update header with session title
            const session = this.sessions.find(s => s.id === sessionId);
            if (session) {
                this.elements.currentMemberName.textContent = session.title || 'New Chat';
            }
        } catch (error) {
            console.error('Failed to load session messages:', error);
        }
    }

    async createSession() {
        try {
            const response = await fetch('/api/chat/sessions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    family_member_id: this.currentFamilyMemberId,
                    title: 'New Chat'
                })
            });
            const session = await response.json();
            this.currentSessionId = session.id;
            await this.loadSessions();
            return session;
        } catch (error) {
            console.error('Failed to create session:', error);
            return null;
        }
    }

    async editSessionTitle(sessionId) {
        const item = document.querySelector(`[data-session-id="${sessionId}"]`);
        const titleEl = item.querySelector('.session-title');
        const currentTitle = titleEl.textContent;

        // Replace with input
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'session-title-input';
        input.value = currentTitle;
        titleEl.replaceWith(input);
        input.focus();
        input.select();

        const save = async () => {
            const newTitle = input.value.trim() || 'New Chat';
            try {
                await fetch(`/api/chat/sessions/${sessionId}`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ title: newTitle })
                });
                await this.loadSessions();
            } catch (error) {
                console.error('Failed to update session title:', error);
            }
        };

        input.addEventListener('blur', save);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') save();
            if (e.key === 'Escape') this.loadSessions();
        });
    }

    async togglePinSession(sessionId) {
        const session = this.sessions.find(s => s.id === sessionId);
        if (!session) return;

        try {
            await fetch(`/api/chat/sessions/${sessionId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_pinned: !session.is_pinned })
            });
            await this.loadSessions();
        } catch (error) {
            console.error('Failed to toggle pin:', error);
        }
    }

    async deleteSession(sessionId) {
        if (!confirm('Delete this conversation?')) return;

        try {
            await fetch(`/api/chat/sessions/${sessionId}`, {
                method: 'DELETE'
            });

            // If deleting current session, start new chat
            if (sessionId === this.currentSessionId) {
                this.currentSessionId = null;
            }
            await this.loadSessions();

            if (!this.currentSessionId) {
                this.startNewChat();
            }
        } catch (error) {
            console.error('Failed to delete session:', error);
        }
    }

    async reorderSessions(draggedId, targetId) {
        const draggedIndex = this.sessions.findIndex(s => s.id === draggedId);
        const targetIndex = this.sessions.findIndex(s => s.id === targetId);

        if (draggedIndex === -1 || targetIndex === -1) return;

        // Reorder locally
        const [dragged] = this.sessions.splice(draggedIndex, 1);
        this.sessions.splice(targetIndex, 0, dragged);

        // Update UI immediately
        this.renderSessions();

        // Save to backend
        try {
            await fetch('/api/chat/sessions/reorder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_ids: this.sessions.map(s => s.id) })
            });
        } catch (error) {
            console.error('Failed to reorder sessions:', error);
            await this.loadSessions();  // Reload on error
        }
    }

    async saveMessage(role, content, modelUsed = null) {
        if (!this.currentSessionId) return;

        try {
            await fetch(`/api/chat/sessions/${this.currentSessionId}/messages`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ role, content, model_used: modelUsed })
            });
        } catch (error) {
            console.error('Failed to save message:', error);
        }
    }

    async generateSessionTitle() {
        if (!this.currentSessionId) return;

        try {
            const response = await fetch(`/api/chat/sessions/${this.currentSessionId}/generate-title`, {
                method: 'POST'
            });
            const data = await response.json();
            await this.loadSessions();
        } catch (error) {
            console.error('Failed to generate title:', error);
        }
    }

    formatTimeAgo(date) {
        const now = new Date();
        const diff = now - date;
        const minutes = Math.floor(diff / 60000);
        const hours = Math.floor(diff / 3600000);
        const days = Math.floor(diff / 86400000);

        if (minutes < 1) return 'just now';
        if (minutes < 60) return `${minutes}m ago`;
        if (hours < 24) return `${hours}h ago`;
        if (days < 7) return `${days}d ago`;
        return date.toLocaleDateString();
    }

    // ==========================================================================
    // Sidebar
    // ==========================================================================

    toggleSidebar() {
        const isCollapsed = this.elements.sidebar.classList.toggle('collapsed');
        document.body.classList.toggle('sidebar-collapsed', isCollapsed);
        localStorage.setItem('sidebarCollapsed', isCollapsed);
    }

    restoreSidebarState() {
        const isCollapsed = localStorage.getItem('sidebarCollapsed') === 'true';
        if (isCollapsed) {
            this.elements.sidebar.classList.add('collapsed');
            document.body.classList.add('sidebar-collapsed');
        }
    }

    // ==========================================================================
    // Utilities
    // ==========================================================================

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    scrollToBottom() {
        this.elements.messagesContainer.scrollTop =
            this.elements.messagesContainer.scrollHeight;
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.app = new MedicalLLMApp();
});
