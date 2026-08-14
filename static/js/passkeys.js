// Entrada com biometria (WebAuthn).
//
// O browser trata da leitura da digital; este ficheiro apenas traduz entre o
// JSON do servidor e os formatos binários que a API exige, e vice-versa.

(function () {
    "use strict";

    function base64urlToBuffer(valor) {
        const base64 = valor.replace(/-/g, "+").replace(/_/g, "/");
        const preenchido = base64.padEnd(
            base64.length + ((4 - (base64.length % 4)) % 4),
            "="
        );
        const binario = atob(preenchido);
        const bytes = new Uint8Array(binario.length);

        for (let i = 0; i < binario.length; i += 1) {
            bytes[i] = binario.charCodeAt(i);
        }

        return bytes.buffer;
    }

    function bufferToBase64url(buffer) {
        const bytes = new Uint8Array(buffer);
        let binario = "";

        for (let i = 0; i < bytes.byteLength; i += 1) {
            binario += String.fromCharCode(bytes[i]);
        }

        return btoa(binario)
            .replace(/\+/g, "-")
            .replace(/\//g, "_")
            .replace(/=/g, "");
    }

    function getCsrfToken() {
        const campo = document.querySelector("[name=csrfmiddlewaretoken]");
        return campo ? campo.value : "";
    }

    function postJson(url, body) {
        return fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCsrfToken(),
            },
            body: body ? JSON.stringify(body) : "{}",
        }).then(function (response) {
            return response.json().then(function (dados) {
                if (!response.ok) {
                    throw new Error(dados.error || "Ocorreu um erro.");
                }
                return dados;
            });
        });
    }

    function mostrarErro(elemento, mensagem) {
        if (!elemento) {
            return;
        }

        elemento.textContent = mensagem;
        elemento.hidden = false;
    }

    // O suporte existe em praticamente todos os telemóveis atuais, mas o site
    // tem de continuar utilizável onde não existe.
    const suportado =
        window.PublicKeyCredential !== undefined &&
        typeof navigator.credentials?.create === "function";

    document.querySelectorAll("[data-passkey-requires-support]").forEach(function (el) {
        el.hidden = !suportado;
    });

    document.querySelectorAll("[data-passkey-unsupported]").forEach(function (el) {
        el.hidden = suportado;
    });

    // --- Registo de um dispositivo ---

    const botaoRegisto = document.querySelector("[data-passkey-register]");

    if (botaoRegisto && suportado) {
        botaoRegisto.addEventListener("click", function () {
            const erro = document.querySelector("[data-passkey-error]");
            const campoNome = document.querySelector("[data-passkey-name]");

            if (erro) {
                erro.hidden = true;
            }

            botaoRegisto.disabled = true;

            postJson(botaoRegisto.dataset.optionsUrl)
                .then(function (opcoes) {
                    opcoes.challenge = base64urlToBuffer(opcoes.challenge);
                    opcoes.user.id = base64urlToBuffer(opcoes.user.id);

                    (opcoes.excludeCredentials || []).forEach(function (item) {
                        item.id = base64urlToBuffer(item.id);
                    });

                    return navigator.credentials.create({ publicKey: opcoes });
                })
                .then(function (credential) {
                    return postJson(botaoRegisto.dataset.verifyUrl, {
                        name: campoNome ? campoNome.value : "",
                        credential: {
                            id: credential.id,
                            rawId: bufferToBase64url(credential.rawId),
                            type: credential.type,
                            response: {
                                clientDataJSON: bufferToBase64url(
                                    credential.response.clientDataJSON
                                ),
                                attestationObject: bufferToBase64url(
                                    credential.response.attestationObject
                                ),
                            },
                        },
                    });
                })
                .then(function () {
                    window.location.reload();
                })
                .catch(function (e) {
                    botaoRegisto.disabled = false;
                    // NotAllowedError acontece quando a pessoa cancela: não é
                    // um erro que valha a pena mostrar em vermelho.
                    if (e && e.name === "NotAllowedError") {
                        return;
                    }
                    mostrarErro(erro, e.message || "Não foi possível registar.");
                });
        });
    }

    // --- Entrada ---

    const botaoEntrada = document.querySelector("[data-passkey-login]");

    if (botaoEntrada && suportado) {
        botaoEntrada.addEventListener("click", function () {
            const erro = document.querySelector("[data-passkey-error]");

            if (erro) {
                erro.hidden = true;
            }

            botaoEntrada.disabled = true;

            postJson(botaoEntrada.dataset.optionsUrl)
                .then(function (opcoes) {
                    opcoes.challenge = base64urlToBuffer(opcoes.challenge);

                    (opcoes.allowCredentials || []).forEach(function (item) {
                        item.id = base64urlToBuffer(item.id);
                    });

                    return navigator.credentials.get({ publicKey: opcoes });
                })
                .then(function (assertion) {
                    return postJson(botaoEntrada.dataset.verifyUrl, {
                        credential: {
                            id: assertion.id,
                            rawId: bufferToBase64url(assertion.rawId),
                            type: assertion.type,
                            response: {
                                clientDataJSON: bufferToBase64url(
                                    assertion.response.clientDataJSON
                                ),
                                authenticatorData: bufferToBase64url(
                                    assertion.response.authenticatorData
                                ),
                                signature: bufferToBase64url(
                                    assertion.response.signature
                                ),
                                userHandle: assertion.response.userHandle
                                    ? bufferToBase64url(assertion.response.userHandle)
                                    : null,
                            },
                        },
                    });
                })
                .then(function (dados) {
                    window.location.href = dados.redirect_url;
                })
                .catch(function (e) {
                    botaoEntrada.disabled = false;
                    if (e && e.name === "NotAllowedError") {
                        return;
                    }
                    mostrarErro(erro, e.message || "Não foi possível entrar.");
                });
        });
    }
})();
