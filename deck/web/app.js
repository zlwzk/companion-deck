/* CompanionDeck 前端逻辑：状态拉取、WebSocket 实时推送、动作触发。 */
(function () {
  "use strict";

  var TOKEN_KEY = "companiondeck_token";
  var token = localStorage.getItem(TOKEN_KEY) || "";
  var state = null;
  var tracks = [];
  var ws = null;
  var wsRetry = 0;

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

  /* ---------- 渲染 ---------- */
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
    var active = state.adapters.find(function (a) { return a.name === state.adapter; });
    $("adapterDesc").textContent = active ? active.description : "";
  }

  function renderTransport() {
    var card = $("transportCard");
    var active = state.adapters.find(function (a) { return a.name === state.adapter; });
    var actions = active ? active.actions || [] : [];
    if (!actions.length) { card.classList.add("hidden"); return; }
    card.classList.remove("hidden");
    ["prev", "play_pause", "next", "stop"].forEach(function (act) {
      var btn = document.querySelector('[data-action="' + act + '"]');
      if (btn) btn.classList.toggle("hidden", actions.indexOf(act) < 0);
    });
  }

  function renderVolume() {
    var card = $("volumeCard");
    var active = state.adapters.find(function (a) { return a.name === state.adapter; });
    var actions = active ? active.actions || [] : [];
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
    var hasInfo = pb.duration_ms > 0 || pb.status !== "stopped";
    $("npCard").classList.toggle("hidden", !hasInfo);
    if (!hasInfo) return;
    var statusText = { playing: "正在播放", paused: "已暂停", stopped: "已停止" }[pb.status] || pb.status;
    $("npStatus").textContent = statusText;
    $("npTitle").textContent = pb.track_name || (state.adapter_display || "") + " · " + statusText;
    var pct = pb.duration_ms > 0 ? Math.min(100, (pb.position_ms / pb.duration_ms) * 100) : 0;
    $("progressBar").style.width = pct + "%";
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

  function renderSounds() {
    var card = $("soundsCard");
    var sounds = state.sounds || [];
    if (!sounds.length) { card.classList.add("hidden"); return; }
    card.classList.remove("hidden");
    var grid = $("soundsGrid");
    grid.innerHTML = "";
    sounds.forEach(function (s) {
      var btn = document.createElement("button");
      btn.className = "sound-btn";
      btn.textContent = s.name;
      btn.addEventListener("click", function () {
        api("/api/sound/play", { method: "POST", body: JSON.stringify({ id: s.id }) }).catch(showError);
      });
      grid.appendChild(btn);
    });
  }

  function renderTracks() {
    var card = $("tracksCard");
    var active = state.adapters.find(function (a) { return a.name === state.adapter; });
    var canTracks = active && active.capabilities.indexOf("tracks") >= 0;
    card.classList.toggle("hidden", !canTracks);
    if (!canTracks) return;
    var kw = ($("trackFilter").value || "").trim().toLowerCase();
    var list = $("trackList");
    list.innerHTML = "";
    var shown = 0;
    tracks.forEach(function (t) {
      if (kw && t.name && t.name.toLowerCase().indexOf(kw) < 0) return;
      if (shown >= 300) return;
      shown++;
      var li = document.createElement("li");
      li.className = "track-item";
      var idx = document.createElement("span");
      idx.className = "track-idx";
      idx.textContent = t.index || "";
      var name = document.createElement("span");
      name.className = "track-name";
      name.textContent = t.name;
      var play = document.createElement("span");
      play.className = "track-play";
      play.textContent = "▶";
      li.appendChild(idx); li.appendChild(name); li.appendChild(play);
      li.addEventListener("click", function () {
        api("/api/sound/play", { method: "POST", body: JSON.stringify({ id: String(t.index) }) }).catch(showError);
      });
      list.appendChild(li);
    });
    if (!shown) {
      var empty = document.createElement("li");
      empty.className = "track-item";
      empty.textContent = "（列表为空）";
      list.appendChild(empty);
    }
  }

  function render() {
    renderAdapterSelect();
    renderTransport();
    renderVolume();
    renderNowPlaying();
    renderProfiles();
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

  /* ---------- 动作 ---------- */
  function bindActions() {
    document.querySelectorAll("[data-action]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var act = btn.getAttribute("data-action");
        api("/api/transport/" + act, { method: "POST" }).then(refresh).catch(showError);
      });
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
  }

  function loadTracks() {
    var active = state.adapters.find(function (a) { return a.name === state.adapter; });
    if (!active || active.capabilities.indexOf("tracks") < 0) { tracks = []; return Promise.resolve(); }
    return api("/api/tracks").then(function (list) {
      tracks = list || [];
    }).catch(function () { tracks = []; });
  }

  /* ---------- WebSocket 实时推送 ---------- */
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
          // 轻量更新：只刷新指示器，不重建列表
          state.adapter_available = s.adapter_available;
          state.playback = s.playback;
          state.volume = s.volume;
          state.muted = s.muted;
          state.profile = s.profile;
          state.profiles = s.profiles;
          state.adapters = s.adapters;
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
    refresh().then(connectWs);
  });

  /* ---------- 启动 ---------- */
  bindActions();
  refresh().then(connectWs);
})();
