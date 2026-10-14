/* CompanionDeck 前端逻辑：状态拉取、WebSocket 实时推送、动作触发。 */
(function () {
  "use strict";

  var TOKEN_KEY = "companiondeck_token";
  var token = localStorage.getItem(TOKEN_KEY) || "";
  var state = null;
  var tracks = [];
  var categories = [];
  var activeCatIdx = null;
  var ws = null;
  var wsRetry = 0;
  var seeking = false;

  var $ = function (id) { return document.getElementById(id); };

  function headers(extra) {
    var h = Object.assign({ "Content-Type": "application/json" }, extra || {});
    if (token) h["Authorization"] = "Bearer " + token;
    return h;
  }

  function api(path, opts) {
    opts = opts || {};
    opts.headers = headers(opts.headers);
    return fetch(path, opts).then(function (r) {
      if (r.status === 401) { showTokenModal(); throw new Error("unauthorized"); }
      if (!r.ok) {
        return r.json().then(function (j) {
          throw new Error(j.detail || ("HTTP " + r.status));
        });
      }
      var ct = r.headers.get("content-type") || "";
      return ct.indexOf("json") >= 0 ? r.json() : r.text();
    });
  }

  function fmtTime(ms) {
    if (!ms && ms !== 0) return "--:--";
    var s = Math.floor(ms / 1000);
    var m = Math.floor(s / 60), sec = s % 60;
    return m + ":" + (sec < 10 ? "0" : "") + sec;
  }

  /* ---------- 适配器 / 传输 / 音量 ---------- */
  function renderAdapterSelect() {
    var sel = $("adapterSelect");
    var current = sel.value;
    sel.innerHTML = "";
    (state.adapters || []).forEach(function (a) {
      var opt = document.createElement("option");
      opt.value = a.name;
      opt.textContent = a.display_name + (a.available ? "" : "（离线）");
      sel.appendChild(opt);
    });
    if (current) sel.value = current;
    sel.value = state.adapter || "";
    var active = (state.adapters || []).find(function (a) { return a.name === state.adapter; });
    $("adapterDesc").textContent = active ? active.description : "";
  }

  function activeAdapter() {
    return (state.adapters || []).find(function (a) { return a.name === state.adapter; });
  }

  function renderTransport() {
    var card = $("transportCard");
    var actions = activeAdapter() ? activeAdapter().actions || [] : [];
    if (!actions.length) { card.classList.add("hidden"); return; }
    card.classList.remove("hidden");
    ["prev", "play_pause", "next", "stop"].forEach(function (act) {
      var btn = document.querySelector('[data-action="' + act + '"]');
      if (btn) btn.classList.toggle("hidden", actions.indexOf(act) < 0);
    });
    // 随机按钮：仅当适配器支持 random 能力时显示
    var caps = activeAdapter() ? activeAdapter().capabilities || [] : [];
    $("btnRandom").classList.toggle("hidden", caps.indexOf("random") < 0);
  }

  function renderVolume() {
    var card = $("volumeCard");
    var actions = activeAdapter() ? activeAdapter().actions || [] : [];
    var hasVol = actions.indexOf("volume_up") >= 0 || actions.indexOf("volume_down") >= 0 || actions.indexOf("toggle_mute") >= 0;
    if (!hasVol) { card.classList.add("hidden"); return; }
    card.classList.remove("hidden");
    $("btnMute").classList.toggle("hidden", actions.indexOf("toggle_mute") < 0);
    $("btnVolDown").classList.toggle("hidden", actions.indexOf("volume_down") < 0);
    $("btnVolUp").classList.toggle("hidden", actions.indexOf("volume_up") < 0);
    var canRead = typeof state.volume === "number";
    $("volumeSlider").classList.toggle("hidden", !canRead);
    $("volumeLabel").classList.toggle("hidden", !canRead);
    if (canRead) {
      $("volumeSlider").value = state.volume;
      $("volumeLabel").textContent = state.muted ? "静音" : state.volume + "%";
      $("btnMute").textContent = state.muted ? "🔇" : "🔊";
    }
  }

  function renderNowPlaying() {
    var pb = state.playback || {};
    var hasInfo = pb.duration_ms > 0 || pb.status !== "stopped" || pb.track_name;
    $("npCard").classList.toggle("hidden", !hasInfo);
    if (!hasInfo) return;
    var statusText = { playing: "正在播放", paused: "已暂停", stopped: "已停止" }[pb.status] || pb.status;
    $("npStatus").textContent = statusText;
    $("npTitle").textContent = pb.track_name || (state.adapter_display || "") + " · " + statusText;
    var meta = [];
    if (pb.artist) meta.push(pb.artist);
    if (pb.title && pb.title !== pb.track_name) meta.push(pb.title);
    if (typeof pb.play_count === "number") meta.push("播放 " + pb.play_count + " 次");
    $("npMeta").textContent = meta.join(" · ");
    var pct = pb.duration_ms > 0 ? Math.min(100, (pb.position_ms / pb.duration_ms) * 100) : 0;
    if (!seeking) $("progressBar").style.width = pct + "%";
    $("timeInfo").textContent = fmtTime(pb.position_ms) + " / " + fmtTime(pb.duration_ms);
    $("btnPlay").textContent = pb.status === "playing" ? "⏸" : "▶";
  }

  function renderProfiles() {
    var row = $("profileRow");
    if (!state.profiles || !state.profiles.length) { row.classList.add("hidden"); row.innerHTML = ""; return; }
    row.classList.remove("hidden");
    row.innerHTML = "";
    state.profiles.forEach(function (name) {
      var chip = document.createElement("button");
      chip.className = "chip" + (name === state.profile ? " active" : "");
      chip.textContent = name;
      chip.addEventListener("click", function () {
        api("/api/profile", { method: "POST", body: JSON.stringify({ profile: name }) })
          .then(refresh).catch(showError);
      });
      row.appendChild(chip);
    });
  }

  /* ---------- 分类 Tab ---------- */
  function renderCategories() {
    var card = $("categoryCard");
    var caps = activeAdapter() ? activeAdapter().capabilities || [] : [];
    if (caps.indexOf("categories") < 0) { card.classList.add("hidden"); return; }
    card.classList.remove("hidden");
    var tabsEl = $("catTabs");
    tabsEl.innerHTML = "";
    categories = state.categories || [];
    if (!categories.length) { card.classList.add("hidden"); return; }
    card.classList.remove("hidden");

    // 默认选中第一个非隐藏分类
    if (activeCatIdx === null || !categories.find(function (c) { return c.index === activeCatIdx; })) {
      var first = categories.find(function (c) { return !c.hidden; }) || categories[0];
      activeCatIdx = first ? first.index : null;
    }
    categories.forEach(function (c) {
      var tab = document.createElement("button");
      tab.className = "cat-tab" + (c.index === activeCatIdx ? " active" : "") + (c.hidden ? " hidden-cat" : "");
      tab.textContent = c.name + (c.sounds && c.sounds.length ? " (" + c.sounds.length + ")" : "");
      tab.addEventListener("click", function () {
        activeCatIdx = c.index;
        renderCategories();
        renderSounds();
        api("/api/category/select", { method: "POST", body: JSON.stringify({ index: c.index }) }).catch(showError);
      });
      tabsEl.appendChild(tab);
    });
  }

  /* ---------- 声音面板（按当前 Tab 分类） ---------- */
  function currentCategory() {
    return categories.find(function (c) { return c.index === activeCatIdx; });
  }

  function renderSounds() {
    var card = $("soundsCard");
    var caps = activeAdapter() ? activeAdapter().capabilities || [] : [];
    if (caps.indexOf("sounds") < 0 && caps.indexOf("categories") < 0) {
      card.classList.add("hidden"); return;
    }
    card.classList.remove("hidden");
    var sounds = state.sounds || [];
    var pbIdx = (state.playback || {}).index;
    var wrap = $("soundsWrap");
    wrap.innerHTML = "";

    // 若有分类且当前选中了某分类：只显示该分类的声音
    if (categories.length && currentCategory()) {
      var cur = currentCategory();
      sounds = sounds.filter(function (s) {
        return s.category_index === cur.index || s.category === cur.name;
      });
      if (!sounds.length && cur.sounds && cur.sounds.length) {
        // 用 categories 树里的声音兜底
        cur.sounds.forEach(function (t, i) {
          var btn = makeSoundButton({
            id: "cat" + cur.index + "-" + (t.index || i),
            name: t.title || t.name,
            category: cur.name,
            category_index: cur.index,
            position_in_category: i + 1,
            index: t.index,
            kind: "category_sound",
          }, pbIdx);
          wrap.appendChild(btn);
        });
        return;
      }
    }
    if (!sounds.length) {
      var empty = document.createElement("div");
      empty.className = "hint";
      empty.textContent = "（当前分类没有声音）";
      wrap.appendChild(empty);
      return;
    }
    sounds.forEach(function (s) {
      wrap.appendChild(makeSoundButton(s, pbIdx));
    });
  }

  function makeSoundButton(s, playingIdx) {
    var btn = document.createElement("button");
    btn.className = "sound-btn";
    if (s.index != null && s.index === playingIdx) btn.classList.add("playing");
    btn.textContent = s.name;
    btn.addEventListener("click", function () {
      api("/api/sound/play", { method: "POST", body: JSON.stringify({ id: s.id }) }).catch(showError);
    });
    return btn;
  }

  function renderTracks() {
    var card = $("tracksCard");
    var canTracks = activeAdapter() && activeAdapter().capabilities.indexOf("tracks") >= 0;
    card.classList.toggle("hidden", !canTracks);
    if (!canTracks) return;
    var kw = ($("trackFilter").value || "").trim().toLowerCase();
    var list = $("trackList");
    list.innerHTML = "";
    var shown = 0;
    var filtered = tracks.filter(function (t) {
      return !kw || (t.name && t.name.toLowerCase().indexOf(kw) >= 0);
    });
    var pbIdx = (state.playback || {}).index;
    if (kw) {
      filtered.forEach(function (t) {
        if (shown >= 300) return;
        shown++;
        list.appendChild(makeTrackItem(t, pbIdx));
      });
    } else {
      groupItems(filtered, function (t) { return t.category || "未分类"; }).forEach(function (g) {
        if (shown >= 300) return;
        var body = document.createElement("div");
        body.className = "track-sublist group-body";
        g.items.slice(0, 300 - shown).forEach(function (t) { body.appendChild(makeTrackItem(t, pbIdx)); shown++; });
        list.appendChild(buildGroup(g, body));
      });
    }
  }

  function groupItems(arr, keyFn) {
    var groups = [], byKey = {};
    arr.forEach(function (it) {
      var k = keyFn(it) || "";
      if (!byKey[k]) { byKey[k] = []; groups.push({ key: k, items: byKey[k] }); }
      byKey[k].push(it);
    });
    return groups;
  }

  function buildGroup(group, bodyEl) {
    var g = document.createElement("div");
    g.className = "group";
    var head = document.createElement("button");
    head.type = "button";
    head.className = "group-head";
    var name = document.createElement("span");
    name.className = "group-name";
    name.textContent = group.key;
    var count = document.createElement("span");
    count.className = "group-count";
    count.textContent = group.items.length;
    var caret = document.createElement("span");
    caret.className = "group-caret";
    caret.textContent = "▾";
    head.appendChild(name); head.appendChild(count); head.appendChild(caret);
    head.addEventListener("click", function () { g.classList.toggle("collapsed"); });
    g.appendChild(head);
    g.appendChild(bodyEl);
    return g;
  }

  function makeTrackItem(t, playingIdx) {
    var li = document.createElement("div");
    li.className = "track-item";
    if (t.index != null && t.index === playingIdx) li.classList.add("playing");
    var idx = document.createElement("span");
    idx.className = "track-idx";
    idx.textContent = t.index || "";
    var name = document.createElement("span");
    name.className = "track-name";
    name.textContent = t.name;
    var meta = document.createElement("span");
    meta.className = "track-meta";
    if (t.artist || t.duration) meta.textContent = [t.artist, t.duration].filter(Boolean).join(" · ");
    var play = document.createElement("span");
    play.className = "track-play";
    play.textContent = "▶";
    li.appendChild(idx); li.appendChild(name);
    if (meta.textContent) li.appendChild(meta);
    li.appendChild(play);
    li.addEventListener("click", function () {
      api("/api/sound/play", { method: "POST", body: JSON.stringify({ id: String(t.index) }) }).catch(showError);
    });
    return li;
  }

  function render() {
    renderAdapterSelect();
    renderTransport();
    renderVolume();
    renderNowPlaying();
    renderProfiles();
    renderCategories();
    renderSounds();
    renderTracks();
    var ok = state.adapter_available;
    $("statusDot").className = "dot " + (ok ? "ok" : "err");
    $("connText").textContent = ok ? "已连接" : (state.adapter ? "目标离线" : "无适配器");
    if (state.adapter && !ok) showError(new Error("目标软件（" + state.adapter_display + "）当前不可用，请确认它正在运行"));
  }

  function renderLight() {
    var ok = state.adapter_available;
    $("statusDot").className = "dot " + (ok ? "ok" : "err");
    $("connText").textContent = ok ? "已连接" : (state.adapter ? "目标离线" : "无适配器");
    renderNowPlaying();
    renderVolumeLight();
    renderSounds(); // 刷新"当前播放"高亮
  }

  function renderVolumeLight() {
    var canRead = typeof state.volume === "number";
    if (!canRead) return;
    var slider = $("volumeSlider");
    if (document.activeElement !== slider) {
      slider.value = state.volume;
      $("volumeLabel").textContent = state.muted ? "静音" : state.volume + "%";
      $("btnMute").textContent = state.muted ? "🔇" : "🔊";
    }
  }

  function refresh() {
    return api("/api/state").then(function (s) {
      state = s;
      render();
    }).catch(function (e) {
      if (e.message !== "unauthorized") showError(e);
    });
  }

  /* ---------- 进度条拖动跳转 ---------- */
  function bindProgressSeek() {
    var track = $("progressTrack");
    var bar = $("progressBar");
    function seekFromEvent(ev) {
      var rect = track.getBoundingClientRect();
      var x = (ev.clientX || (ev.touches && ev.touches[0].clientX) || 0) - rect.left;
      var pct = Math.max(0, Math.min(1, x / rect.width));
      var dur = (state.playback || {}).duration_ms || 0;
      if (dur > 0) {
        bar.style.width = (pct * 100) + "%";
        return Math.round(pct * dur);
      }
      return null;
    }
    var moved = false;
    track.addEventListener("pointerdown", function (ev) {
      seeking = true; moved = false;
      var pos = seekFromEvent(ev);
      if (pos != null) bar.style.width = ((pos / (state.playback || {}).duration_ms) * 100) + "%";
    });
    track.addEventListener("pointermove", function (ev) {
      if (!seeking) return;
      var pos = seekFromEvent(ev);
      if (pos != null) { bar.style.width = ((pos / (state.playback || {}).duration_ms) * 100) + "%"; moved = true; }
    });
    track.addEventListener("pointerup", function (ev) {
      if (!seeking) return;
      var pos = seekFromEvent(ev);
      if (pos != null && moved) {
        api("/api/seek", { method: "POST", body: JSON.stringify({ position_ms: pos }) }).catch(showError);
      }
      seeking = false;
    });
    track.addEventListener("pointercancel", function () { seeking = false; });
  }

  /* ---------- 动作绑定 ---------- */
  function bindActions() {
    document.querySelectorAll("[data-action]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var act = btn.getAttribute("data-action");
        api("/api/transport/" + act, { method: "POST" }).then(refresh).catch(showError);
      });
    });

    $("btnRandom").addEventListener("click", function () {
      api("/api/sound/random", { method: "POST" }).then(refresh).catch(showError);
    });

    $("btnCatRandom").addEventListener("click", function () {
      if (activeCatIdx == null) { showError(new Error("请先选择分类")); return; }
      api("/api/sound/random-from-category", { method: "POST", body: JSON.stringify({ category_index: activeCatIdx }) })
        .then(refresh).catch(showError);
    });

    $("btnCatPrev").addEventListener("click", function () {
      api("/api/category/prev", { method: "POST" }).then(function (s) { state = s; render(); }).catch(showError);
    });
    $("btnCatNext").addEventListener("click", function () {
      api("/api/category/next", { method: "POST" }).then(function (s) { state = s; render(); }).catch(showError);
    });

    $("adapterSelect").addEventListener("change", function () {
      api("/api/adapter", { method: "POST", body: JSON.stringify({ adapter: this.value }) })
        .then(function (s) { state = s; return loadTracks(); })
        .then(render)
        .catch(showError);
    });

    var slider = $("volumeSlider");
    slider.addEventListener("input", function () {
      $("volumeLabel").textContent = this.value + "%";
    });
    slider.addEventListener("change", function () {
      api("/api/volume", { method: "POST", body: JSON.stringify({ volume: parseInt(this.value, 10) }) }).catch(showError);
    });

    $("trackFilter").addEventListener("input", renderTracks);

    bindProgressSeek();

    // QR 弹窗
    $("btnQr").addEventListener("click", openQr);
    $("btnQrClose").addEventListener("click", function () {
      $("qrModal").classList.add("hidden");
    });
  }

  function loadTracks() {
    var active = activeAdapter();
    if (!active || active.capabilities.indexOf("tracks") < 0) { tracks = []; return Promise.resolve(); }
    return api("/api/tracks").then(function (list) {
      tracks = list || [];
    }).catch(function () { tracks = []; });
  }

  /* ---------- 二维码扫码连接 ---------- */
  function openQr() {
    var modal = $("qrModal");
    var wrap = $("qrWrap");
    var addr = $("qrAddr");
    wrap.innerHTML = "正在生成…";
    addr.textContent = "";
    modal.classList.remove("hidden");
    // 构造带 token 的 URL（用当前页面 host + token）
    var url = location.href;
    var img = new Image();
    img.src = "/api/qr?url=" + encodeURIComponent(url);
    img.alt = "扫码连接二维码";
    img.style.maxWidth = "100%";
    img.onload = function () { wrap.innerHTML = ""; wrap.appendChild(img); };
    img.onerror = function () {
      wrap.innerHTML = '<p style="color:#0b0e13;font-size:13px;">二维码库未安装，请手动复制地址：</p>';
      var code = document.createElement("div");
      code.textContent = url;
      code.style.cssText = "color:#0b0e13;word-break:break-all;font-size:12px;margin-top:8px;";
      wrap.appendChild(code);
    };
    addr.textContent = "地址：" + url;
  }

  /* ---------- WebSocket ---------- */
  function connectWs() {
    if (!token) return;
    try { if (ws) ws.close(); } catch (e) { /* ignore */ }
    var proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(proto + "://" + location.host + "/ws?token=" + encodeURIComponent(token));
    ws.onmessage = function (ev) {
      try {
        var s = JSON.parse(ev.data);
        if (!state) { state = s; render(); return; }
        if (s.adapter === state.adapter && s.version === state.version) {
          state.adapter_available = s.adapter_available;
          state.playback = s.playback;
          state.volume = s.volume;
          state.muted = s.muted;
          state.profile = s.profile;
          state.profiles = s.profiles;
          state.adapters = s.adapters;
          if (s.categories) state.categories = s.categories;
          renderLight();
        }
      } catch (e) { /* ignore */ }
    };
    ws.onclose = function () {
      wsRetry++;
      setTimeout(function () { if (token) connectWs(); }, Math.min(10000, 1000 * wsRetry));
    };
    ws.onopen = function () { wsRetry = 0; };
  }

  /* ---------- 令牌与错误 ---------- */
  function showTokenModal() {
    $("tokenModal").classList.remove("hidden");
    $("tokenInput").focus();
  }

  function hideTokenModal() {
    $("tokenModal").classList.add("hidden");
  }

  function showError(err) {
    var dot = $("statusDot");
    dot.className = "dot err";
    $("connText").textContent = "错误";
    console.error("[CompanionDeck]", err);
  }

  $("btnTokenOk").addEventListener("click", function () {
    var t = $("tokenInput").value.trim();
    if (!t) return;
    token = t;
    localStorage.setItem(TOKEN_KEY, t);
    hideTokenModal();
    loadVersion();
    refresh().then(connectWs);
  });

  /* ---------- 版本信息 ---------- */
  function loadVersion() {
    api("/api/version").then(function (v) {
      if (v.current) $("verNow").textContent = "v" + v.current;
      var el = $("verNew");
      if (!el) return;
      if (v.update_available && v.latest) {
        el.innerHTML = ' · <a href="' + (v.url || "#") + '" target="_blank" rel="noopener" style="color:#4ade80">🎉 有新版本 v' + v.latest + "</a>";
      } else if (v.checked && v.latest) {
        el.textContent = " · 已是最新";
      }
    }).catch(function () { /* 离线时静默 */ });
  }

  /* ---------- 启动 ---------- */
  bindActions();
  loadVersion();
  refresh().then(connectWs);
})();
