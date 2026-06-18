document.addEventListener("DOMContentLoaded", () => {
    
    // ==========================================
    // 1. INTERACTIVE SVG SCROLL-LINE DRAWING
    // ==========================================
    const path = document.querySelector("#scroll-path");
    if (path) {
        const pathLength = path.getTotalLength();
        
        // Prepare SVG path dashes
        path.style.strokeDasharray = `${pathLength} ${pathLength}`;
        path.style.strokeDashoffset = pathLength;
        
        // Update line drawing on scroll
        const drawLineOnScroll = () => {
            const scrollPercent = window.scrollY / (document.documentElement.scrollHeight - window.innerHeight);
            const drawLength = pathLength * scrollPercent;
            
            // Draw path proportionally to scroll
            path.style.strokeDashoffset = pathLength - drawLength;
        };
        
        window.addEventListener("scroll", drawLineOnScroll);
        drawLineOnScroll(); // Initial run
    }

    // ==========================================
    // 2. LAZY-LOADING FOR SCREENSHOT VISUALS
    // ==========================================
    const lazyImages = document.querySelectorAll(".lazy-image");
    
    const lazyLoadObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                const wrapper = img.closest(".lazy-load-wrapper");
                
                // Set wrapper loading pulse
                if (wrapper) wrapper.classList.add("loading");
                
                // Load actual image source
                img.src = img.dataset.src;
                img.addEventListener("load", () => {
                    img.classList.add("loaded");
                    if (wrapper) wrapper.classList.remove("loading");
                });
                
                // Stop observing this image once loaded
                observer.unobserve(img);
            }
        });
    }, {
        rootMargin: "0px 0px 50px 0px", // Load slightly before they scroll into view
        threshold: 0.01
    });

    lazyImages.forEach(img => lazyLoadObserver.observe(img));

    // Helper to force reload screenshot
    const reloadScreenshot = () => {
        const img = document.getElementById("screenshot-img");
        const container = document.getElementById("screenshot-wrapper");
        if (img) {
            // Append cache-busting timestamp query parameter
            const newSrc = `/screenshot.png?t=${new Date().getTime()}`;
            
            // Check if file exists by fetching headers
            fetch(newSrc, { method: 'HEAD' })
                .then(res => {
                    if (res.ok) {
                        img.src = newSrc;
                        img.classList.add("loaded");
                        container.classList.add("has-image");
                    }
                })
                .catch(() => {});
        }
    };

    // Try to load initial screenshot on load
    reloadScreenshot();

    // ==========================================
    // 3. CONFIGURATION MANAGING
    // ==========================================
    const apiKeyInput = document.getElementById("api-key");
    const textModelSelect = document.getElementById("text-model");
    const visionModelSelect = document.getElementById("vision-model");
    const saveConfigBtn = document.getElementById("save-config-btn");

    // Fetch config values
    fetch("/api/config")
        .then(res => res.json())
        .then(data => {
            if (data.api_key) apiKeyInput.value = data.api_key;
            if (data.text_model) textModelSelect.value = data.text_model;
            if (data.vision_model) visionModelSelect.value = data.vision_model;
        });

    // Save configurations
    saveConfigBtn.addEventListener("click", () => {
        const payload = {
            text_model: textModelSelect.value,
            vision_model: visionModelSelect.value,
            api_key: apiKeyInput.value
        };
        
        fetch("/api/config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        })
        .then(res => res.json())
        .then(data => {
            if (data.status === "success") {
                alert("Configuration updated successfully!");
            }
        });
    });

    // ==========================================
    // 4. CHAT AND STREAMING LOG RUNNER
    // ==========================================
    const chatInput = document.getElementById("chat-input");
    const sendBtn = document.getElementById("send-btn");
    const chatBox = document.getElementById("chat-box");
    const consoleBox = document.getElementById("console-box");
    const previewWrapper = document.getElementById("preview-wrapper");
    const previewImg = document.getElementById("preview-img");
    const clearPreviewBtn = document.getElementById("clear-preview-btn");
    
    let pastedImageBase64 = null;

    // Handle image pasting (Ctrl+V)
    chatInput.addEventListener("paste", (e) => {
        const items = (e.clipboardData || e.originalEvent.clipboardData).items;
        for (const item of items) {
            if (item.type.indexOf("image") === 0) {
                const blob = item.getAsFile();
                const reader = new FileReader();
                reader.onload = (event) => {
                    pastedImageBase64 = event.target.result;
                    previewImg.src = pastedImageBase64;
                    previewWrapper.style.display = "flex";
                };
                reader.readAsDataURL(blob);
                e.preventDefault(); // Stop pasting image file names
                break;
            }
        }
    });

    // Clear attached image
    clearPreviewBtn.addEventListener("click", () => {
        pastedImageBase64 = null;
        previewImg.src = "";
        previewWrapper.style.display = "none";
    });

    const escapeHtml = (text) => {
        return text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    };

    const appendMessage = (sender, text, imageUrl = null) => {
        const msgDiv = document.createElement("div");
        msgDiv.className = `message ${sender}-msg`;
        let escapedText = escapeHtml(text || "");
        let contentHtml = escapedText.replace(/\n/g, "<br>");
        if (imageUrl) {
            contentHtml = `<div class="chat-attached-image"><img src="${imageUrl}" style="max-width: 150px; border-radius: var(--radius-eight); margin-bottom: 8px; display: block;"></div>` + contentHtml;
        }
        msgDiv.innerHTML = contentHtml;
        chatBox.appendChild(msgDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
    };

    const appendConsole = (text, type = "normal") => {
        const line = document.createElement("div");
        line.className = `console-line ${type}`;
        line.textContent = `[${new Date().toLocaleTimeString()}] ${text}`;
        consoleBox.appendChild(line);
        consoleBox.scrollTop = consoleBox.scrollHeight;
    };

    const runChatRequest = async (prompt) => {
        // Capture image ref locally and clear preview instantly
        const attachedImage = pastedImageBase64;
        pastedImageBase64 = null;
        previewWrapper.style.display = "none";
        
        appendMessage("user", prompt, attachedImage);
        chatInput.value = "";
        
        appendConsole(`User Query: "${prompt}" ${attachedImage ? '[Image Attached]' : ''}`, "normal");
        
        try {
            const response = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    message: prompt,
                    image: attachedImage, // Sends the optional pasted Base64
                    text_model: textModelSelect.value,
                    vision_model: visionModelSelect.value
                })
            });
            
            const reader = response.body.getReader();
            const decoder = new TextDecoder("utf-8");
            let buffer = "";
            
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n");
                
                // Keep the last partial line in buffer
                buffer = lines.pop();
                
                for (const line of lines) {
                    if (!line.trim()) continue;
                    
                    try {
                        const chunk = JSON.parse(line);
                        
                        if (chunk.type === "status") {
                            appendConsole(chunk.content, "normal");
                        } 
                        else if (chunk.type === "tool_start") {
                            appendConsole(`Tool Requested: [${chunk.tool}] with args: ${JSON.stringify(chunk.args)}`, "tool");
                        } 
                        else if (chunk.type === "tool_end") {
                            appendConsole(`Tool Executed: [${chunk.tool}] -> Result: ${chunk.result.slice(0, 100)}...`, "success");
                            
                            // If screenshot is captured, reload screen element
                            if (chunk.tool === "take_screenshot") {
                                setTimeout(reloadScreenshot, 1000); // Wait 1s for file systems to sync
                            }
                        } 
                        else if (chunk.type === "message") {
                            appendMessage("agent", chunk.content);
                        } 
                        else if (chunk.type === "error") {
                            appendConsole(chunk.content, "error");
                            appendMessage("agent", `⚠️ Error: ${chunk.content}`);
                        }
                    } catch (e) {
                        // Ignore parse errors on partial stream lines
                    }
                }
            }
        } catch (err) {
            appendConsole(`Fetch Error: ${err}`, "error");
        }
    };

    sendBtn.addEventListener("click", () => {
        const text = chatInput.value.trim();
        if (text || pastedImageBase64) runChatRequest(text);
    });

    chatInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            const text = chatInput.value.trim();
            if (text || pastedImageBase64) runChatRequest(text);
        }
    });

    // ==========================================
    // 5. QUICK ACTION BUTTONS
    // ==========================================
    const snapBtn = document.getElementById("snap-btn");
    snapBtn.addEventListener("click", () => {
        runChatRequest("Take a screenshot and summarize what is visible on the desktop screen.");
    });
});

