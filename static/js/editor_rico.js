/*
 * O editor de texto das páginas do "o que tratamos".
 *
 * Troca a caixa de texto por um editor com barra de ferramentas — títulos,
 * listas, tabelas, ligações e imagens. Se este ficheiro não correr, ou se o
 * TinyMCE não carregar, a caixa de texto continua lá e continua a gravar: o
 * que se perde é o conforto, não o trabalho.
 *
 * `license_key: "gpl"` porque é a versão auto-alojada sob GPL. Sem isso, o
 * TinyMCE 7 põe um aviso por cima do editor.
 */

(function () {
    "use strict";

    // `querySelectorAll` e não `querySelector`: há duas caixas — o texto
    // português e o inglês — e a primeira versão disto punha o editor só na
    // primeira que encontrasse.
    var caixas = document.querySelectorAll(".editor-rico");

    if (!caixas.length || typeof tinymce === "undefined") {
        return;
    }

    var config = document.getElementById("editor-rico-config");
    var enderecoDaImagem = config ? config.dataset.uploadUrl : "";
    var token = config ? config.dataset.csrf : "";

    function enviarImagem(blobInfo) {
        // O envio é feito à mão e não pelo mecanismo do TinyMCE porque o
        // Django exige o cabeçalho CSRF, e o mecanismo dele não o põe.
        return new Promise(function (resolve, reject) {
            var dados = new FormData();
            dados.append("file", blobInfo.blob(), blobInfo.filename());

            fetch(enderecoDaImagem, {
                method: "POST",
                headers: { "X-CSRFToken": token },
                body: dados,
                credentials: "same-origin",
            })
                .then(function (resposta) {
                    return resposta.json().then(function (corpo) {
                        if (!resposta.ok) {
                            // A mensagem vem do servidor — "isto não é uma
                            // imagem", "não pode passar de 2 MB" — e é a que
                            // faz sentido mostrar a quem está a escrever.
                            reject({
                                message: corpo.error || "Não foi possível enviar.",
                                remove: true,
                            });
                            return;
                        }

                        resolve(corpo.location);
                    });
                })
                .catch(function () {
                    reject({ message: "Não foi possível enviar a imagem.", remove: true });
                });
        });
    }

    caixas.forEach(function (caixa) {
        tinymce.init({
            target: caixa,
            license_key: "gpl",
            language: "pt_PT",
            menubar: "edit view insert format table",
            plugins: "lists link image table code autoresize visualblocks",
            toolbar:
                "undo redo | blocks | bold italic underline | " +
                "bullist numlist | link image table | removeformat code",

            // Só os títulos que a página aceita. O <h1> é o título da página e
            // é a página que o dá: dois <h1> valem menos do que um, e o
            // sanitizador do servidor deitá-lo-ia fora à mesma.
            block_formats:
                "Parágrafo=p; Título=h2; Subtítulo=h3; Subtítulo menor=h4; Citação=blockquote",

            // Cresce com o texto em vez de ter uma barra de deslocamento própria.
            // Duas barras na mesma página é o que faz perder o sítio onde se ia.
            autoresize_bottom_margin: 30,
            min_height: 420,
            max_height: 900,

            branding: false,
            promotion: false,
            convert_urls: false,

            images_upload_handler: enviarImagem,
            automatic_uploads: true,
            // Colar uma imagem do lado de fora envia-a; sem isto ficava embutida
            // no HTML como base64 e o sanitizador do servidor deitava-a fora.
            paste_data_images: true,

            content_style:
                "body { font-family: system-ui, sans-serif; font-size: 16px; line-height: 1.7; }" +
                "table { border-collapse: collapse; }" +
                "table td, table th { border: 1px solid #ccc; padding: 6px 10px; }",
        });
    });
})();
