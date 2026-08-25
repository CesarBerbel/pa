/*
    Procura no seletor de indicativo do telefone.

    A peça verdadeira é o <select> que vem do servidor: sem este ficheiro
    continua a escolher-se um país e o formulário funciona na mesma. O que isto
    acrescenta é uma caixa de procura por cima — duzentos países numa lista
    pendente encontram-se a escrever, mas só se o teclado ajudar, e num
    telemóvel não ajuda.

    Não há dependências: o mesmo desenho da lista de moradas sugeridas, que já
    existia na marcação.
*/
(function () {
    "use strict";

    function ligar(campo) {
        var seletor = campo.querySelector("[data-phone-country]");

        if (!seletor || campo.dataset.phoneReady) {
            return;
        }

        campo.dataset.phoneReady = "1";

        var paises = Array.prototype.map.call(seletor.options, function (opcao) {
            return {
                valor: opcao.value,
                texto: opcao.textContent.trim(),
                // Sem acentos, para "Suecia" encontrar "Suécia": quem escreve
                // depressa não vai buscar o acento.
                procuravel: semAcentos(opcao.textContent.toLowerCase())
            };
        });

        var caixa = document.createElement("input");
        caixa.type = "text";
        caixa.className = "form-control phone-country-search";
        caixa.autocomplete = "off";
        caixa.setAttribute("role", "combobox");
        caixa.setAttribute("aria-expanded", "false");
        caixa.setAttribute("aria-label", "País do indicativo");

        var lista = document.createElement("ul");
        lista.className = "phone-country-list";
        lista.setAttribute("role", "listbox");
        lista.hidden = true;

        var caixaDoSeletor = seletor.parentNode;
        caixaDoSeletor.classList.add("phone-country-picker");
        caixaDoSeletor.insertBefore(caixa, seletor);
        caixaDoSeletor.appendChild(lista);

        // O <select> continua a ser quem guarda a resposta: fica escondido dos
        // olhos, mas não dos formulários nem dos leitores de ecrã que o sigam
        // pela etiqueta.
        seletor.classList.add("visually-hidden");
        seletor.setAttribute("tabindex", "-1");

        function semAcentos(texto) {
            if (!texto.normalize) {
                return texto;
            }

            return texto.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
        }

        function mostrarEscolhido() {
            var escolhido = paises.filter(function (pais) {
                return pais.valor === seletor.value;
            })[0];

            caixa.value = escolhido ? escolhido.texto : "";
        }

        function fechar() {
            lista.hidden = true;
            lista.innerHTML = "";
            caixa.setAttribute("aria-expanded", "false");
        }

        function escolher(pais) {
            seletor.value = pais.valor;
            // Quem estiver a ouvir o <select> — o próprio formulário, ou outro
            // JavaScript — não pode ficar sem saber que ele mudou.
            seletor.dispatchEvent(new Event("change", { bubbles: true }));
            mostrarEscolhido();
            fechar();
        }

        function desenhar(encontrados) {
            lista.innerHTML = "";

            if (!encontrados.length) {
                fechar();
                return;
            }

            var escolhido = null;

            // A lista sai inteira, e não cortada: aberta sem nada escrito, é
            // uma lista pendente como a de qualquer <select>, e é a altura da
            // caixa que a limita. Quem escreve estreita-a por si.
            encontrados.forEach(function (pais) {
                var item = document.createElement("li");
                var botao = document.createElement("button");

                botao.type = "button";
                botao.className = "phone-country-option";
                botao.setAttribute("role", "option");
                botao.textContent = pais.texto;

                if (pais.valor === seletor.value) {
                    botao.classList.add("is-chosen");
                    botao.setAttribute("aria-selected", "true");
                    escolhido = botao;
                }

                botao.addEventListener("click", function () {
                    escolher(pais);
                });

                botao.addEventListener("keydown", function (evento) {
                    if (evento.key === "ArrowDown" || evento.key === "ArrowUp") {
                        evento.preventDefault();
                        andar(botao, evento.key === "ArrowDown" ? 1 : -1);
                        return;
                    }

                    if (evento.key === "Escape") {
                        fechar();
                        mostrarEscolhido();
                        caixa.focus();
                    }
                });

                item.appendChild(botao);
                lista.appendChild(item);
            });

            lista.hidden = false;
            caixa.setAttribute("aria-expanded", "true");

            // Abrir com o país escolhido à vista, e não no princípio de uma
            // lista de duzentos onde ele pode estar a meio.
            if (escolhido && escolhido.scrollIntoView) {
                escolhido.scrollIntoView({ block: "nearest" });
            }
        }

        function opcoes() {
            return Array.prototype.slice.call(
                lista.querySelectorAll(".phone-country-option")
            );
        }

        function andar(botao, passo) {
            var todos = opcoes();
            var seguinte = todos[todos.indexOf(botao) + passo];

            if (seguinte) {
                seguinte.focus();
            } else if (passo < 0) {
                // Do primeiro para cima volta-se à caixa, para continuar a
                // escrever sem tirar as mãos do teclado.
                caixa.focus();
            }
        }

        function procurar() {
            var texto = semAcentos(caixa.value.trim().toLowerCase());

            if (!texto) {
                desenhar(paises);
                return;
            }

            desenhar(
                paises.filter(function (pais) {
                    return pais.procuravel.indexOf(texto) !== -1;
                })
            );
        }

        function abrir() {
            // A caixa mostra o país escolhido, e usá-lo como procura abria a
            // lista com um item só — o que já estava escolhido. Clicar tem de
            // abrir a lista inteira, como um <select> faz.
            desenhar(paises);
            caixa.select();
        }

        caixa.addEventListener("input", procurar);
        caixa.addEventListener("focus", abrir);
        caixa.addEventListener("mousedown", function (evento) {
            // Já com o foco, um segundo clique volta a abrir em vez de não
            // fazer nada: é o que acontece num <select>.
            if (document.activeElement === caixa && lista.hidden) {
                evento.preventDefault();
                abrir();
            }
        });

        caixa.addEventListener("keydown", function (evento) {
            if (evento.key === "Escape") {
                fechar();
                mostrarEscolhido();
                return;
            }

            if (evento.key === "ArrowDown") {
                evento.preventDefault();

                if (lista.hidden) {
                    abrir();
                }

                var partida =
                    lista.querySelector(".phone-country-option.is-chosen") ||
                    lista.querySelector(".phone-country-option");

                if (partida) {
                    partida.focus();
                }

                return;
            }

            if (evento.key === "Enter" && !lista.hidden) {
                // Sem isto, o Enter submetia o formulário com a procura
                // escrita e o país por escolher.
                evento.preventDefault();

                var escolhido = lista.querySelector(
                    ".phone-country-option.is-chosen"
                );

                // Aberta sem nada escrito, a lista está inteira e o primeiro
                // é Portugal: escolher-lhe o primeiro trocava o país a quem só
                // queria fechar a lista.
                if (escolhido && caixa.value.trim() === escolhido.textContent) {
                    fechar();
                    return;
                }

                var primeiro = lista.querySelector(".phone-country-option");

                if (primeiro) {
                    primeiro.click();
                }
            }
        });

        document.addEventListener("click", function (evento) {
            if (!caixaDoSeletor.contains(evento.target)) {
                fechar();
                mostrarEscolhido();
            }
        });

        mostrarEscolhido();
    }

    function ligarTodos(raiz) {
        Array.prototype.forEach.call(
            (raiz || document).querySelectorAll("[data-phone-field]"),
            ligar
        );
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            ligarTodos(document);
        });
    } else {
        ligarTodos(document);
    }

    // Para os formulários que aparecem depois, como o do cliente novo dentro
    // da marcação.
    window.ligarProcuraDeIndicativos = ligarTodos;
})();
