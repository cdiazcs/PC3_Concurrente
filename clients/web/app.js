const MAX_UPLOAD_BYTES = 2 * 1024 * 1024; // 2 MB límite de archivo

const drawCanvas = document.getElementById("drawCanvas");
const drawCtx = drawCanvas.getContext("2d");
const preview16 = document.getElementById("preview16");
const prevCtx = preview16.getContext("2d");

const fileInput = document.getElementById("fileInput");
const clearCanvasBtn = document.getElementById("clearCanvasBtn");
const invertColorsChk = document.getElementById("invertColors");
const sendBtn = document.getElementById("sendBtn");
const clearChatBtn = document.getElementById("clearChatBtn");
const chatMessages = document.getElementById("chatMessages");
const base64Output = document.getElementById("base64Output");
const sizeInfo = document.getElementById("sizeInfo");
const statusBadge = document.getElementById("status-badge");

let isDrawing = false;
let reqCounter = 1;
const sessionId = Math.random().toString(36).substring(2, 8);

function initCanvas() {
  drawCtx.fillStyle = "#000000";
  drawCtx.fillRect(0, 0, drawCanvas.width, drawCanvas.height);
  drawCtx.strokeStyle = "#ffffff";
  drawCtx.lineWidth = 12;
  drawCtx.lineCap = "round";
  drawCtx.lineJoin = "round";
  syncDownsample16x16();
}

function getPos(evt) {
  const rect = drawCanvas.getBoundingClientRect();
  const clientX = evt.touches ? evt.touches[0].clientX : evt.clientX;
  const clientY = evt.touches ? evt.touches[0].clientY : evt.clientY;
  return {
    x: ((clientX - rect.left) / rect.width) * drawCanvas.width,
    y: ((clientY - rect.top) / rect.height) * drawCanvas.height,
  };
}

drawCanvas.addEventListener("pointerdown", (e) => {
  isDrawing = true;
  const p = getPos(e);
  drawCtx.beginPath();
  drawCtx.moveTo(p.x, p.y);
});

drawCanvas.addEventListener("pointermove", (e) => {
  if (!isDrawing) return;
  const p = getPos(e);
  drawCtx.lineTo(p.x, p.y);
  drawCtx.stroke();
  syncDownsample16x16();
});

window.addEventListener("pointerup", () => {
  if (isDrawing) {
    isDrawing = false;
    syncDownsample16x16();
  }
});

clearCanvasBtn.addEventListener("click", initCanvas);
invertColorsChk.addEventListener("change", syncDownsample16x16);

fileInput.addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (!file) return;
  if (file.size > MAX_UPLOAD_BYTES) {
    appendMessage("err", "La imagen supera el límite máximo permitido de 2 MB.");
    return;
  }
  const reader = new FileReader();
  reader.onload = (ev) => {
    const img = new Image();
    img.onload = () => {
      drawCtx.fillStyle = "#000000";
      drawCtx.fillRect(0, 0, drawCanvas.width, drawCanvas.height);
      drawCtx.drawImage(img, 0, 0, drawCanvas.width, drawCanvas.height);
      syncDownsample16x16();
    };
    img.src = ev.target.result;
  };
  reader.readAsDataURL(file);
});

/**
 * Reduce el lienzo a 16x16 y extrae los 256 valores en escala de grises [0..1]
 * más el PNG Base64 de la imagen 16x16.
 */
