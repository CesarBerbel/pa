$(document).ready(function () {
    // Public visual schedule AJAX controller.

    const serviceInput = $("#service");
    const dateInput = $("#date");
    const filterForm = $("#agenda-filter-form");
    const filterPanel = $(".app-agenda-filter");
    const resultsPanel = $(".app-agenda-results");
    const slotsContainer = $("#agenda-slots-container");
    const weekDays = $(".app-week-day");

    const slotsUrl = slotsContainer.data("slots-url");
    const bookingUrl = slotsContainer.data("booking-url");

    function updateBrowserUrl(serviceId, selectedDate) {
        // Keep URL synchronized without reloading the page.
        const newUrl = `/agenda-publica/?service=${encodeURIComponent(serviceId)}&date=${encodeURIComponent(selectedDate)}`;
        window.history.pushState({}, "", newUrl);
    }

    function renderLoading() {
        // Keep current slots visible and show only a loading overlay.
        slotsContainer.addClass("is-loading");
    }

    function renderEmpty() {
        // Show empty state when there are no available slots.
        slotsContainer.html(`
            <div class="app-empty-state">
                <div class="app-empty-icon">⌛</div>
                <h3>Nenhum horário disponível</h3>
                <p>Tente escolher outra data ou outro serviço.</p>
            </div>
        `);
    }

    function renderSlots(slots, serviceId, selectedDate) {
        // Render available slots returned by the backend.
        if (!slots || slots.length === 0) {
            renderEmpty();
            return;
        }

        let html = `<div class="app-slots-grid">`;

        slots.forEach(function (slot) {
            const appointmentUrl = `${bookingUrl}?service=${encodeURIComponent(serviceId)}&date=${encodeURIComponent(selectedDate)}&start_time=${encodeURIComponent(slot.value)}`;

            html += `
                <a href="${appointmentUrl}" class="app-slot-card">
                    <span class="app-slot-time">
                        ${slot.label}
                    </span>

                    <span class="app-slot-status">
                        Disponível
                    </span>

                    <span class="app-slot-cta">
                        Marcar
                    </span>
                </a>
            `;
        });

        html += `</div>`;

        slotsContainer.html(html);
    }

    function updateSelectedWeekDay(selectedDate) {
        // Update active day in the week strip.
        weekDays.removeClass("is-active");

        weekDays.each(function () {
            const dayLink = $(this);

            if (dayLink.data("date") === selectedDate) {
                dayLink.addClass("is-active");
            }
        });
    }

    function updateServiceSummary() {
        // Update selected service summary without page reload.
        const selectedOption = serviceInput.find("option:selected");

        $("#selected-service-name").text(selectedOption.data("name") || selectedOption.text());
        $("#selected-service-duration").text((selectedOption.data("duration") || "") + " minutos");
    }

    function loadAvailableSlots() {
        // Load available slots using AJAX.
        const serviceId = serviceInput.val();
        const selectedDate = dateInput.val();

        if (!serviceId || !selectedDate) {
            renderEmpty();
            return;
        }

        filterForm.addClass("is-loading");
        filterPanel.addClass("is-loading");
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
                renderSlots(response.slots, serviceId, selectedDate);
                updateBrowserUrl(serviceId, selectedDate);
                updateSelectedWeekDay(selectedDate);
                updateServiceSummary();
            },
            error: function () {
                slotsContainer.html(`
                    <div class="app-empty-state">
                        <div class="app-empty-icon">⚠️</div>
                        <h3>Erro ao carregar horários</h3>
                        <p>Tente novamente dentro de instantes.</p>
                    </div>
                `);
            },
            complete: function () {
                filterForm.removeClass("is-loading");
                filterPanel.removeClass("is-loading");
                resultsPanel.removeClass("is-loading");
                slotsContainer.removeClass("is-loading");
            }
        });
    }

    serviceInput.on("change", loadAvailableSlots);
    dateInput.on("change", loadAvailableSlots);

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