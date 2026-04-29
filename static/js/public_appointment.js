$(document).ready(function () {
    // Load available slots when service or date changes.
    function loadAvailableSlots() {
        const serviceId = $("#id_service").val();
        const selectedDate = $("#id_date").val();
        const startTimeSelect = $("#id_start_time");

        startTimeSelect.empty();
        startTimeSelect.append(
            $("<option>", {
                value: "",
                text: "Carregando horários..."
            })
        );

        if (!serviceId || !selectedDate) {
            startTimeSelect.empty();
            startTimeSelect.append(
                $("<option>", {
                    value: "",
                    text: "Selecione um serviço e uma data"
                })
            );
            return;
        }

        $.ajax({
            url: "/marcar/horarios/",
            method: "GET",
            data: {
                service: serviceId,
                date: selectedDate
            },
            success: function (response) {
                startTimeSelect.empty();

                if (!response.slots || response.slots.length === 0) {
                    startTimeSelect.append(
                        $("<option>", {
                            value: "",
                            text: "Nenhum horário disponível"
                        })
                    );
                    return;
                }

                startTimeSelect.append(
                    $("<option>", {
                        value: "",
                        text: "Selecione um horário"
                    })
                );

                response.slots.forEach(function (slot) {
                    startTimeSelect.append(
                        $("<option>", {
                            value: slot.value,
                            text: slot.label
                        })
                    );
                });
            },
            error: function () {
                startTimeSelect.empty();
                startTimeSelect.append(
                    $("<option>", {
                        value: "",
                        text: "Erro ao carregar horários"
                    })
                );
            }
        });
    }

    $("#id_service, #id_date").on("change", function () {
        loadAvailableSlots();
    });

    // Load slots automatically when the page already has service and date.
    if ($("#id_service").val() && $("#id_date").val()) {
        loadAvailableSlots();
    }
});