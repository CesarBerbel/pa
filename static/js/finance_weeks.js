/*
    A altura das barras das semanas.

    Feita aqui e não no template porque depende do maior valor das semanas do
    mês, e o template não sabe dividir. Feita em JavaScript e não no servidor
    porque é desenho: sem este ficheiro as barras ficam todas no mínimo, e os
    valores continuam escritos por cima de cada uma — nada do que interessa se
    perde.
*/
(function () {
    "use strict";

    var barras = document.querySelectorAll(".finance-week-bar");

    if (!barras.length) {
        return;
    }

    var valores = Array.prototype.map.call(barras, function (barra) {
        return parseFloat(barra.dataset.total || "0") || 0;
    });

    var maior = Math.max.apply(null, valores);

    if (maior <= 0) {
        return;
    }

    barras.forEach(function (barra, i) {
        // Um mínimo visível para uma semana com pouco não parecer uma
        // semana com nada: zero e "quase zero" são coisas diferentes, e a diferença
        // perde-se se as duas forem uma linha de um pixel.
        var altura = valores[i] > 0 ? Math.max(6, (valores[i] / maior) * 100) : 0;

        barra.style.height = altura + "%";
    });
})();