function syncDownsample16x16() {
  prevCtx.drawImage(drawCanvas, 0, 0, 16, 16);
  const imgData = prevCtx.getImageData(0, 0, 16, 16);
  const data = imgData.data;
  const invert = invertColorsChk.checked;
  const pixels = new Array(256);

  for (let i = 0; i < 256; i++) {
    const r = data[i * 4];
    const g = data[i * 4 + 1];
    const b = data[i * 4 + 2];
    let gray = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0;
    if (invert) gray = 1.0 - gray;
    gray = Math.max(0, Math.min(1, gray));
    pixels[i] = Number(gray.toFixed(6));

    // Reflejar exactamente en el preview16 lo que verá la CNN
    const lum = Math.round(gray * 255);
    data[i * 4] = lum;
    data[i * 4 + 1] = lum;
    data[i * 4 + 2] = lum;
    data[i * 4 + 3] = 255;
  }
  prevCtx.putImageData(imgData, 0, 0);

  const dataUrl = preview16.toDataURL("image/png");
  const pureBase64 = dataUrl.split(",")[1];
  base64Output.value = pureBase64;
  sizeInfo.textContent = `${pureBase64.length} chars Base64 · 256 floats`;

  return { pixels, pureBase64, dataUrl };
}

function appendMessage(type, htmlContent) {
  const div = document.createElement("div");
  div.className = `msg msg-${type}`;
  div.innerHTML = htmlContent;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

clearChatBtn.addEventListener("click", () => {
  chatMessages.innerHTML = "";
});

sendBtn.addEventListener("click", async () => {
  const { pixels, pureBase64, dataUrl } = syncDownsample16x16();
  const idSolicitud = `web-${sessionId}-${String(reqCounter++).padStart(4, "0")}`;
  const idCliente = document.getElementById("clientId").value.trim() || "cliente-web-01";
  const modo = document.getElementById("mode").value;
  const backendHost = document.getElementById("backendHost").value.trim() || "127.0.0.1";
  const backendPort = Number(document.getElementById("backendPort").value) || 9000;

  appendMessage(
    "user",
    `<div class="msg-meta">Solicitud: ${idSolicitud} · Modo: ${modo}</div>
     Enviando imagen 16×16 (${pureBase64.length} B Base64)
     <img src="${dataUrl}" class="thumb-chat" alt="16x16" />`
  );

  sendBtn.disabled = true;
  try {
    const res = await fetch("/api/classify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        schemaVersion: 1,
        tipo: "CLASIFICAR_IMAGEN",
        idSolicitud,
        idCliente,
        modeloDestino: "A",
        modo,
        timestamp: new Date().toISOString(),
        intento: 1,
        backendHost,
        backendPort,
        payload: {
          mimeType: "image/png",
          imagenBase64: pureBase64,
          pixels,
        },
      }),
    });

    const data = await res.json();
    if (!res.ok) {
      appendMessage("err", `<div class="msg-meta">Error HTTP ${res.status} · ${idSolicitud}</div>${data.error || "Fallo en clasificación"}`);
      return;
    }

    const p = data.payload;
    const probs = p.probabilidades;
    appendMessage(
      "bot",
      `<div class="msg-meta">ID: ${data.idSolicitud} · ${p.duracionMs} ms · ${p.modo}</div>
       <strong>Predicción: ${p.etiqueta.toUpperCase()}</strong><br/>
       Círculo: ${(probs.circulo * 100).toFixed(2)}% |
       Cruz: ${(probs.cruz * 100).toFixed(2)}% |
       Triángulo: ${(probs.triangulo * 100).toFixed(2)}%`
    );
  } catch (err) {
    appendMessage("err", `<div class="msg-meta">Error de red · ${idSolicitud}</div>No se pudo contactar con el Gateway HTTP: ${err.message}`);
  } finally {
    sendBtn.disabled = false;
  }
});

async function checkGatewayHealth() {
  try {
    const res = await fetch("/api/health");
    if (res.ok) {
      statusBadge.textContent = "Gateway HTTP Activo";
      statusBadge.className = "badge badge-ok";
    } else {
      statusBadge.textContent = "Gateway con advertencias";
      statusBadge.className = "badge badge-warn";
    }
  } catch {
    statusBadge.textContent = "Gateway desconectado";
    statusBadge.className = "badge badge-err";
  }
}

initCanvas();
checkGatewayHealth();