(async () => {
  const params = new URLSearchParams(location.search);
  const hash = new URLSearchParams(location.hash.replace(/^#/, ""));
  const mode = params.get("mode") || "enroll";
  const sessionId = params.get("session_id");
  const sessionToken = hash.get("token") || sessionStorage.getItem("face_identity_session_token") || "";
  const mount = document.querySelector("#scanner-root");

  const onError = (error) => {
    console.error("FaceIdentity demo error", error);
  };
  const onSuccess = (result) => {
    console.info("FaceIdentity demo success", result);
  };
  const options = { sessionId, sessionToken, mount, onError, onSuccess, autoComplete: false };

  if (mode === "verify") {
    await window.FaceIdentity.verify(options);
  } else {
    await window.FaceIdentity.enroll(options);
  }
})();
