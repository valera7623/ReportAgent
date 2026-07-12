import { API_BASE, API_KEY_STORAGE } from "../config.js";
import { mountShell } from "../layout.js";
import { loadingHtml, toast } from "../ui.js";
import { escapeHtml } from "../utils.js";
import { bindDownloadButtons, pollTaskUntilSuccess } from "../download.js";
import { onError } from "../api.js";

let mediaRecorder = null;
let audioChunks = [];
let recording = false;
let recorderMimeType = "audio/webm";

function extensionFromMime(mime) {
  const m = (mime || "").toLowerCase();
  if (m.includes("webm")) return "webm";
  if (m.includes("ogg")) return "ogg";
  if (m.includes("mp4") || m.includes("m4a")) return "m4a";
  if (m.includes("mpeg") || m.includes("mp3")) return "mp3";
  if (m.includes("wav")) return "wav";
  return "webm";
}

function pickRecorderMimeType() {
  const types = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/ogg"];
  for (const type of types) {
    if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(type)) {
      return type;
    }
  }
  return "audio/webm";
}

function apiKey() {
  return localStorage.getItem(API_KEY_STORAGE);
}

async function pollVoiceTask(taskId, outputFormat, onStatus) {
  const key = apiKey();
  if (!key) throw new Error("Нет API-ключа");

  for (let i = 0; i < 120; i++) {
    const res = await fetch(`${API_BASE}/tasks/${taskId}`, {
      headers: { "X-API-Key": key },
    });
    const data = await res.json();
    const status = data.status;
    onStatus?.(status, data);

    if (status === "SUCCESS") {
      return data;
    }
    if (status === "FAILURE") {
      throw new Error(data.error || "Генерация отчёта не удалась");
    }
    if (status === "NEEDS_CLARIFICATION") {
      return { needsClarification: true, data };
    }
    await new Promise((r) => setTimeout(r, 2000));
  }
  throw new Error("Таймаут ожидания отчёта");
}

async function uploadVoice(blob, filename = "voice.webm") {
  const key = apiKey();
  if (!key) throw new Error("Войдите и создайте API-ключ");

  const form = new FormData();
  form.append("audio", blob, filename);

  const res = await fetch(`${API_BASE}/voice/generate_report`, {
    method: "POST",
    headers: { "X-API-Key": key },
    body: form,
  });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text };
  }
  if (!res.ok) {
    const msg = typeof data?.detail === "string" ? data.detail : data?.detail?.message || "Ошибка голосового запроса";
    throw new Error(msg);
  }
  return data;
}

async function sendClarification(taskId, answer) {
  const key = apiKey();
  const res = await fetch(`${API_BASE}/voice/clarify`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": key },
    body: JSON.stringify({ task_id: taskId, answer }),
  });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text };
  }
  if (!res.ok) {
    throw new Error(typeof data?.detail === "string" ? data.detail : "Ошибка уточнения");
  }
  return data;
}

function renderClarificationUI(root, taskId, question, transcript) {
  const el = root.querySelector("#voice-result");
  if (!el) return;
  el.innerHTML = `
    <div class="card"><div class="card-body">
      <h3>Нужно уточнение</h3>
      <p>${escapeHtml(question || "Уточните запрос")}</p>
      ${transcript ? `<p class="text-muted"><b>Распознано:</b> ${escapeHtml(transcript)}</p>` : ""}
      <textarea id="voice-clarify" class="input" rows="3" placeholder="Например: ссылка на Google Sheets или описание данных"></textarea>
      <button class="btn" id="voice-clarify-btn" style="margin-top:.75rem">Отправить уточнение</button>
    </div></div>`;

  el.querySelector("#voice-clarify-btn")?.addEventListener("click", async () => {
    const answer = el.querySelector("#voice-clarify")?.value?.trim();
    if (!answer) {
      toast("Введите ответ", "error");
      return;
    }
    const btn = el.querySelector("#voice-clarify-btn");
    btn.disabled = true;
    btn.textContent = "Обработка...";
    try {
      const result = await sendClarification(taskId, answer);
      if (result.status === "needs_clarification") {
        renderClarificationUI(root, result.task_id, result.clarification_question, null);
        toast("Нужно ещё одно уточнение", "info");
        return;
      }
      await handleQueuedTask(root, result.task_id, "pdf", result.download_url);
    } catch (err) {
      onError(err);
    } finally {
      btn.disabled = false;
      btn.textContent = "Отправить уточнение";
    }
  });
}

