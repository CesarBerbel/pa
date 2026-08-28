/*
    As mensagens do site fecham-se sozinhas.

    Cada uma traz o seu prazo em `data-auto-dismiss`: dois segundos para as
    informativas, cinco para os erros. Um erro precisa de mais tempo porque
    quem o lê tem de decidir o que fazer a seguir; uma confirmação só precisa
    de ser vista.

    **A contagem pára enquanto lá estiverem.** Com o rato por cima ou com o
    teclado dentro da mensagem, alguém está a lê-la — fechá-la à conta do
    relógio seria tirar-lhe da frente exatamente aquilo que foi pedir. Volta a
    contar quando sair, e do princípio.

    Sem este ficheiro as mensagens ficam na página até alguém carregar no X,
    que é como sempre foi.
*/
(function () {
    "use strict";

    function ligar(alerta) {
        var prazo = parseInt(alerta.dataset.autoDismiss || "0", 10);

        if (!prazo || typeof bootstrap === "undefined") {
            return;
        }

        var relogio = null;

        function fechar() {
            // `getOrCreateInstance` e não `new`: o Bootstrap já criou a sua
            // instância se alguém carregou no X primeiro, e duas instâncias
            // sobre o mesmo elemento deixam-no meio fechado.
            bootstrap.Alert.getOrCreateInstance(alerta).close();
        }

        function contar() {
            parar();
            relogio = window.setTimeout(fechar, prazo);
        }

        function parar() {
            if (relogio) {
                window.clearTimeout(relogio);
                relogio = null;
            }
        }

        alerta.addEventListener("mouseenter", parar);
        alerta.addEventListener("mouseleave", contar);
        alerta.addEventListener("focusin", parar);
        alerta.addEventListener("focusout", contar);

        contar();
    }

    document.querySelectorAll("[data-auto-dismiss]").forEach(ligar);
})();
