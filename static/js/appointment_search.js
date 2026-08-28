/*
    Procura por nome na lista de atendimentos.

    A peça verdadeira é o <select> que vem do servidor: sem este ficheiro
    continua a escolher-se um atendimento e o formulário grava na mesma. O que
    isto acrescenta é uma caixa de procura por cima — uma lista pendente com
    centenas de consultas encontra-se a escrever, mas só se o teclado ajudar, e
    num telemóvel não ajuda.

    Mesmo desenho da procura de indicativos em phone_country_search.js.
*/
(function () {
    "use strict";

    function semAcentos(texto) {
        // "Sonia" tem de encontrar "Sónia": quem escreve depressa não vai
        // buscar o acento.
        return texto.normalize("NFD").replace(/[̀-ͯ]/g, "");
    }

    function ligar(seletor) {
        if (seletor.dataset.searchReady) {
            return;
        }

        seletor.dataset.searchReady = "1";

        var opcoes = Array.prototype.map.call(seletor.options, function (opcao) {
            return {
                elemento: opcao,
                procuravel: semAcentos(opcao.textContent.toLowerCase()),
                // A opção vazia — "Escolha o atendimento…" — nunca se esconde:
                // é como se desfaz uma escolha.
                fixa: opcao.value === "",
            };
        });

        var caixa = document.createElement("input");
        caixa.type = "search";
        caixa.className = "form-control mb-2";
        caixa.autocomplete = "off";
        caixa.placeholder = "Procurar pelo nome da pessoa…";
        caixa.setAttribute("aria-label", "Procurar atendimento pelo nome");

        var contagem = document.createElement("p");
        contagem.className = "form-text mt-1 mb-0";
        // `aria-live` para quem não vê a lista a encolher ouvir o resultado.
        contagem.setAttribute("aria-live", "polite");

        seletor.parentNode.insertBefore(caixa, seletor);
        seletor.parentNode.insertBefore(contagem, seletor.nextSibling);

        function filtrar() {
            var procura = semAcentos(caixa.value.trim().toLowerCase());
            var visiveis = 0;

            opcoes.forEach(function (opcao) {
                var mostra = opcao.fixa || !procura || opcao.procuravel.indexOf(procura) !== -1;

                // `hidden` e `disabled` juntos: houve browsers que
                // ignoraram o `hidden` num <option>, e aí a opção continuava
                // a aparecer na lista. Desativada, pelo menos não se escolhe.
                opcao.elemento.hidden = !mostra;
                opcao.elemento.disabled = !mostra;

                if (mostra && !opcao.fixa) {
                    visiveis += 1;
                }
            });

            if (!procura) {
                contagem.textContent = "";
                return;
            }

            if (visiveis === 0) {
                contagem.textContent = "Nenhum atendimento com esse nome.";
                return;
            }

            contagem.textContent =
                visiveis === 1 ? "1 atendimento" : visiveis + " atendimentos";

            // Com um só resultado, escolhe-se sozinho: é o que a pessoa ia
            // fazer a seguir de qualquer maneira.
            if (visiveis === 1) {
                var unica = opcoes.filter(function (o) {
                    return !o.fixa && !o.elemento.hidden;
                })[0];

                seletor.value = unica.elemento.value;
            }
        }

        caixa.addEventListener("input", filtrar);
    }

    document.querySelectorAll("select[data-appointment-search]").forEach(ligar);
})();