async function handleQueuedTask(root, taskId, outputFormat, downloadUrl) {
  const el = root.querySelector("#voice-result");
  if (el) {
    el.innerHTML = `<div class="card"><div class="card-body">
      <p>Генерация отчёта… <span class="mono">${escapeHtml(taskId.slice(0, 12))}…</span></p>
      <p class="text-muted" id="voice-poll-status">В очереди</p>
    </div></div>`;
  }

  await pollVoiceTask(taskId, outputFormat, (status) => {
    const st = root.querySelector("#voice-poll-status");
    if (st) st.textContent = `Статус: ${status}`;
  });

  if (el) {
    el.innerHTML = `<div class="card"><div class="card-body">
      <p class="text-success">Отчёт готов!</p>
      <button class="btn" data-download-task="${escapeHtml(taskId)}" data-download-format="${escapeHtml(outputFormat)}">Скачать</button>
      ${downloadUrl ? `<p class="text-muted" style="margin-top:.5rem"><a href="${escapeHtml(downloadUrl)}" target="_blank" rel="noopener">Прямая ссылка</a></p>` : ""}
    </div></div>`;
    bindDownloadButtons(el);
  }
  toast("Голосовой отчёт готов", "success");
}

async function startRecording(btn) {
  if (!navigator.mediaDevices?.getUserMedia) {
    toast("Микрофон недоступен в этом браузере", "error");
    return;
  }
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  audioChunks = [];
  recorderMimeType = pickRecorderMimeType();
  const options = recorderMimeType ? { mimeType: recorderMimeType } : undefined;
  mediaRecorder = new MediaRecorder(stream, options);
  mediaRecorder.ondataavailable = (e) => {
    if (e.data.size > 0) audioChunks.push(e.data);
  };
  mediaRecorder.start();
  recording = true;
  btn.textContent = "⏹ Остановить";
  btn.classList.add("btn-danger");
}

function stopRecording() {
  return new Promise((resolve) => {
    if (!mediaRecorder || !recording) {
      resolve(null);
      return;
    }
    mediaRecorder.onstop = () => {
      const mime = mediaRecorder.mimeType || recorderMimeType || "audio/webm";
      const blob = new Blob(audioChunks, { type: mime });
      mediaRecorder.stream.getTracks().forEach((t) => t.stop());
      recording = false;
      resolve(blob);
    };
    mediaRecorder.stop();
  });
}

export async function renderVoice(root) {
  mountShell(
    root,
    "Голос",
    `
    <div class="page-header">
      <h1>Голосовой отчёт</h1>
      <p class="seo-lead">Запишите запрос — ReportAgent распознает речь и сгенерирует отчёт. Нужен <code>OPENAI_API_KEY</code> на сервере.</p>
    </div>
    <div class="grid-2">
      <div class="card">
        <div class="card-body">
          <h3>Запись</h3>
          <p class="text-muted">Укажите в запросе ссылку на Google Sheets или опишите данные. Для CSV/Excel используйте дашборд.</p>
          <button class="btn" id="voice-record">🎤 Начать запись</button>
          <label class="btn btn-outline" style="margin-left:.5rem;cursor:pointer">
            Загрузить аудио
            <input type="file" id="voice-file" accept="audio/*,.webm,.m4a,.mp3,.wav,.ogg" hidden />
          </label>
        </div>
      </div>
      <div class="card">
        <div class="card-body">
          <h3>Пример фразы</h3>
          <p class="text-muted">«Сделай PDF-отчёт по таблице https://docs.google.com/spreadsheets/d/… с графиком продаж»</p>
        </div>
      </div>
    </div>
    <div id="voice-result" style="margin-top:1.25rem"></div>`,
    (el) => {
      const recordBtn = el.querySelector("#voice-record");
      recordBtn?.addEventListener("click", async () => {
        try {
          if (recording) {
            recordBtn.disabled = true;
            recordBtn.textContent = "Отправка...";
            const blob = await stopRecording();
            recordBtn.classList.remove("btn-danger");
            recordBtn.textContent = "🎤 Начать запись";
            if (!blob || blob.size < 500) {
              toast("Запись слишком короткая", "error");
              return;
            }
            const ext = extensionFromMime(blob.type);
            const result = await uploadVoice(blob, `voice.${ext}`);
            if (result.status === "needs_clarification") {
              renderClarificationUI(el, result.task_id, result.clarification_question, result.transcript);
              return;
            }
            const fmt = result.intent?.output_format || "pdf";
            await handleQueuedTask(el, result.task_id, fmt, result.download_url);
          } else {
            await startRecording(recordBtn);
          }
        } catch (err) {
          onError(err);
          recordBtn.textContent = "🎤 Начать запись";
          recordBtn.classList.remove("btn-danger");
          recording = false;
        } finally {
          recordBtn.disabled = false;
        }
      });

      el.querySelector("#voice-file")?.addEventListener("change", async (ev) => {
        const file = ev.target.files?.[0];
        if (!file) return;
        try {
          const result = await uploadVoice(file, file.name);
          if (result.status === "needs_clarification") {
            renderClarificationUI(el, result.task_id, result.clarification_question, result.transcript);
            return;
          }
          const fmt = result.intent?.output_format || "pdf";
          await handleQueuedTask(el, result.task_id, fmt, result.download_url);
        } catch (err) {
          onError(err);
        }
        ev.target.value = "";
      });
    },
  );
}
