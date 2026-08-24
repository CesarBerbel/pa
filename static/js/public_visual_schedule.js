$(document).ready(function () {
    // Public visual schedule AJAX controller.

    const serviceInput = $("#service");
    const dateInput = $("#date");
    // No telemóvel a data escolhe-se por lista, mas quem manda continua a ser
    // #date: um único estado, dois controlos a escrever nele.
    const daySelect = $("#day-select");
    const resultsPanel = $(".app-agenda-results");
    const slotsContainer = $("#agenda-slots-container");
    const statusPill = $("#availability-status-pill");

    const slotsUrl = slotsContainer.data("slots-url");
    const bookingUrl = slotsContainer.data("booking-url");

    function escapeHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function updateBrowserUrl(serviceId, selectedDate) {
        // Keep URL synchronized without reloading the page.
        const newUrl = `/agenda-publica/?service=${encodeURIComponent(serviceId)}&date=${encodeURIComponent(selectedDate)}`;
        window.history.pushState({}, "", newUrl);
    }

    function renderLoading() {
        // Keep current slots visible and show only a loading overlay.
        slotsContainer.addClass("is-loading");
    }

    function getDefaultStatus() {
        return {
            type: "no_slots",
            is_fully_blocked: false,
            title: "Horários esgotados",
            message: "Horários esgotados, favor verificar outro dia.",
            icon: "bi-clock-history",
            block_title: "",
            block_notes: ""
        };
    }

    function updateAvailabilityStatus(status) {
        const safeStatus = status || getDefaultStatus();
        const typeClass = `status-${safeStatus.type || "no_slots"}`;
        const iconClass = safeStatus.icon || "bi-clock-history";

        statusPill
            .removeClass(function (_index, className) {
                return (className.match(/(^|\s)status-\S+/g) || []).join(" ");
            })
            .addClass(typeClass)
            .html(`
                <i class="bi ${escapeHtml(iconClass)}"></i>
                <span>${escapeHtml(safeStatus.title)}</span>
            `);
    }

    function renderEmpty(status) {
        // Show empty state when there are no available slots.
        const safeStatus = status || getDefaultStatus();
        const icon = escapeHtml(safeStatus.icon || "bi-clock-history");
        const title = escapeHtml(safeStatus.title || "Nenhum horário disponível");
        const message = escapeHtml(
            safeStatus.message || "Tente escolher outra data ou outro serviço."
        );

        if (safeStatus.is_fully_blocked) {
            slotsContainer.html(`
                <div class="app-empty-state app-full-blocked-state">
                    <div class="app-empty-icon">
                        <i class="bi ${icon}"></i>
                    </div>
                    <h3>${title}</h3>
                    <p>${message}</p>
                </div>
            `);
            return;
        }

        slotsContainer.html(`
            <div class="app-empty-state">
                <div class="app-empty-icon">
                    <i class="bi ${icon}"></i>
                </div>
                <h3>${title}</h3>
                <p>${message}</p>
            </div>
        `);
    }

    function renderSlots(slots, serviceId, selectedDate, status) {
        // Render available slots returned by the backend.
        updateAvailabilityStatus(status);

        if (!slots || slots.length === 0) {
            renderEmpty(status);
            return;
        }

        const labelReserved = slotsContainer.data("label-reserved") || "Reservado";

        let html = `<div class="app-slots-grid">`;

        slots.forEach(function (slot) {
            // Horários ocupados continuam visíveis, mas riscados e sem ligação:
            // a cliente vê a agenda cheia em vez de um dia aparentemente vazio.
            // O rótulo escondido é para quem usa leitor de ecrã e não vê o risco.
            if (slot.is_available === false) {
                html += `
                    <div class="app-slot-card is-reserved" aria-disabled="true"
                         title="${escapeHtml(labelReserved)}">
                        <span class="app-slot-time">${escapeHtml(slot.label)}</span>
                        <span class="visually-hidden">${escapeHtml(labelReserved)}</span>
                    </div>
                `;
                return;
            }

            const appointmentUrl = `${bookingUrl}?service=${encodeURIComponent(serviceId)}&date=${encodeURIComponent(selectedDate)}&start_time=${encodeURIComponent(slot.value)}`;

            html += `
                <a href="${appointmentUrl}" class="app-slot-card">
                    <span class="app-slot-time">${escapeHtml(slot.label)}</span>
                </a>
            `;
        });

        html += `</div>`;

        slotsContainer.html(html);
    }

    function updateSelectedWeekDay(selectedDate) {
        // Update active day in the week strip.
        const weekDays = $(".app-week-day");

        weekDays.removeClass("is-active");

        weekDays.each(function () {
            const dayLink = $(this);

            if (dayLink.data("date") === selectedDate) {
                dayLink.addClass("is-active");
            }
        });

        updateDaySelect(selectedDate);
    }

    function formatarDia(valor) {
        // "segunda-feira, 18 de agosto"
        const partes = valor.split("-");
        const data = new Date(partes[0], partes[1] - 1, partes[2]);

        return data.toLocaleDateString(document.documentElement.lang || "pt-PT", {
            weekday: "long",
            day: "numeric",
            month: "long",
        });
    }

    function updateDaySelect(selectedDate) {
        if (!daySelect.length || daySelect.val() === selectedDate) {
            return;
        }

        // A lista só traz os dias em que a clínica abre. Se a data vier de
        // outro sítio — do campo de data ou de um link — a opção pode não
        // existir, e a lista ficaria em branco a mostrar um dia diferente
        // daquele que a página está a apresentar.
        if (!daySelect.find(`option[value="${selectedDate}"]`).length) {
            daySelect.append(
                $("<option>", {
                    value: selectedDate,
                    text: formatarDia(selectedDate),
                })
            );
        }

        daySelect.val(selectedDate);
    }

    function loadAvailableSlots() {
        // Load available slots using AJAX.
        const serviceId = serviceInput.val();
        const selectedDate = dateInput.val();

        if (!serviceId || !selectedDate) {
            const status = getDefaultStatus();
            updateAvailabilityStatus(status);
            renderEmpty(status);
            return;
        }

        resultsPanel.addClass("is-loading");

        renderLoading();

        $.ajax({
            url: slotsUrl,
            method: "GET",
            data: {
                service: serviceId,
                date: selectedDate
            },
            success: function (response) {
                renderSlots(response.slots, serviceId, selectedDate, response.availability_status);
                updateBrowserUrl(serviceId, selectedDate);
                updateSelectedWeekDay(selectedDate);
            },
            error: function () {
                slotsContainer.html(`
                    <div class="app-empty-state">
                        <div class="app-empty-icon">
                            <i class="bi bi-exclamation-triangle"></i>
                        </div>
                        <h3>Erro ao carregar horários</h3>
                        <p>Tente novamente dentro de instantes.</p>
                    </div>
                `);
            },
            complete: function () {
                resultsPanel.removeClass("is-loading");
                slotsContainer.removeClass("is-loading");
            }
        });
    }

    serviceInput.on("change", loadAvailableSlots);
    dateInput.on("change", loadAvailableSlots);

    daySelect.on("change", function () {
        dateInput.val(daySelect.val());
        loadAvailableSlots();
    });

    // Escolher o serviço segue a ligação do catálogo e recarrega a página.
    // Era trocada só a grelha de horários, e isso deixava para trás tudo o
    // resto que depende do serviço: a faixa de dias continuava a mostrar as
    // vagas do serviço anterior, e numa página que abre sem serviço nenhum
    // nem sequer havia faixa para trocar.

    // ------------------------------------------------------------------
    // Carrossel de dias
    //
    // A faixa traz todos os dias de trabalho que o site aceita marcar, do
    // primeiro ao fim do horizonte, e mostra os que couberem no ecrã. As setas
    // correm-na de uma página de cada vez; quem tem ecrã tátil continua a
    // arrastar.
    // ------------------------------------------------------------------

    const weekStrip = $("#app-week-strip");
    const weekArrows = $("[data-week-arrow]");

    function updateWeekArrows() {
        if (!weekStrip.length) {
            return;
        }

        const strip = weekStrip[0];
        // Um pixel de folga: a rolagem dá valores fracionários e o fim quase
        // nunca calha exatamente em scrollWidth - clientWidth.
        const inicio = strip.scrollLeft <= 1;
        const fim = strip.scrollLeft >= strip.scrollWidth - strip.clientWidth - 1;

        weekArrows.filter('[data-week-arrow="prev"]').prop("disabled", inicio);
        weekArrows.filter('[data-week-arrow="next"]').prop("disabled", fim);
    }

    function scrollWeekStrip(direcao) {
        const strip = weekStrip[0];
        const primeiroDia = weekStrip.find(".app-week-day").first();
        // Uma página de cada vez, mas nunca menos do que um dia: num ecrã
        // estreito onde só cabe um cartão e meio, saltar a largura visível
        // deixava meio dia por ver de cada vez que se carregava na seta.
        const largura = Math.max(
            strip.clientWidth,
            primeiroDia.length ? primeiroDia.outerWidth(true) : 0
        );

        strip.scrollBy({ left: direcao * largura, behavior: "smooth" });
    }

    weekArrows.on("click", function () {
        scrollWeekStrip($(this).data("week-arrow") === "prev" ? -1 : 1);
    });

    weekStrip.on("scroll", updateWeekArrows);
    $(window).on("resize", updateWeekArrows);

    // Com uma data no endereço, o dia escolhido pode estar fora do que se vê:
    // a faixa começa sempre em hoje, e sem isto a marcação escolhida ficava
    // longe à direita, sem sinal nenhum de que estava lá.
    const diaAtivo = weekStrip.find(".app-week-day.is-active")[0];

    if (diaAtivo) {
        // Sem animação e sem mexer na página à volta, ao contrário do que
        // `scrollIntoView` faria: ao abrir, o dia escolhido está no sítio, não
        // desliza até lá nem arrasta a página consigo.
        weekStrip[0].scrollLeft = diaAtivo.offsetLeft - weekStrip[0].offsetLeft;
    }

    updateWeekArrows();

    $(".app-week-day").on("click", function (event) {
        // Load selected week day without full page reload.
        event.preventDefault();

        const selectedDate = $(this).data("date");

        if (!selectedDate) {
            return;
        }

        dateInput.val(selectedDate);
        loadAvailableSlots();
    });
});
