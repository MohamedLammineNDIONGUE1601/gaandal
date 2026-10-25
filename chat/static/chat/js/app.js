(() => {
  const $ = (id) => document.getElementById(id);
  const els = {
    list: $("convList"), messages: $("messages"), welcome: $("welcome"), input: $("input"),
    form: $("composer"), send: $("sendBtn"), title: $("chatTitle"), sidebar: $("sidebar"),
    fileInput: $("fileInput"), attach: $("attachBtn"), mic: $("micBtn"),
    attachmentList: $("attachmentList"), activeFlag: $("activeFlag"),
  };
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const state = { convId: null, streaming: false, controller: null, files: [], recorder: null, dialect: null };

  // ---------- Dialectes ----------
  const DIALECTS = {
    pular_gn: { countries: [["gn", "Guinée"]], label: "Pular (Guinée / Fouta-Djalon)" },
    pulaar_sn: {
      countries: [["sn", "Sénégal"], ["mr", "Mauritanie"], ["gm", "Gambie"]],
      label: "Pulaar (Sénégal, Mauritanie, Gambie)",
    },
    fulfulde_ml: { countries: [["ml", "Mali"]], label: "Maasina (Mali)" },
    fulfulde_east: {
      countries: [["ng", "Nigeria"], ["cm", "Cameroun"], ["td", "Tchad"]],
      label: "Fulfulde de l’Est (Nigeria, Cameroun, Tchad)",
    },
  };

  function renderFlags(container, countries) {
    container.replaceChildren();
    countries.forEach(([code, country]) => {
      const flag = document.createElement("img");
      flag.className = "country-flag-img";
      flag.src = `${els.messages.dataset.flagBase}${code}.svg`;
      flag.width = 18;
      flag.height = 12;
      flag.alt = "";
      flag.title = country;
      flag.setAttribute("aria-hidden", "true");
      container.appendChild(flag);
    });
  }

  function setComposerEnabled(enabled) {
    [els.input, els.send, els.attach, els.fileInput, els.mic].forEach((control) => {
      control.disabled = !enabled;
    });
    els.input.placeholder = enabled
      ? "Posez votre question à Gaandal…"
      : "Choisissez d’abord un dialecte ci-dessus pour écrire…";
  }

  function selectDialect(dialect) {
    const selected = DIALECTS[dialect];
    if (!selected) return;
    state.dialect = dialect;
    document.querySelectorAll(".dialect-btn").forEach((btn) => {
      const isSelected = btn.dataset.dialect === dialect;
      btn.classList.toggle("selected", isSelected);
      btn.setAttribute("aria-pressed", String(isSelected));
    });
    renderFlags(els.activeFlag, selected.countries);
    els.activeFlag.setAttribute(
      "aria-label",
      `Dialecte choisi : ${selected.label}. Pays : ${selected.countries.map(([, country]) => country).join(", ")}`,
    );
    els.welcome.querySelector("p").textContent =
      `Variante choisie : ${selected.label}. Vous pouvez commencer la discussion.`;
    els.welcome.querySelector(".suggestions").style.display = "flex";
    setComposerEnabled(true);
  }

  function clearDialectSelection() {
    state.dialect = null;
    document.querySelectorAll(".dialect-btn").forEach((btn) => {
      btn.classList.remove("selected");
      btn.setAttribute("aria-pressed", "false");
    });
    els.activeFlag.replaceChildren();
    els.activeFlag.removeAttribute("aria-label");
    els.welcome.querySelector("p").textContent =
      "Avant de commencer, quelle variante dialectale souhaitez-vous utiliser ?";
    els.welcome.querySelector(".suggestions").style.display = "none";
    setComposerEnabled(false);
  }

  document.querySelectorAll(".dialect-btn").forEach((btn) => {
    btn.onclick = () => {
      selectDialect(btn.dataset.dialect);
      els.input.focus();
    };
  });
  clearDialectSelection();

  // ---------- Thème ----------
  const savedTheme = localStorage.getItem("intellecto-theme");
  if (savedTheme) document.documentElement.dataset.theme = savedTheme;
  $("themeToggle").onclick = () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("intellecto-theme", next);
  };
  $("menuBtn").onclick = () => els.sidebar.classList.toggle("open");

  // ---------- API ----------
  async function api(url, opts = {}) {
    const res = await fetch(url, {
      ...opts,
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf, ...(opts.headers || {}) },
    });
    if (!res.ok) {
      let msg = "Erreur réseau";
      try { msg = (await res.json()).error || msg; } catch (_) {}
      throw new Error(msg);
    }
    return res.json();
  }

  // ---------- Rendu Markdown ----------
  marked.setOptions({ breaks: true, gfm: true });
  const markdownRenderer = new marked.Renderer();
  const defaultCodeRenderer = markdownRenderer.code.bind(markdownRenderer);
  markdownRenderer.code = (code, info, escaped) => {
    const language = info?.trim().split(/\s+/, 1)[0].toLowerCase();
    if (language === "svg") {
      const svg = DOMPurify.sanitize(code, {
        USE_PROFILES: { html: true, svg: true, svgFilters: true },
      });
      return `<div class="chart-svg" role="img" aria-label="Illustration">${svg}</div>`;
    }
    return defaultCodeRenderer(code, info, escaped);
  };

  function renderMarkdown(el, text, { typesetMath = true } = {}) {
    let placeholderPrefix = "MATHJAXPROTECTEDFRAGMENT";
    while (text.includes(placeholderPrefix)) placeholderPrefix += "X";
    const mathFragments = [];
    const markdownText = text.replace(
      /(\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|\$[^$\n]+\$)/g,
      (math) => {
        const placeholder = `${placeholderPrefix}${mathFragments.length}TOKEN`;
        mathFragments.push([placeholder, math]);
        return placeholder;
      },
    );
    el.innerHTML = DOMPurify.sanitize(marked.parse(markdownText, { renderer: markdownRenderer }), {
      USE_PROFILES: { html: true, svg: true, svgFilters: true },
    });
    if (mathFragments.length) {
      const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      const textNodes = [];
      while (walker.nextNode()) textNodes.push(walker.currentNode);
      for (const node of textNodes) {
        const fragment = document.createDocumentFragment();
        const pattern = new RegExp(`${placeholderPrefix}(\\d+)TOKEN`, "g");
        let lastIndex = 0;
        let match;
        let replaced = false;
        while ((match = pattern.exec(node.textContent)) !== null) {
          replaced = true;
          fragment.append(document.createTextNode(node.textContent.slice(lastIndex, match.index)));
          fragment.append(
            document.createTextNode(mathFragments[Number(match[1])][1]),
          );
          lastIndex = pattern.lastIndex;
        }
        if (replaced) {
          fragment.append(document.createTextNode(node.textContent.slice(lastIndex)));
          node.parentNode.replaceChild(fragment, node);
        }
      }
    }
    el.querySelectorAll("a").forEach((a) => { a.target = "_blank"; a.rel = "noopener noreferrer"; });
    el.querySelectorAll("pre").forEach((pre) => {
      if (pre.querySelector(".copy-btn")) return;
      const btn = document.createElement("button");
      btn.className = "copy-btn";
      btn.type = "button";
      btn.textContent = "Copier";
      btn.onclick = async () => {
        await navigator.clipboard.writeText(pre.querySelector("code")?.innerText || pre.innerText);
        btn.textContent = "Copié ✓";
        setTimeout(() => (btn.textContent = "Copier"), 1500);
      };
      pre.appendChild(btn);
    });
    if (typesetMath) {
      const typeset = () => {
        const mathJax = window.MathJax;
        if (!mathJax?.startup?.promise) return;
        mathJax.startup.promise
          .then(() => mathJax.typesetPromise([el]))
          .catch((error) => {
            console.error("Le rendu des formules mathématiques a échoué.", error);
          });
      };
      const mathJaxScript = document.querySelector('script[src*="tex-chtml.js"]');
      if (window.MathJax?.startup?.promise) {
        typeset();
      } else if (mathJaxScript) {
        mathJaxScript.addEventListener("load", typeset, { once: true });
      }
    }
  }

  function scrollDown(force = false) {
    const m = els.messages;
    const near = m.scrollHeight - m.scrollTop - m.clientHeight < 160;
    if (force || near) m.scrollTop = m.scrollHeight;
  }

  function addMessage(role, text = "", { error = false, attachments = [] } = {}) {
    els.welcome.style.display = "none";
    const wrap = document.createElement("div");
    wrap.className = `msg ${role}${error ? " error" : ""}`;
    const avatar = document.createElement("div");
    avatar.className = "avatar";
    avatar.textContent = role === "user" ? "Vous" : "✦";
    if (role === "user") avatar.textContent = "V";
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    if (role === "assistant") {
      bubble.classList.add("md");
      if (text) renderMarkdown(bubble, text);
    } else {
      bubble.textContent = text;
    }
    if (attachments.length) {
      const fileList = document.createElement("div");
      fileList.className = "msg-attachments";
      for (const file of attachments) {
        const chip = document.createElement("span");
        chip.className = "attachment-chip";
        chip.textContent = `${file.kind === "audio" ? "🎙" : file.kind === "image" ? "▧" : "📎"} ${file.name}`;
        fileList.appendChild(chip);
      }
      bubble.appendChild(fileList);
    }
    wrap.append(avatar, bubble);
    els.messages.appendChild(wrap);
    scrollDown(true);
    return bubble;
  }

  function resetView() {
    els.messages.querySelectorAll(".msg").forEach((n) => n.remove());
    els.welcome.style.display = "";
    els.title.textContent = "Gaandal";
  }

  // ---------- Conversations ----------
  async function loadList() {
    const { conversations } = await api("/api/conversations/");
    els.list.innerHTML = "";
    conversations.forEach((c) => {
      const item = document.createElement("div");
      item.className = "conv-item" + (c.id === state.convId ? " active" : "");
      item.dataset.id = c.id;
      const t = document.createElement("span");
      t.className = "t";
      t.textContent = c.title;
      const del = document.createElement("button");
      del.className = "del";
      del.title = "Supprimer";
      del.textContent = "✕";
      del.onclick = async (e) => {
        e.stopPropagation();
        if (!confirm("Supprimer cette conversation ?")) return;
        await api(`/api/conversations/${c.id}/`, { method: "DELETE" });
        if (state.convId === c.id) {
          state.convId = null;
          resetView();
          clearDialectSelection();
        }
        loadList();
      };
      item.append(t, del);
      item.onclick = () => openConversation(c.id);
      els.list.appendChild(item);
    });
  }

  async function openConversation(id) {
    if (state.streaming) return;
    const data = await api(`/api/conversations/${id}/`);
    state.convId = id;
    selectDialect(data.dialect || "pulaar_sn");
    resetView();
    els.title.textContent = data.title;
    data.messages.forEach((m) => addMessage(m.role, m.content, { attachments: m.attachments || [] }));
    els.sidebar.classList.remove("open");
    loadList();
  }

  $("newChat").onclick = () => {
    if (state.streaming) return;
    state.convId = null;
    resetView();
    clearDialectSelection();
    els.sidebar.classList.remove("open");
    loadList();
  };

  // ---------- Envoi / streaming ----------
  function setStreaming(on) {
    state.streaming = on;
    els.send.classList.toggle("stop", on);
    els.send.textContent = on ? "■" : "➤";
    els.send.setAttribute("aria-label", on ? "Arrêter" : "Envoyer");
  }

  function renderPendingAttachments() {
    els.attachmentList.replaceChildren();
    state.files.forEach((file, index) => {
      const chip = document.createElement("div");
      chip.className = "attachment-chip";
      const label = document.createElement("span");
      label.textContent = `${file.type.startsWith("audio/") ? "🎙" : file.type.startsWith("image/") ? "▧" : "📎"} ${file.name}`;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.setAttribute("aria-label", `Retirer ${file.name}`);
      remove.textContent = "×";
      remove.onclick = () => {
        state.files.splice(index, 1);
        renderPendingAttachments();
      };
      chip.append(label, remove);
      els.attachmentList.appendChild(chip);
    });
  }

  function addFiles(files) {
    const next = [...state.files, ...files];
    const totalSize = next.reduce((sum, file) => sum + file.size, 0);
    if (next.length > 5) {
      alert("Vous pouvez joindre au maximum 5 fichiers.");
      return;
    }
    if (next.some((file) => file.size > 15 * 1024 * 1024) || totalSize > 25 * 1024 * 1024) {
      alert("Chaque fichier doit faire 15 Mo maximum et l’ensemble 25 Mo maximum.");
      return;
    }
    state.files = next;
    renderPendingAttachments();
  }

  async function toggleVoiceRecording() {
    if (state.recorder) {
      state.recorder.stop();
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      alert("L’enregistrement audio n’est pas pris en charge par ce navigateur.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const options = {};
      if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) options.mimeType = "audio/webm;codecs=opus";
      else if (MediaRecorder.isTypeSupported("audio/mp4")) options.mimeType = "audio/mp4";
      const recorder = new MediaRecorder(stream, options);
      const chunks = [];
      state.recorder = recorder;
      els.mic.classList.add("recording");
      els.mic.textContent = "■";
      recorder.addEventListener("dataavailable", (event) => {
        if (event.data.size) chunks.push(event.data);
      });
      recorder.addEventListener("stop", () => {
        const type = recorder.mimeType || "audio/webm";
        const extension = type.includes("mp4") ? "m4a" : type.includes("ogg") ? "ogg" : "webm";
        const recording = new File(chunks, `message-vocal.${extension}`, { type });
        stream.getTracks().forEach((track) => track.stop());
        state.recorder = null;
        els.mic.classList.remove("recording");
        els.mic.textContent = "🎙";
        if (recording.size) addFiles([recording]);
      }, { once: true });
      recorder.start();
    } catch (error) {
      alert(`Impossible d’accéder au microphone : ${error.message}`);
    }
  }

  async function sendMessage(text, files = state.files) {
    text = text.trim();
    if ((!text && !files.length) || state.streaming) return;
    if (!state.dialect) return;

    if (!state.convId) {
      const conv = await api("/api/conversations/", { method: "POST", body: JSON.stringify({ dialect: state.dialect }) });
      state.convId = conv.id;
    }
    const attachments = files.map((file) => ({
      name: file.name,
      kind: file.type.startsWith("audio/") ? "audio" : file.type.startsWith("image/") ? "image" : "file",
    }));
    addMessage("user", text, { attachments });
    els.input.value = "";
    state.files = [];
    els.fileInput.value = "";
    renderPendingAttachments();
    autosize();

    const bubble = addMessage("assistant");
    bubble.innerHTML = '<div class="typing"><span></span><span></span><span></span></div>';
    setStreaming(true);
    state.controller = new AbortController();

    let full = "";
    try {
      const formData = new FormData();
      formData.append("message", text);
      files.forEach((file) => formData.append("files", file, file.name));
      const res = await fetch(`/api/conversations/${state.convId}/chat/`, {
        method: "POST",
        headers: { "X-CSRFToken": csrf },
        body: formData,
        signal: state.controller.signal,
      });
      if (!res.ok) {
        let msg = "Erreur du serveur";
        try { msg = (await res.json()).error || msg; } catch (_) {}
        throw new Error(msg);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let raf = false;
      const paint = () => {
        raf = false;
        if (!state.streaming) return;
        renderMarkdown(bubble, full, { typesetMath: false });
        bubble.classList.add("cursor");
        scrollDown();
      };
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();
        for (const line of lines) {
          if (!line.trim()) continue;
          const evt = JSON.parse(line);
          if (evt.type === "delta") {
            full += evt.text;
            if (!raf) { raf = true; requestAnimationFrame(paint); }
          } else if (evt.type === "error") {
            throw new Error(evt.text);
          } else if (evt.type === "done") {
            els.title.textContent = evt.title;
          }
        }
      }
    } catch (err) {
      if (err.name === "AbortError") {
        if (!full) bubble.textContent = "Génération interrompue.";
      } else {
        const wrap = bubble.closest(".msg");
        wrap.classList.add("error");
        if (full) {
          wrap.querySelector(".bubble").insertAdjacentHTML("beforeend", `<p>⚠ ${DOMPurify.sanitize(err.message)}</p>`);
        } else {
          bubble.textContent = "⚠ " + err.message;
        }
      }
    } finally {
      bubble.classList.remove("cursor");
      if (full) renderMarkdown(bubble, full);
      setStreaming(false);
      state.controller = null;
      loadList();
      els.input.focus();
    }
  }

  // ---------- Composer ----------
  function autosize() {
    els.input.style.height = "auto";
    els.input.style.height = Math.min(els.input.scrollHeight, 200) + "px";
  }
  els.input.addEventListener("input", autosize);
  els.attach.onclick = () => els.fileInput.click();
  els.fileInput.addEventListener("change", () => {
    addFiles([...els.fileInput.files]);
    els.fileInput.value = "";
  });
  els.mic.onclick = toggleVoiceRecording;
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) els.mic.hidden = true;
  els.input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      els.form.requestSubmit();
    }
  });
  els.form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (state.streaming) { state.controller?.abort(); return; }
    sendMessage(els.input.value);
  });
  document.querySelectorAll(".chip").forEach((c) => (c.onclick = () => sendMessage(c.dataset.prompt)));

  loadList();
})();
