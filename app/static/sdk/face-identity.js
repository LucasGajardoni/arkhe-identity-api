(function attachFaceIdentity(global) {
  class FaceIdentityError extends Error {
    constructor(message, code, detail) {
      super(message);
      this.name = "FaceIdentityError";
      this.code = code || "FACE_IDENTITY_ERROR";
      this.detail = detail;
    }
  }

  class CameraController {
    constructor(video, constraints) {
      this.video = video;
      this.constraints = constraints || { video: { facingMode: "user" }, audio: false };
      this.stream = null;
    }

    async start() {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new FaceIdentityError("Camera indisponivel neste navegador.", "CAMERA_UNAVAILABLE");
      }
      this.stream = await navigator.mediaDevices.getUserMedia(this.constraints);
      this.video.srcObject = this.stream;
      await this.video.play();
      return this.stream;
    }

    capture() {
      const canvas = document.createElement("canvas");
      canvas.width = this.video.videoWidth;
      canvas.height = this.video.videoHeight;
      const context = canvas.getContext("2d");
      context.drawImage(this.video, 0, 0);
      return canvas.toDataURL("image/jpeg", 0.9).split(",")[1];
    }

    stop() {
      if (this.stream) {
        this.stream.getTracks().forEach((track) => track.stop());
        this.stream = null;
      }
      this.video.srcObject = null;
    }
  }

  class FaceIdentityTransport {
    constructor(baseUrl) {
      this.baseUrl = (baseUrl || "").replace(/\/$/, "");
    }

    async post(path, sessionToken, body) {
      const res = await fetch(`${this.baseUrl}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${sessionToken}` },
        body: JSON.stringify(body || {}),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = data.detail || {};
        throw new FaceIdentityError(detail.message || detail || "Falha na API facial.", detail.code || `HTTP_${res.status}`, data);
      }
      return data;
    }
  }

  class ScannerUI {
    constructor(options) {
      this.mount = options.mount || document.body;
      this.labels = {
        center_face: "Centralize o rosto",
        turn_left: "Vire um pouco para a esquerda",
        turn_right: "Vire um pouco para a direita",
        turn_up: "Levante um pouco o rosto",
        turn_down: "Abaixe um pouco o rosto",
        complete: "Capturas suficientes",
      };
      this.root = document.createElement("div");
      this.root.className = "face-identity-widget";
      this.root.innerHTML = `
        <video class="face-identity-video" autoplay playsinline muted></video>
        <div class="face-identity-controls">
          <strong data-role="status">Centralize o rosto</strong>
          <button type="button" data-role="capture">Capturar</button>
          <button type="button" data-role="stop">Encerrar</button>
        </div>
      `;
      this.mount.appendChild(this.root);
      this.video = this.root.querySelector("video");
      this.status = this.root.querySelector('[data-role="status"]');
      this.captureButton = this.root.querySelector('[data-role="capture"]');
      this.stopButton = this.root.querySelector('[data-role="stop"]');
    }

    setStatus(value) {
      this.status.textContent = this.labels[value] || value || "Aguardando";
    }

    destroy() {
      this.root.remove();
    }
  }

  async function runScanner(mode, options) {
    if (!options || !options.sessionId || !options.sessionToken) {
      throw new FaceIdentityError("sessionId e sessionToken sao obrigatorios.", "INVALID_OPTIONS");
    }
    const transport = options.transport || new FaceIdentityTransport(options.baseUrl);
    const ui = options.ui || new ScannerUI(options);
    const camera = options.camera || new CameraController(ui.video, options.constraints);
    const capturePath =
      mode === "verify"
        ? `/v1/verifications/${options.sessionId}/attempts`
        : `/v1/enrollments/${options.sessionId}/captures`;

    let closed = false;
    let capturing = false;

    const cleanup = () => {
      closed = true;
      camera.stop();
      if (options.destroyOnClose) ui.destroy();
    };

    try {
      await camera.start();
      ui.captureButton.addEventListener("click", async () => {
        if (closed || capturing) return;
        capturing = true;

        try {
          const imageBase64 = camera.capture();
          const result = await transport.post(capturePath, options.sessionToken, { image_base64: imageBase64 });
          options.onProgress?.(result);
          ui.setStatus(result.next_hint || result.status);

          if (mode === "verify") {
            if (result.matched || result.status === "not_matched") {
              cleanup();
            }

            options.onSuccess?.(result);
          } else if (result.ready && options.autoComplete) {
            const complete = await transport.post(`/v1/enrollments/${options.sessionId}/complete`, options.sessionToken);
            cleanup();
            options.onSuccess?.(complete);
          }
        } catch (error) {
          options.onError?.(error);
          ui.setStatus(error.message);
        } finally {
          capturing = false;
        }
      });
      ui.stopButton.addEventListener("click", cleanup);
      return { camera, transport, ui, stop: cleanup };
    } catch (error) {
      cleanup();
      options.onError?.(error);
      throw error;
    }
  }

  const FaceIdentity = {
    CameraController,
    FaceIdentityError,
    FaceIdentityTransport,
    ScannerUI,
    enroll(options) {
      return runScanner("enroll", options);
    },
    verify(options) {
      return runScanner("verify", options);
    },
  };

  global.FaceIdentity = FaceIdentity;
})(window);
